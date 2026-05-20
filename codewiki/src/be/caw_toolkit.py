"""CawToolKit — CodeWiki's three agent tools exposed as a caw MCP server.

A new toolkit instance is created per agent session (top-level module *or*
sub-module).  State lives on ``self``:

* ``self._deps`` is the live :class:`CodeWikiDeps` for the current module
* ``self._backend`` is a back-reference to :class:`CawBackend` so the
  sub-module recursion can start a fresh session without importing
  :mod:`codewiki.src.be.caw_backend` at module load time (circular import)

Claude Code's built-in writers (``Write``/``Edit``/``NotebookEdit``) and
``Bash`` are disabled at the agent level (see :func:`CawBackend._run_module_agent_sync`).
The agent must use ``str_replace_editor`` for all file writes so Mermaid
validation runs uniformly across both backends.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Union

from caw import ToolKit, tool

from codewiki.src.be.agent_tools.deps import CodeWikiDeps

if TYPE_CHECKING:
    from codewiki.src.be.caw_backend import CawBackend

logger = logging.getLogger(__name__)


def _coerce_json_arg(value):
    # Some MCP/CLI bridges emit list/int tool args as JSON-encoded strings
    # (e.g. ``"[1, 50]"`` instead of ``[1, 50]``).  Parity with the
    # pydantic-ai tool path; see _coerce_json_string in str_replace_editor.py.
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


class CawToolKit(
    ToolKit,
    server_name="codewiki_tools",
    display_name="CodeWiki Tools",
):
    """MCP tool server exposing CodeWiki tools to a caw Agent."""

    def __init__(
        self,
        deps: CodeWikiDeps,
        backend: "CawBackend",
        allow_subagent: bool,
    ) -> None:
        self._deps = deps
        self._backend = backend
        self._allow_subagent = allow_subagent

    # ------------------------------------------------------------------
    # Tool: read_code_components
    # ------------------------------------------------------------------

    @tool(
        description=(
            "Read the source code of the given component ids. "
            "component_ids is a list of strings like "
            "['sweagent/types.py::AgentRunResult', 'auth/middleware.py::verify_token'] "
            "where the part before '::' is the file path and the part after is the component name."
        )
    )
    async def read_code_components(self, component_ids: List[str]) -> str:
        results = []
        for cid in component_ids:
            if cid not in self._deps.components:
                results.append(f"# Component {cid} not found")
            else:
                results.append(
                    f"# Component {cid}:\n"
                    f"{self._deps.components[cid].source_code.strip()}\n\n"
                )
        return "\n".join(results)

    # ------------------------------------------------------------------
    # Tool: str_replace_editor
    # Reuses the EditTool implementation + Mermaid validator from the
    # existing module so behavior matches the pydantic-ai path exactly.
    # ------------------------------------------------------------------

    @tool(
        description=(
            "Custom editing tool for viewing, creating and editing files.\n"
            "* If `path` is a file, `view` displays the result of applying `cat -n`. "
            "If `path` is a directory, `view` lists non-hidden files and directories up to 2 levels deep.\n"
            "* The `create` command cannot be used if the specified `path` already exists as a file.\n"
            "* If a `command` generates a long output, it will be truncated and marked with `<response clipped>`.\n"
            "* The `undo_edit` command will revert the last edit made to the file at `path`.\n"
            "* Only `view` command is allowed when `working_dir` is `repo`."
        )
    )
    async def str_replace_editor(
        self,
        working_dir: str,
        command: str,
        path: Optional[str] = None,
        file: Optional[str] = None,
        file_text: Optional[str] = None,
        view_range: Union[List[int], str, None] = None,
        old_str: Optional[str] = None,
        new_str: Optional[str] = None,
        insert_line: Union[int, str, None] = None,
    ) -> str:
        from codewiki.src.be.agent_tools.str_replace_editor import EditTool
        from codewiki.src.be.utils import validate_mermaid_diagrams

        if path is None and file is None:
            return "Error: Either `path` or `file` parameter must be provided."
        if path is None:
            path = file
        if command != "view" and working_dir == "repo":
            return "The `view` command is the only allowed command when `working_dir` is `repo`."

        view_range = _coerce_json_arg(view_range)
        insert_line = _coerce_json_arg(insert_line)

        edit_tool = EditTool(self._deps.registry, self._deps.absolute_docs_path)

        if working_dir == "docs":
            absolute_path = str(Path(self._deps.absolute_docs_path) / path)
        else:
            absolute_path = str(Path(self._deps.absolute_repo_path) / path)

        edit_tool(
            command=command,
            path=absolute_path,
            file_text=file_text,
            view_range=view_range,
            old_str=old_str,
            new_str=new_str,
            insert_line=insert_line,
        )

        result = "\n".join(edit_tool.logs)

        if command != "view" and path.endswith(".md"):
            mermaid_validation = await validate_mermaid_diagrams(absolute_path, path)
            result = result + "\n---------- Mermaid validation ----------\n" + mermaid_validation

        return result

    # ------------------------------------------------------------------
    # Tool: generate_sub_module_documentation
    # ------------------------------------------------------------------

    @tool(
        description=(
            "Delegate documentation generation of sub-modules to sub-agents. Each sub-module "
            "is documented separately.\n"
            "sub_module_specs: a dictionary mapping sub-module names to their core component IDs. "
            "Example: {'authentication': ['auth_handler.py::AuthHandler'], "
            "'database': ['db_client.py::DBClient']}"
        )
    )
    async def generate_sub_module_documentation(
        self, sub_module_specs: Dict[str, List[str]]
    ) -> str:
        if not self._allow_subagent:
            return (
                "generate_sub_module_documentation is not available for this module "
                "(leaf module or max depth reached)."
            )

        # Run the blocking recursion in a worker thread so the caw MCP server's
        # event loop stays responsive while sub-agents run.
        return await asyncio.to_thread(self._run_sub_modules, sub_module_specs)

    # ------------------------------------------------------------------
    # Internal: synchronous recursion driver
    # ------------------------------------------------------------------

    def _run_sub_modules(self, sub_module_specs: Dict[str, List[str]]) -> str:
        deps = self._deps
        previous_module_name = deps.current_module_name

        # Add sub-modules to the in-memory module tree.
        value = deps.module_tree
        for key in deps.path_to_current_module:
            value = value[key]["children"]
        for sub_name, core_ids in sub_module_specs.items():
            value[sub_name] = {"components": core_ids, "children": {}}

        try:
            for sub_name, core_ids in sub_module_specs.items():
                indent = "  " * deps.current_depth
                arrow = "└─" if deps.current_depth > 0 else "→"
                logger.info("%s%s Generating documentation for sub-module: %s", indent, arrow, sub_name)

                deps.current_module_name = sub_name
                deps.path_to_current_module.append(sub_name)
                deps.current_depth += 1
                try:
                    # Spawn a fresh caw session for the sub-module.  We already
                    # run inside a worker thread (started by the parent tool
                    # call), so call the sync entry point directly to avoid
                    # double-wrapping.  ``start_depth`` carries the parent's
                    # depth so the sub-agent's max_depth guard stays accurate.
                    self._backend._run_module_agent_sync(
                        module_name=sub_name,
                        components=deps.components,
                        core_component_ids=core_ids,
                        module_path=list(deps.path_to_current_module),
                        working_dir=deps.absolute_docs_path,
                        start_depth=deps.current_depth,
                    )
                finally:
                    deps.path_to_current_module.pop()
                    deps.current_depth -= 1
        finally:
            deps.current_module_name = previous_module_name

        return (
            "Generate successfully. Documentations: "
            + ", ".join(key + ".md" for key in sub_module_specs.keys())
            + " are saved in the working directory."
        )
