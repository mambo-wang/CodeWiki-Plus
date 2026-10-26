import logging
import os
import json
from typing import Dict, List, Any
from copy import deepcopy
import traceback

# Configure logging and monitoring
logger = logging.getLogger(__name__)

# Local imports
from codewiki.src.be.dependency_analyzer import DependencyGraphBuilder
from codewiki.src.be.backend import LLMBackend, get_backend
from codewiki.src.be.prompt_template import (
    REPO_OVERVIEW_PROMPT,
    MODULE_OVERVIEW_PROMPT,
)
from codewiki.src.be.cluster_modules import (
    cluster_modules,
    get_clustering_input_token_count,
    module_tree_coverage_gap,
)
from codewiki.src.config import (
    Config,
    FIRST_MODULE_TREE_FILENAME,
    MODULE_TREE_FILENAME,
    OVERVIEW_FILENAME,
    meta_join,
    meta_resolve,
)
from codewiki.src.utils import file_manager


class ModuleGenerationError(RuntimeError):
    """A run finished with modules that failed to generate (ADR-0020 #2).

    Raised after every module has had its attempt, so one broken module no
    longer hides behind a successful exit code. Partial pages stay on disk,
    metadata is still written, and the ledger stays resumable (``degraded``).
    """

    def __init__(self, failures: List[tuple[str, str]]):
        self.failures = list(failures)
        detail = "; ".join(f"{name}: {err}" for name, err in self.failures)
        super().__init__(f"{len(self.failures)} module(s) failed: {detail}")


