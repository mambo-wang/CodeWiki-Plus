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

{_END_MARKER}"""
