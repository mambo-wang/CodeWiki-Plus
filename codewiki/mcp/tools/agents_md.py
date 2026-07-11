"""Inject wiki usage instructions into the target project's AGENTS.md.

Called from ``close_session`` after wiki generation completes.  Uses HTML
comment delimiters so repeated invocations update only the CodeWiki section
without overwriting user-authored content.
"""

from __future__ import annotations

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


def write_agents_md(session: SessionState) -> None:
    """Create or update ``<repo_path>/AGENTS.md`` with wiki usage info.

    - If the file does not exist, it is created with the section.
    - If the section markers are found, only the delimited block is replaced.
    - If the file exists but has no markers, the section is appended.

    Failures are logged and silently swallowed — this must never block
    session cleanup.
    """
    repo_path = Path(session.repo_path)
    output_dir = Path(session.output_dir)

    # Relative path from repo root to wiki output (portable across machines)
    try:
        rel_path = os.path.relpath(output_dir, repo_path).replace("\\", "/")
    except ValueError:
        # On Windows, relpath fails across drives — fall back to absolute
        rel_path = str(output_dir).replace("\\", "/")

    # Extract module names from the saved module tree
    modules = _extract_modules(session.module_tree)

    section = _build_section(rel_path, modules)
    agents_path = repo_path / "AGENTS.md"

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


def _build_section(rel_path: str, modules: list[str]) -> str:
    """Build the delimited Markdown section for AGENTS.md."""

    # Module listing with links
    if modules:
        module_lines = "\n".join(
            f"- [{m}]({rel_path}/{m}.md)" for m in modules
        )
        modules_block = f"\n**模块列表：**\n\n{module_lines}\n"
    else:
        modules_block = ""

    return f"""\
{_BEGIN_MARKER}

## CodeWiki LLM Wiki

本项目已使用 [CodeWiki](https://github.com/mambo-wang/CodeWiki-CN) 生成 LLM Wiki 文档，位于 `{rel_path}/` 目录。

**入口文件：**

- [`{rel_path}/overview.md`]({rel_path}/overview.md) — 仓库级架构总览（含 Mermaid 架构图）
- [`{rel_path}/index.md`]({rel_path}/index.md) — 文档目录与知识笔记索引
- [`{rel_path}/schema.yaml`]({rel_path}/schema.yaml) — 项目文档约定（命名规范、必填章节等）
{modules_block}
### MCP 工具用法

如果当前 IDE 已配置 CodeWiki MCP 服务器，可直接使用以下工具：

**查询文档和笔记（query_wiki）：**

```json
{{
  "query": "如何处理依赖分析",
  "scope": "模块名（可选，限定搜索范围）",
  "include_notes": true,
  "include_code_refs": true,
  "max_results": 10,
  "expand_terms": ["依赖图", "依赖追踪"]
}}
```

返回排序后的匹配结果（含上下文片段）和相关组件 ID。在编码、调试或做设计决策时，先查询 wiki 获取相关上下文。

**归档决策/经验教训（ingest_note）：**

```json
{{
  "note_type": "decision",
  "title": "选择 SQLite 作为缓存后端",
  "content": "选择原因：...",
  "related_modules": ["模块名"]
}}
```

`note_type` 可选值：`decision`（设计决策）、`lesson`（经验教训）、`architecture`（架构说明）、`bug_fix`（Bug 修复记录）、`general`（通用笔记）。笔记存储在 `{rel_path}/notes/` 目录，可被 `query_wiki` 检索。

**文档一致性检查（lint_wiki）：**

```json
{{}}
```

检查文档与代码是否一致，包括：过时引用、断链、未文档化组件、循环依赖、覆盖率。

### 使用建议

1. **编码前**：先用 `query_wiki` 搜索相关模块文档，了解架构约定和依赖关系
2. **做决策时**：用 `query_wiki` 搜索已有的 `decision` 类型笔记，避免重复讨论
3. **完成重要决策后**：用 `ingest_note` 归档，让未来的 Agent 和团队成员都能查到
4. **定期维护**：用 `lint_wiki` 检查文档是否过时，保持文档与代码同步

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

{_END_MARKER}"""
