"""Inject wiki usage instructions into the target project's AGENTS.md.

Called from ``close_session`` after wiki generation completes.  Uses HTML
comment delimiters so repeated invocations update only the CodeWiki section
without overwriting user-authored content.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codewiki.mcp.session import SessionState

logger = logging.getLogger(__name__)

# Delimiters for the injectable section
_BEGIN_MARKER = "<!-- CodeWiki LLM Wiki -->"
_END_MARKER = "<!-- /CodeWiki LLM Wiki -->"


def write_agents_md(*, repo_path: str, output_dir: str, module_tree: dict | None = None) -> None:
    """Create or update ``<repo_path>/AGENTS.md`` with wiki usage info.

    - If the file does not exist, it is created with the section.
    - If the section markers are found, only the delimited block is replaced.
    - If the file exists but has no markers, the section is appended.

    Failures are logged and silently swallowed — this must never block
    session cleanup.
    """
    _write_agents_md(repo_path, output_dir, module_tree or {})


def _write_agents_md(repo_path: str, output_dir: str, module_tree: dict) -> None:
    """Internal implementation of write_agents_md."""
    repo_path_p = Path(repo_path)
    output_dir_p = Path(output_dir)

    # Relative path from repo root to wiki output (portable across machines)
    try:
        rel_path = os.path.relpath(output_dir_p, repo_path_p).replace("\\", "/")
    except ValueError:
        # On Windows, relpath fails across drives — fall back to absolute
        rel_path = str(output_dir_p).replace("\\", "/")

    # Extract module names from the saved module tree
    modules = _extract_modules(module_tree)

    section = _build_section(rel_path, modules, output_dir_p)
    agents_path = repo_path_p / "AGENTS.md"

    if agents_path.exists():
        content = agents_path.read_text(encoding="utf-8")
        begin_idx = content.find(_BEGIN_MARKER)
        end_idx = content.find(_END_MARKER)

        if begin_idx != -1 and end_idx != -1 and end_idx > begin_idx:
            # Replace existing section (keep content before/after)
            before = content[:begin_idx]
            after = content[end_idx + len(_END_MARKER):]
            new_content = before + section + after
        else:
            # Append section at end
            separator = "\n\n" if not content.endswith("\n") else "\n"
            new_content = content + separator + section + "\n"
    else:
        new_content = section + "\n"

    agents_path.write_text(new_content, encoding="utf-8")
    logger.info("Updated AGENTS.md at %s", agents_path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_modules(module_tree: dict) -> list[str]:
    """Recursively collect all module names (top-level + nested children)."""
    names: list[str] = []
    if not module_tree or not isinstance(module_tree, dict):
        return names
    for name, node in module_tree.items():
        names.append(name)
        children = node.get("children") if isinstance(node, dict) else None
        if children and isinstance(children, dict):
            names.extend(_extract_modules(children))
    return names


def _build_section(rel_path: str, modules: list[str], output_dir_p: Path) -> str:
    """Build the delimited Markdown section for AGENTS.md."""

    # Module listing with links (structured wiki layout)
    if modules:
        # V2 (injection budget): cap the module list; overflow collapses to a
        # pointer line so AGENTS.md stops growing linearly with module count.
        try:
            from codewiki.mcp.tools.page_router import load_schema
            from codewiki.mcp.tools.injection_budget import cap_module_lines
            capped = cap_module_lines(
                modules, output_dir_p, load_schema(str(output_dir_p))
            )
        except Exception:  # budget must never break AGENTS.md injection
            capped = {"lines": modules, "hidden_count": 0}
        module_lines = "\n".join(
            f"- [{m}]({rel_path}/wiki/modules/{m}.md)" for m in capped["lines"]
        )
        hidden = int(capped.get("hidden_count") or 0)
        overflow = (
            f"\n（其余 {hidden} 个模块省略——用 `{rel_path}/wiki/index.md` 或 `query_wiki` 检索）"
            if hidden else ""
        )
        modules_block = f"\n**模块列表：**\n\n{module_lines}{overflow}\n"
    else:
        modules_block = ""

    return f"""\
{_BEGIN_MARKER}

## CodeWiki LLM Wiki

