"""CawBackend — subscription-mode backend using the ``claude`` / ``codex`` CLIs.

Implements :class:`LLMBackend` by routing all completions and agent runs
through :mod:`caw`, which wraps the official Claude Code and Codex CLI
binaries.  Authentication is the user's existing OAuth subscription — no
API key is needed.

Provider mapping:

* ``provider="claude-code"`` → caw provider ``"claude_code"``
* ``provider="codex"``       → caw provider ``"codex"``

``config.main_model`` is passed straight through to caw.  caw forwards it
to ``claude --model`` / ``codex --model``; whichever values those CLIs
accept are valid here.  ``config.cluster_model`` is honored per-call when
passed explicitly through :meth:`complete`.  ``config.fallback_model`` is
ignored (caw has no built-in fallback chain).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import Any, Dict, List

from caw import Agent as CawAgent
from caw import ToolGroup

from codewiki.src.be.agent_tools.deps import CodeWikiDeps
from codewiki.src.be.backend import LLMBackend
from codewiki.src.be.dependency_analyzer.models.core import Node
from codewiki.src.be.prompt_template import (
    format_leaf_system_prompt,
    format_system_prompt,
    format_user_prompt,
)
from codewiki.src.be.utils import is_complex_module
from codewiki.src.config import MODULE_TREE_FILENAME, OVERVIEW_FILENAME, Config
from codewiki.src.utils import file_manager

logger = logging.getLogger(__name__)


_CAW_PROVIDER_MAP = {
    "claude-code": "claude_code",
    "codex": "codex",
}

_CLI_BINARY = {
    "claude-code": "claude",
    "codex": "codex",
}

# Disable WRITER (Write/Edit/NotebookEdit) so the agent must use CodeWiki's
# str_replace_editor and Mermaid validation runs.  EXEC (Bash), INTERACTION
# (AskUserQuestion) and WEB (WebFetch/WebSearch) are also off — keeps behaviour
# in line with the pydantic-ai path which exposes no shell, prompt or web
# access.  PARALLEL (Task) stays enabled: Claude Code can fan out Read-heavy
# exploration without affecting documentation correctness.
_AGENT_TOOL_GROUP = (
    ToolGroup.ALL - ToolGroup.WRITER - ToolGroup.EXEC - ToolGroup.INTERACTION - ToolGroup.WEB
)


def _resolve_caw_provider(provider: str) -> str:
    try:
        return _CAW_PROVIDER_MAP[provider]
    except KeyError as e:
        raise ValueError(
            f"Unsupported caw provider {provider!r}. Expected one of: "
            f"{sorted(_CAW_PROVIDER_MAP.keys())}"
        ) from e


class CawBackend(LLMBackend):
    """Routes LLM operations through the claude / codex CLI subscription."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._caw_provider = _resolve_caw_provider(config.provider)
        # main_model is passed straight through; empty string → caw default.
        self._model: str | None = config.main_model or None

        # Fail loudly here rather than producing a confusing caw error mid-run.
        cli = _CLI_BINARY[config.provider]
        if shutil.which(cli) is None:
            raise RuntimeError(
                f"Subscription mode requires the '{cli}' CLI on PATH. "
                f"Install it and run '{cli} login', then try again."
            )

    # ------------------------------------------------------------------
    # Single-shot completion (clustering, parent / repo overviews)
    # ------------------------------------------------------------------

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,  # unused: subscription CLIs don't expose temperature
    ) -> str:
        # Blocks the calling thread for the lifetime of the claude/codex
        # subprocess.  Callers running this from an async context (e.g. the
        # documentation_generator) accept this — there is no concurrent work
        # to do while clustering is in flight anyway.
        effective_model = model or self._model
        agent = CawAgent(
            provider=self._caw_provider,
            model=effective_model,
            tools=ToolGroup.READER,
        )
        traj = agent.completion(prompt)
        return traj.result

    # ------------------------------------------------------------------
    # Per-module agent loop
    # ------------------------------------------------------------------

    async def run_module_agent(
        self,
        module_name: str,
        components: Dict[str, Node],
        core_component_ids: List[str],
        module_path: List[str],
        working_dir: str,
    ) -> Dict[str, Any]:
        # caw.completion shells out to a subprocess and blocks the calling
        # thread.  Push it off the event loop so the rest of the async
        # pipeline keeps moving.
        return await asyncio.to_thread(
            self._run_module_agent_sync,
            module_name,
            components,
            core_component_ids,
            module_path,
            working_dir,
        )

    def _run_module_agent_sync(
        self,
        module_name: str,
        components: Dict[str, Node],
        core_component_ids: List[str],
        module_path: List[str],
        working_dir: str,
        start_depth: int = 1,
    ) -> Dict[str, Any]:
        # ``start_depth`` lets the recursion preserve max_depth across nested
        # _run_module_agent_sync calls — each fresh deps object would otherwise
        # reset current_depth to 1 and silently bypass max_depth guards.
        from codewiki.src.be.caw_toolkit import CawToolKit  # local import to avoid cycles

        config = self._config
        module_tree_path = os.path.join(working_dir, MODULE_TREE_FILENAME)
        module_tree = file_manager.load_json(module_tree_path)

        overview_docs_path = os.path.join(working_dir, OVERVIEW_FILENAME)
        if os.path.exists(overview_docs_path):
            logger.info("✓ Overview docs already exists at %s", overview_docs_path)
            return module_tree
        docs_path = os.path.join(working_dir, f"{module_name}.md")
        if os.path.exists(docs_path):
            logger.info("✓ Module docs already exists at %s", docs_path)
            return module_tree

        custom_instructions = config.get_prompt_addition()
        is_complex = is_complex_module(components, core_component_ids)
        if is_complex:
            system_prompt = format_system_prompt(module_name, custom_instructions)
        else:
            system_prompt = format_leaf_system_prompt(module_name, custom_instructions)

        deps = CodeWikiDeps(
            absolute_docs_path=working_dir,
            absolute_repo_path=str(os.path.abspath(config.repo_path)),
            registry={},
            components=components,
            path_to_current_module=list(module_path),
            current_module_name=module_name,
            module_tree=module_tree,
            max_depth=config.max_depth,
            current_depth=start_depth,
            config=config,
            custom_instructions=custom_instructions,
        )

        # Sub-agent delegation is only meaningful for multi-file modules
        # that have not yet reached the configured recursion depth.
        allow_subagent = is_complex and start_depth < config.max_depth
        toolkit = CawToolKit(deps=deps, backend=self, allow_subagent=allow_subagent)

        agent = CawAgent(
            provider=self._caw_provider,
            model=self._model,
            system_prompt=system_prompt,
            tools=_AGENT_TOOL_GROUP,
            tool_servers=[toolkit],
        )

        user_prompt = format_user_prompt(
            module_name=module_name,
            core_component_ids=core_component_ids,
            components=components,
            module_tree=deps.module_tree,
        )

        try:
            traj = agent.completion(user_prompt)
            logger.info(
                "Module %s completed via caw (turns=%d, tool_calls=%d)",
                module_name,
                traj.num_turns,
                traj.total_tool_calls,
            )
            file_manager.save_json(deps.module_tree, module_tree_path)
            return deps.module_tree
        except Exception as e:
            logger.error("Error processing module %s via caw: %s", module_name, e)
            raise