class DocumentationGenerator:
    """Main documentation generation orchestrator."""

    def __init__(self, config: Config, commit_id: str = None, backend: LLMBackend = None):
        self.config = config
        self.commit_id = commit_id
        self.graph_builder = DependencyGraphBuilder(config)
        self.backend: LLMBackend = backend or get_backend(config)

    def _ledger_phase(self, working_dir: str, phase: str) -> None:
        """Mirror *phase* into the job ledger when one exists (ADR-0020 #1).

        The MCP tool path owns the ledger; the legacy pipeline never creates
        it. Without a ledger this is a no-op, so plain CLI runs are unchanged.
        """
        try:
            from codewiki.mcp.tools import job_state

            job_state.set_phase(getattr(self.config, "repo_path", None), working_dir, phase)
        except Exception:
            logger.debug("job ledger phase update failed", exc_info=True)

    def _record_degraded(self, working_dir: str, stage: str, code: str, detail: str) -> None:
        """Record a non-fatal loss in an existing ledger (no-op without one)."""
        try:
            from codewiki.mcp.tools import job_state

            job_state.record_degraded(
                getattr(self.config, "repo_path", None),
                working_dir,
                stage=stage,
                code=code,
                detail=detail,
            )
        except Exception:
            logger.debug("job ledger degraded record failed", exc_info=True)

    def _mark_page_written(
        self, working_dir: str, filename: str, page_type: str = "module"
    ) -> None:
        """Mirror a page that is actually on disk into an existing ledger.

        The existence check matters: an agent run can return without writing
        anything, and marking that as written would hide a missing page from
        the resume view.
        """
        if not os.path.exists(os.path.join(working_dir, filename)):
            return
        try:
            from codewiki.mcp.tools import job_state

            job_state.mark_page_written(
                getattr(self.config, "repo_path", None),
                working_dir,
                filename,
                page_type=page_type,
            )
        except Exception:
            logger.debug("job ledger page mark failed", exc_info=True)

    def create_documentation_metadata(
        self, working_dir: str, components: Dict[str, Any], num_leaf_nodes: int
    ):
        """Create a metadata file with documentation generation information."""
        from datetime import datetime

        metadata = {
            "generation_info": {
                "timestamp": datetime.now().isoformat(),
                "main_model": self.config.main_model,
                "generator_version": "5.2.1",
                "repo_path": self.config.repo_path,
                "commit_id": self.commit_id,
            },
            "statistics": {
                "total_components": len(components),
                "leaf_nodes": num_leaf_nodes,
                "max_depth": self.config.max_depth,
            },
            "files_generated": [
                "overview.md",
                ".meta/module_tree.json",
                ".meta/first_module_tree.json",
            ],
        }

        # Add generated markdown files to the metadata
        try:
            for file_path in os.listdir(working_dir):
                if file_path.endswith(".md") and file_path not in metadata["files_generated"]:
                    metadata["files_generated"].append(file_path)
        except Exception as e:
            logger.warning(f"Could not list generated files: {e}")

        metadata_path = meta_join(working_dir, "metadata.json")
        file_manager.save_json(metadata, metadata_path)

    def get_processing_order(
        self, module_tree: Dict[str, Any], parent_path: List[str] = []
    ) -> List[tuple[List[str], str]]:
        """Get the processing order using topological sort (leaf modules first)."""
        processing_order = []

        def collect_modules(tree: Dict[str, Any], path: List[str]):
            for module_name, module_info in tree.items():
                current_path = path + [module_name]

                # If this module has children, process them first
                if (
                    module_info.get("children")
                    and isinstance(module_info["children"], dict)
                    and module_info["children"]
                ):
                    collect_modules(module_info["children"], current_path)
                    # Add this parent module after its children
                    processing_order.append((current_path, module_name))
                else:
                    # This is a leaf module, add it immediately
                    processing_order.append((current_path, module_name))

        collect_modules(module_tree, parent_path)
        return processing_order

    def is_leaf_module(self, module_info: Dict[str, Any]) -> bool:
        """Check if a module is a leaf module (has no children or empty children)."""
        children = module_info.get("children", {})
        return not children or (isinstance(children, dict) and len(children) == 0)

    def build_overview_structure(
        self, module_tree: Dict[str, Any], module_path: List[str], working_dir: str
    ) -> Dict[str, Any]:
        """Build structure for overview generation with 1-depth children docs and target indicator."""

        processed_module_tree = deepcopy(module_tree)
        module_info = processed_module_tree
        for path_part in module_path:
            module_info = module_info[path_part]
            if path_part != module_path[-1]:
                module_info = module_info.get("children", {})
            else:
                module_info["is_target_for_overview_generation"] = True

        if "children" in module_info:
            module_info = module_info["children"]

        for child_name, child_info in module_info.items():
            child_docs_path = self._resolve_child_docs_path(working_dir, child_name)
            if child_docs_path is not None:
                child_info["docs"] = file_manager.load_text(child_docs_path)
            else:
                logger.warning(
                    f"Module docs not found at {os.path.join(working_dir, f'{child_name}.md')}"
                )
                child_info["docs"] = ""

        return processed_module_tree

    @staticmethod
    def _resolve_child_docs_path(working_dir: str, child_name: str) -> str | None:
        """Resolve the on-disk path for a child module's .md doc.

        Sub-agents sometimes save files under a sanitized variant of the
        module name (spaces → underscores, lowercased, etc.) rather than the
        exact key in the module tree. Try a small set of common variants
        before giving up so the overview prompt still gets the children's
        content as context.
        """
        candidates = []
        seen = set()
        base_variants = [
            child_name,
            child_name.replace(" ", "_"),
            child_name.replace(" ", "-"),
            child_name.replace(" ", ""),
        ]
        for variant in base_variants:
            for cased in (variant, variant.lower()):
                if cased not in seen:
                    seen.add(cased)
                    candidates.append(f"{cased}.md")

        for filename in candidates:
            candidate_path = os.path.join(working_dir, filename)
            if os.path.exists(candidate_path):
                return candidate_path
        return None

    async def generate_module_documentation(
        self, components: Dict[str, Any], leaf_nodes: List[str]
    ) -> str:
        """Generate documentation for all modules using dynamic programming approach."""
        # Prepare output directory
        working_dir = os.path.abspath(self.config.docs_dir)
        file_manager.ensure_directory(working_dir)

        module_tree_path = meta_resolve(working_dir, MODULE_TREE_FILENAME)
        first_module_tree_path = meta_resolve(working_dir, FIRST_MODULE_TREE_FILENAME)
        module_tree = file_manager.load_json(module_tree_path)
        first_module_tree = file_manager.load_json(first_module_tree_path)

        # Get processing order (leaf modules first)
        processing_order = self.get_processing_order(first_module_tree)

        # Process modules in dependency order
        final_module_tree = module_tree
        processed_modules = set()
        failures: List[tuple[str, str]] = []

        if len(module_tree) > 0:
            self._ledger_phase(working_dir, "generating")
            for module_path, module_name in processing_order:
                module_key = "/".join(module_path)
                try:
                    # Reload module tree to get latest hierarchical structure from sub-agent modifications
                    module_tree = file_manager.load_json(module_tree_path)

                    # Get the module info from the tree
                    module_info = module_tree
                    for path_part in module_path:
                        module_info = module_info[path_part]
                        if path_part != module_path[-1]:  # Not the last part
                            module_info = module_info.get("children", {})

                    # Skip if already processed
                    if module_key in processed_modules:
                        continue

                    # Process the module
                    if self.is_leaf_module(module_info):
                        logger.info(f"📄 Processing leaf module: {module_key}")
                        final_module_tree = await self.backend.run_module_agent(
                            module_name=module_name,
                            components=components,
                            core_component_ids=module_info["components"],
                            module_path=module_path,
                            working_dir=working_dir,
                        )
                    else:
                        logger.info(f"📁 Processing parent module: {module_key}")
                        final_module_tree = await self.generate_parent_module_docs(
                            module_path, working_dir
                        )

                    self._mark_page_written(working_dir, f"{module_name}.md")
                    processed_modules.add(module_key)

                except Exception as e:
                    # Keep going so one broken module cannot block the rest, but
                    # do not pretend the run succeeded (ADR-0020 decision 2).
                    logger.error(f"Failed to process module {module_key}: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    failures.append((module_key, str(e)))
                    self._record_degraded(
                        working_dir, "module", "module_failed", f"{module_key}: {e}"
                    )

            # Generate repo overview
            logger.info("📚 Generating repository overview")
            try:
                final_module_tree = await self.generate_parent_module_docs([], working_dir)
                self._mark_page_written(working_dir, OVERVIEW_FILENAME, page_type="overview")
            except Exception as e:
                logger.error(f"Failed to generate repository overview: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                failures.append(("overview", str(e)))
                self._record_degraded(working_dir, "overview", "overview_failed", str(e))
        else:
            logger.info("Processing whole repo because repo can fit in the context window")
            repo_name = os.path.basename(os.path.normpath(self.config.repo_path))
            self._ledger_phase(working_dir, "generating")
            try:
                final_module_tree = await self.backend.run_module_agent(
                    module_name=repo_name,
                    components=components,
                    core_component_ids=leaf_nodes,
                    module_path=[],
                    working_dir=working_dir,
                )
            except Exception as e:
                logger.error(f"Failed to process the whole repo: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                failures.append((repo_name, str(e)))
                self._record_degraded(working_dir, "module", "module_failed", f"{repo_name}: {e}")
            else:
                # save final_module_tree to module_tree.json
                file_manager.save_json(
                    final_module_tree, meta_join(working_dir, MODULE_TREE_FILENAME)
                )

                # rename repo_name.md to overview.md
                repo_overview_path = os.path.join(working_dir, f"{repo_name}.md")
                if os.path.exists(repo_overview_path):
                    os.rename(repo_overview_path, os.path.join(working_dir, OVERVIEW_FILENAME))
                self._mark_page_written(working_dir, OVERVIEW_FILENAME, page_type="overview")

        if failures:
            self._ledger_phase(working_dir, "degraded")
            raise ModuleGenerationError(failures)

        return working_dir

    async def generate_parent_module_docs(
        self, module_path: List[str], working_dir: str
    ) -> Dict[str, Any]:
        """Generate documentation for a parent module based on its children's documentation."""
        module_name = (
            module_path[-1]
            if len(module_path) >= 1
            else os.path.basename(os.path.normpath(self.config.repo_path))
        )

        logger.info(f"Generating parent documentation for: {module_name}")

        # Load module tree
        module_tree_path = meta_resolve(working_dir, MODULE_TREE_FILENAME)
        module_tree = file_manager.load_json(module_tree_path)

        # Page-level skip only (ADR-0020 decision 2). ``overview.md`` used to
        # short-circuit every parent module here; it now only gates its own
        # page via the ``parent_docs_path`` check below.
        # check if parent docs already exists
        parent_docs_path = os.path.join(
            working_dir,
            f"{module_name if len(module_path) >= 1 else OVERVIEW_FILENAME.replace('.md', '')}.md",
        )
        if os.path.exists(parent_docs_path):
            logger.info(f"✓ Parent docs already exists at {parent_docs_path}")
            return module_tree

        # Create repo structure with 1-depth children docs and target indicator
        repo_structure = self.build_overview_structure(module_tree, module_path, working_dir)

        custom_section = ""
        if self.config and self.config.agent_instructions:
            addition = self.config.get_prompt_addition()
            if addition:
                custom_section = f"\n<CUSTOM_INSTRUCTIONS>\n{addition}\n</CUSTOM_INSTRUCTIONS>"

        prompt = (
            MODULE_OVERVIEW_PROMPT.format(
                module_name=module_name,
                repo_structure=json.dumps(repo_structure, indent=4),
                custom_instructions=custom_section,
            )
            if len(module_path) >= 1
            else REPO_OVERVIEW_PROMPT.format(
                repo_name=module_name,
                repo_structure=json.dumps(repo_structure, indent=4),
                custom_instructions=custom_section,
            )
        )

        try:
            parent_docs = self.backend.complete(prompt)

            # Parse and save parent documentation. Subscription-CLI backends
            # (claude-code / codex) sometimes ignore the <OVERVIEW> wrapper and
            # return raw markdown; fall back to the response as-is in that case
            # rather than crashing with an index error.
            if "<OVERVIEW>" in parent_docs and "</OVERVIEW>" in parent_docs:
                parent_content = parent_docs.split("<OVERVIEW>")[1].split("</OVERVIEW>")[0].strip()
            else:
                logger.warning(
                    f"Overview response for {module_name} missing <OVERVIEW> wrapper; "
                    f"using raw response as markdown."
                )
                parent_content = parent_docs.strip()
            file_manager.save_text(parent_content, parent_docs_path)

            logger.debug(f"Successfully generated parent documentation for: {module_name}")
            return module_tree

        except Exception as e:
            logger.error(f"Error generating parent documentation for {module_name}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def run(self) -> None:
        """Run the complete documentation generation process using dynamic programming."""
        try:
            # Build dependency graph
            components, leaf_nodes, _routes = self.graph_builder.build_dependency_graph()

            logger.debug(f"Found {len(leaf_nodes)} leaf nodes")
            # logger.debug(f"Leaf nodes:\n{'\n'.join(sorted(leaf_nodes)[:200])}")
            # exit()

            # Cluster modules
            working_dir = os.path.abspath(self.config.docs_dir)
            file_manager.ensure_directory(working_dir)
            first_module_tree_path = meta_resolve(working_dir, FIRST_MODULE_TREE_FILENAME)
            module_tree_path = meta_resolve(working_dir, MODULE_TREE_FILENAME)

            # Reuse the cached tree only while it still covers every leaf node.
            # A new top-level module would otherwise never enter the tree and
            # never get a page (ADR-0020 decision 3).
            module_tree = None
            if os.path.exists(first_module_tree_path):
                cached = file_manager.load_json(first_module_tree_path)
                gap = module_tree_coverage_gap(cached, leaf_nodes)
                if gap:
                    logger.info(
                        "Cached module tree misses %d component(s); re-clustering "
                        "(e.g. %s)",
                        len(gap),
                        ", ".join(gap[:3]),
                    )
                    module_tree = None
                else:
                    logger.debug(f"Module tree found at {first_module_tree_path}")
                    module_tree = cached

            if module_tree is None:
                logger.debug(f"Module tree not found at {module_tree_path}, clustering modules")
                clustering_tokens = get_clustering_input_token_count(leaf_nodes, components)
                logger.info(
                    "Preparing %d leaf nodes for module clustering (%d tokens, threshold %d)",
                    len(leaf_nodes),
                    clustering_tokens,
                    self.config.max_token_per_module,
                )
                # Bind cluster_model into the completer so the backend uses the
                # configured clustering model (separate from main_model) when
                # one is set.  Caw mode's cluster_model is typically empty —
                # complete() falls back to its own _model in that case.
                cluster_model = self.config.cluster_model or None
                module_tree = cluster_modules(
                    leaf_nodes,
                    components,
                    self.config,
                    completer=lambda p: self.backend.complete(p, model=cluster_model),
                )
                file_manager.save_json(module_tree, first_module_tree_path)

            file_manager.save_json(module_tree, module_tree_path)

            if len(module_tree) == 0:
                logger.info(
                    "Module clustering produced no top-level modules; continuing in "
                    "whole-repository documentation mode"
                )
            else:
                logger.info(
                    "Grouped components into %d top-level modules",
                    len(module_tree),
                )

            # Generate module documentation using dynamic programming approach
            # This processes leaf modules first, then parent modules.
            # Metadata is written even when the run degrades: pages that did land
            # must stay inspectable, and the exception still propagates.
            try:
                await self.generate_module_documentation(components, leaf_nodes)
            finally:
                self.create_documentation_metadata(working_dir, components, len(leaf_nodes))

            logger.debug(
                "Documentation generation completed successfully using dynamic programming!"
            )
            logger.debug("Processing order: leaf modules → parent modules → repository overview")
            logger.debug(f"Documentation saved to: {working_dir}")

        except Exception as e:
            logger.error(f"Documentation generation failed: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