本项目已使用 [CodeWiki](https://github.com/mambo-wang/CodeWiki-Plus) 生成 LLM Wiki 文档，位于 `{rel_path}/` 目录。

**入口文件：**

- [`{rel_path}/wiki/overview.md`]({rel_path}/wiki/overview.md) — 仓库级架构总览（含 Mermaid 架构图）
- [`{rel_path}/wiki/index.md`]({rel_path}/wiki/index.md) — 文档目录与知识笔记索引
- [`{rel_path}/schema.yaml`]({rel_path}/schema.yaml) — 项目文档约定（命名规范、必填章节等）
{modules_block}
### 使用建议

1. **编码前**：先用 `query_wiki` 搜索相关模块文档，了解架构约定和依赖关系
2. **做决策时**：用 `query_wiki` 搜索已有的 `decision` 类型笔记，避免重复讨论
3. **完成重要决策后**：用 `ingest_note` 归档，让未来的 Agent 和团队成员都能查到
4. **定期维护**：用 `lint_wiki` 检查文档是否过时，保持文档与代码同步

### 采纳声明（检索反馈）

当你通过 `query_wiki` 检索并**实际使用了**某条结果（作为决策依据、修改参照或答案来源）时，在最终回复中附带一行声明注释：

```
<!-- codewiki:referenced-docs: ["notes/pitfall-xxx.md", "wiki/modules/yyy.md"] -->
```

路径必须与 query_wiki 返回的 `file` 字段完全一致。声明过的文档会获得采纳计数（`usage.adopted_count`），在未来检索中排序提升（采纳权重是单纯召回的 2 倍）；长期高频召回却零采纳的笔记会被 `lint_wiki` 的 `low_adoption` 检查标记为"需要重写得更可操作"。

**注意**：只声明真正用到的文档——这是帮助知识库学习"什么内容真正有用"的信号，不是礼貌性致谢。忘了声明没关系（漏报可容忍），但不要声明没用过的（误报不可容忍）。

### 纠正识别与经验沉淀

当你被用户纠正、吐槽或补充了未知上下文时，这可能是值得沉淀的经验。按以下规则处理：

**识别纠正信号（满足任一即触发）：**

- 用户明确否定你的输出："不对""你搞错了""不是这样的""应该是…"
- 用户表达重复犯错的不满："又…""上次就…""为什么又…"
- 你修改了自己的输出后用户仍不满意，说明理解有根本偏差
- 用户补充了你不知道的关键上下文："你不知道吗…""这个项目一直都是…""我们约定过…"
- 用户指出方法名/Javadoc 与实际行为不一致，或指出代码中的历史遗留问题

**执行三步流程：**

1. **反思**：明确说出自己错在哪里、正确做法是什么、根因是什么（是缺少项目上下文？还是对代码理解有误？）
2. **起草笔记**：将教训整理为结构化内容，包含：背景（什么场景下犯了错）、正确做法、根因分析
3. **征求确认**：向用户展示笔记草稿，询问"要把这条经验记录到 Wiki 吗？"——**必须得到用户确认后才执行 `ingest_note`**，不要默默保存

**归档示例：**

```json
{{
  "note_type": "lesson",
  "title": "OrderService.process() 只做参数校验不做业务处理",
  "content": "## 背景\\n\\nAgent 误以为 OrderService.process() 包含完整业务逻辑，基于方法名做了错误的设计假设。\\n\\n## 正确做法\\n\\nprocess() 仅做入参校验和格式化，实际业务处理在 OrderService.execute() 中。老项目方法名与实际行为不一致是常见情况，应优先阅读实现而非信任方法名。\\n\\n## 根因\\n\\n十几年老项目，方法经过多次重构但名称未更新。",
  "related_modules": ["order"]
}}
```

**注意**：不是每次纠正都需要沉淀。只记录有复用价值的经验——特定于本次任务的临时调整、用户个人偏好等不需要记录。判断标准：如果未来的 Agent 或新同事遇到同样场景时这条经验有用，就值得记录。

### 主动知识沉淀

不要等用户纠正才记录。当对话中出现以下信号时，主动执行反思并提取知识：

**触发信号（满足任一即激活反思）：**

- 完成一个多步骤调试/排查后定位到根因（尤其是走了弯路的情况）
- 讨论了两个及以上方案并做出了选择
- 发现代码实际行为与文档/命名/注释不一致
- 用户补充了隐性项目知识（约定、历史原因、"我们一直这么做"）
- 一次探索性调研收敛到明确结论
- 发现了可复用的模式、工具链用法或环境配置技巧

**四问过滤（全部通过才值得记录）：**

1. 下一次对话（无本次上下文）还能用到吗？
2. 另一个 Agent 或新同事遇到同样场景能直接受益吗？
3. `query_wiki` 确认现有文档未覆盖？
4. 属于"事实/决策/模式/教训"而非"本次任务临时状态"？

**路由表：**

| 知识类型 | 写入方式 |
|---------|---------|
| 做了技术选型/方案取舍 | `ingest_note(note_type="decision")` |
| 踩坑/易错点 | `ingest_note(note_type="pitfall")` |
| 经验教训（调试过程、认知修正） | `ingest_note(note_type="lesson")` |
| 架构层面的事实发现 | `ingest_note(note_type="architecture")` |
| 临时绕过方案（含恢复条件） | `ingest_note(note_type="workaround")` |
| 多方案横向对比（含表格） | `write_doc_file(page_type="comparison")` |
| 调研结论存档 | `write_doc_file(page_type="query")` |

**执行流程：**

1. 识别到触发信号后，回顾相关对话片段，提取候选知识项
2. 对每个候选项执行四问过滤，丢弃未通过的
3. 用 `query_wiki` 检查是否已有覆盖（避免重复）
4. 按路由表确定写入方式，起草结构化内容（背景→结论→根因→适用范围）
5. 向用户展示草稿并征求确认——**必须确认后才写入**
6. 一次对话中可积累多个候选项，在自然停顿点（任务完成、话题切换）统一呈现，避免频繁打断

**不要记录的内容：**

- 仅与本次任务相关的临时变量、路径、参数
- 用户个人偏好（这属于 Agent 记忆，不属于项目 Wiki）
- 已在代码注释或 README 中明确写明的信息
- 未经验证的猜测或"可能""也许"级别的推断

{_END_MARKER}"""
