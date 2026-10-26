"""LLMBackend — unified abstraction over the API LLM path.

CodeWiki has two LLM call shapes:

* a synchronous single-shot completion (clustering, parent / repo overviews)
* an asynchronous multi-turn agentic loop with custom tools (per-module docs)

The single implementation satisfies this interface:

* :class:`PydanticAIBackend` — wraps the openai-compatible / anthropic
  / bedrock / azure-openai paths via pydantic-ai + litellm.  API-key based.

Provider selection happens in one place: :func:`get_backend`.
"""

from __future__ import annotations

import abc
import os
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from codewiki.src.be.dependency_analyzer.models.core import Node


def module_page_present(working_dir: str, module_name: str) -> bool:
    """Return True when *module_name*'s own page already exists on disk.

    Skip granularity is the page, never the run (ADR-0020 decision 2).
    ``overview.md`` must not be used as a global shortcut: it exists after any
    completed run, so gating on it would make a missing module page
    unfillable. Each backend calls this before spawning its module agent.
    """
    return os.path.exists(os.path.join(working_dir, f"{module_name}.md"))


class LLMBackend(abc.ABC):
    """Abstract LLM backend used by the documentation generator."""

    @abc.abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        """Single-shot text completion."""

    @abc.abstractmethod
    async def run_module_agent(
        self,
        module_name: str,
        components: Dict[str, "Node"],
        core_component_ids: List[str],
        module_path: List[str],
        working_dir: str,
    ) -> Dict[str, Any]:
        """Run the per-module agent loop.  Returns the updated module_tree dict."""


def get_backend(config) -> "LLMBackend":
    """Return the backend instance matching ``config.provider``."""
    from codewiki.src.be.pydantic_ai_backend import PydanticAIBackend

    return PydanticAIBackend(config)
