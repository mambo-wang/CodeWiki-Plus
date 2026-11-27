"""
Call Graph Analyzer

Central orchestrator for multi-language call graph analysis.
Coordinates language-specific analyzers to build comprehensive call graphs
across different programming languages in a repository.
"""

from typing import TYPE_CHECKING, Dict, List, Optional, Set
import logging
import os
import traceback
import time
import signal
import threading
import re
from collections import defaultdict
from pathlib import Path
from contextlib import contextmanager
from codewiki.src.be.dependency_analyzer.models.core import Node, CallRelationship
from codewiki.src.be.dependency_analyzer.models.cross_service import RouteNode
from codewiki.src.be.dependency_analyzer.analyzers.ruby import RUBY_IMPLICIT_PREFIX
from codewiki.src.be.dependency_analyzer.analyzers.route_extractors import get_extractor
from codewiki.src.be.dependency_analyzer.analyzers.route_extractors.mq_patterns import (
    extract_mq_routes,
)
from codewiki.src.be.dependency_analyzer.utils.patterns import CODE_EXTENSIONS
from codewiki.src.be.dependency_analyzer.utils.security import safe_open_text, is_likely_minified
from codewiki.src.be.dependency_analyzer.utils.external_symbols import (
    CPP_STANDARD_HEADERS,
    is_external_symbol,
    is_macro_name,
)
from codewiki.src.be.dependency_analyzer.utils.grammars import ensure_grammars

if TYPE_CHECKING:
    from codewiki.src.be.dependency_analyzer.analyzers.lean_resolution import LeanNameResolver

logger = logging.getLogger(__name__)


class TimeoutError(BaseException):
    """必须绕过语言分析器内部的 Exception 捕获，由分派层统一处理。"""

    pass


@contextmanager
def timeout(seconds):
    """Context manager for timeout on file parsing.

    Uses SIGALRM, which is only available on the MAIN thread of a Unix
    process.  When running elsewhere (Windows, or a worker thread such as
    the MCP registry's mode="thread" dispatch via asyncio.to_thread),
    signal.signal() raises ValueError, so we skip the timeout protection
    and parse without it instead of failing every file.
    """

    def signal_handler(signum, frame):
        raise TimeoutError(f"File parsing exceeded {seconds}s timeout")

    use_signal = (
        hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread()
    )
    if not use_signal:
        # Windows / non-main thread: SIGALRM unavailable, skip timeout
        yield
        return

    old_handler = signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


class CallGraphAnalyzer:
    def __init__(self):
        """Initialize the call graph analyzer."""
        self.functions: Dict[str, Node] = {}
        self.call_relationships: List[CallRelationship] = []
        self.routes: List[RouteNode] = []
        self._repo_name: str = ""
        self._python_project_modules: set = set()
        self._python_external_import_roots: set = set()
        self._rust_impls: list[tuple[str, str, int]] = []
        self._go_visible: dict[str, set[str]] = {}
        self._go_index = None
        self._scala_index = None
        self._dart_index = None
        self._dart_cached_edges: list[tuple[str, str]] = []
        self._parsed_files: set[str] = set()
        self._reset_lean_state()
        logger.debug("CallGraphAnalyzer initialized.")

    def analyze_code_files(
        self,
        code_files: List[Dict],
        base_dir: str,
        skip_file_paths: Optional[Set[str]] = None,
        cached_components: Optional[Dict[str, Node]] = None,
    ) -> Dict:
        """
        Complete analysis: Analyze all files to build complete call graph with all nodes.

        This approach:
        1. Analyzes all code files
        2. Extracts all functions and relationships
        3. Builds complete call graph
        4. Returns all nodes and relationships

        Args:
            code_files: List of code file info dicts
            base_dir: Base directory of the repository
            skip_file_paths: Optional set of absolute file paths to skip (for incremental mode)
            cached_components: Unchanged components from SQLite. Go, Scala and Dart nodes are
                merged before package/scope resolution so changed files can call cached symbols.
        """
        # Dart visible scope 需要未变更文件的 import/export/part 指令；
        # 在增量过滤前保留完整文件清单。
        self._parsed_files = set()
        dart_files = [
            file_info["path"] for file_info in code_files if file_info.get("language") == "dart"
        ]
        if skip_file_paths and cached_components:
            # 旧缓存没有原始引用语义，不能凭目标名复核；让这些 Dart 文件
            # 在首次升级后重解析一次，后续缓存即可安全增量。
            stale_dart_paths = set()
            for node in cached_components.values():
                if (
                    node.language == "dart" or Path(node.file_path).suffix.lower() == ".dart"
                ) and "dart_raw_dependencies" not in node.metadata:
                    stale_dart_paths.add(node.file_path)
                    try:
                        stale_dart_paths.add(
                            Path(os.path.relpath(node.file_path, base_dir)).as_posix()
                        )
                    except (TypeError, ValueError):
                        pass
            if stale_dart_paths:
                skip_file_paths = set(skip_file_paths) - stale_dart_paths
        if skip_file_paths:
            original_count = len(code_files)
            skipped_paths = set(skip_file_paths)
            for skipped in skip_file_paths:
                try:
                    skipped_paths.add(Path(os.path.relpath(skipped, base_dir)).as_posix())
                except (TypeError, ValueError):
                    pass
            # Zig 与 Lean 的文件级 import/open/export 会改变其他 caller 的
            # 可见域；任一文件变化都全量重解析该语言，而非只解析差量。
            skipped_paths = {
                p for p in skipped_paths if Path(p).suffix.lower() not in {".zig", ".lean"}
            }
            code_files = [
                file_info for file_info in code_files if file_info.get("path") not in skipped_paths
            ]
            logger.info(
                f"Incremental mode: skipping {original_count - len(code_files)} unchanged files, "
                f"parsing {len(code_files)} changed files"
            )

        logger.debug(f"Starting analysis of {len(code_files)} files")
        logger.info(f"📊 Parsing {len(code_files)} source files (this may take a few minutes)...")

        self.functions = {}
        self.call_relationships = []
        self.routes = []
        self._rust_impls = []
        self._go_visible = {}
        self._go_index = None
        self._scala_index = None
        self._dart_index = None
        self._dart_cached_edges = []
        self._reset_lean_state()
        self._repo_name = Path(base_dir).name
        code_files = self._route_contextual_headers(code_files, base_dir)
        # 在逐文件解析前验证 grammar；下载/ABI 失败不能退化成零节点。
        ensure_grammars(f["language"] for f in code_files)
        self._python_project_modules = self._collect_python_modules(code_files)
        self._python_external_import_roots = set()

        files_analyzed = 0
        files_failed = 0
        start_time = time.time()

        for idx, file_info in enumerate(code_files, 1):
            file_path = file_info["path"]
            self._parsed_files.add(file_path)
            try:
                # Log progress every file with elapsed time
                if idx % max(1, len(code_files) // 10) == 0 or idx <= 5:
                    elapsed = time.time() - start_time
                    rate = idx / elapsed if elapsed > 0 else 0
                    remaining = (len(code_files) - idx) / rate if rate > 0 else 0
                    logger.info(
                        f"  [{idx}/{len(code_files)}] {file_path} ({elapsed:.1f}s elapsed, ~{remaining:.1f}s remaining)"
                    )

                self._analyze_code_file(base_dir, file_info)
                files_analyzed += 1
            except Exception as e:
                # Lean 的 import/open/export 需要完整文件态；半份结果回填缓存
                # 会静默产生错误可见域。grammar/parser/scanner 故障必须显式失败。
                if file_info.get("language") == "lean":
                    raise
                files_failed += 1
                logger.warning(
                    f"  ⚠️  [{idx}/{len(code_files)}] Failed to analyze {file_path}: {str(e)[:100]}"
                )

        elapsed_time = time.time() - start_time
        logger.info(
            f"✓ Analysis complete: {files_analyzed}/{len(code_files)} files analyzed, "
            f"{files_failed} failed, {len(self.functions)} functions, {len(self.call_relationships)} relationships, "
            f"{len(self.routes)} routes ({elapsed_time:.1f}s)"
        )

        logger.debug("Resolving call relationships")
        self._merge_cached_go_components(cached_components)
        self._merge_cached_scala_components(cached_components)
        self._merge_cached_dart_components(cached_components)
        self._merge_cached_vue_components(cached_components, base_dir)
        self._merge_cached_zig_components(cached_components, base_dir)
        self._merge_cached_lean_components(cached_components, base_dir)
        self._rebuild_dart_scope(base_dir, dart_files)
        self._resolve_rust_impl_bases()
        if any(func.language == "go" for func in self.functions.values()):
            from codewiki.src.be.dependency_analyzer.analyzers.go_package import (
                link_go_interfaces,
            )

            self.call_relationships.extend(link_go_interfaces(self.functions))
        self._resolve_call_relationships()
        self._deduplicate_relationships()
        viz_data = self._generate_visualization_data()

        return {
            "call_graph": {
                "total_functions": len(self.functions),
                "total_calls": len(self.call_relationships),
                "languages_found": list(set(f.get("language") for f in code_files)),
                "files_analyzed": files_analyzed,
                "analysis_approach": "complete_unlimited",
            },
            "functions": [func.model_dump() for func in self.functions.values()],
            "relationships": [rel.model_dump() for rel in self.call_relationships],
            "visualization": viz_data,
            "routes": [r.model_dump() for r in self.routes],
        }

    def extract_code_files(self, file_tree: Dict) -> List[Dict]:
        """
        Extract code files from file tree structure.

        Filters files based on supported extensions and excludes test/config files.

        Args:
            file_tree: Nested dictionary representing file structure

        Returns:
            List of code file information dictionaries
        """
        code_files = []

        def traverse(tree):
            if tree["type"] == "file":
                ext = tree.get("extension", "").lower()
                if ext in CODE_EXTENSIONS:
                    name = tree["name"].lower()
                    if not any(skip in name for skip in []):
                        code_files.append(
                            {
                                "path": tree["path"],
                                "name": tree["name"],
                                "extension": ext,
                                "language": CODE_EXTENSIONS[ext],
                            }
                        )
            elif tree["type"] == "directory" and tree.get("children"):
                for child in tree["children"]:
                    traverse(child)

        traverse(file_tree)
        return code_files

    def _route_contextual_headers(self, code_files: List[Dict], base_dir: str) -> List[Dict]:
        """Route ambiguous .h headers per file.

        A header is parsed as C++ when its own content shows C++ signals, or
        when the repository is C++-only (so even a signal-free header cannot be
        C). In a mixed C/C++ repository, a plain C header stays routed as C.
        """
        cpp_extensions = {".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hxx", ".h++"}
        has_cpp_files = any(
            file_info.get("extension", "").lower() in cpp_extensions
            or file_info.get("language") == "cpp"
            for file_info in code_files
        )
        has_c_files = any(
            file_info.get("extension", "").lower() == ".c" for file_info in code_files
        )

        routed_files = []
        for file_info in code_files:
            routed = dict(file_info)
            if routed.get("extension", "").lower() == ".h":
                if self._header_has_cpp_signal(base_dir, routed["path"]):
                    routed["language"] = "cpp"
                elif has_cpp_files and not has_c_files:
                    routed["language"] = "cpp"
            routed_files.append(routed)
        return routed_files

    def _header_has_cpp_signal(self, base_dir: str, relative_path: str) -> bool:
        base = Path(base_dir)
        try:
            content = safe_open_text(base, base / relative_path)
        except Exception:
            return False

        if re.search(
            r"\b(?:namespace\s+[A-Za-z_{:]|class\s+[A-Za-z_]|template\s*<"
            r"|typename\b|(?:public|private|protected)\s*:)",
            content,
        ):
            return True
        if "::" in content:
            return True
        for header in CPP_STANDARD_HEADERS:
            if f"#include <{header}>" in content:
                return True
        return False

    def _analyze_code_file(self, repo_dir: str, file_info: Dict):
        """
        Analyze a single code file based on its language.

        Routes to appropriate language-specific analyzer.

        Args:
            repo_dir: Repository directory path
            file_info: File information dictionary
        """

        base = Path(repo_dir)
        file_path = base / file_info["path"]

        try:
            # Add timeout protection (30 seconds per file max)
            with timeout(30):
                content = safe_open_text(base, file_path)

                # Skip minified/bundled files that pass the size guard
                if is_likely_minified(content):
                    logger.debug(f"Skipping minified/bundled file: {file_path}")
                    return

                language = file_info["language"]
                if language == "python":
                    self._analyze_python_file(file_path, content, repo_dir)
                elif language == "javascript":
                    self._analyze_javascript_file(file_path, content, repo_dir)
                elif language == "typescript":
                    self._analyze_typescript_file(file_path, content, repo_dir)
                elif language == "java":
                    self._analyze_java_file(file_path, content, repo_dir)
                elif language == "kotlin":
                    self._analyze_kotlin_file(file_path, content, repo_dir)
                elif language == "csharp":
                    self._analyze_csharp_file(file_path, content, repo_dir)
                elif language == "c":
                    self._analyze_c_file(file_path, content, repo_dir)
                elif language == "cpp":
                    self._analyze_cpp_file(file_path, content, repo_dir)
                elif language == "php":
                    self._analyze_php_file(file_path, content, repo_dir)
                elif language == "go":
                    self._analyze_go_file(file_path, content, repo_dir)
                elif language == "scala":
                    self._analyze_scala_file(file_path, content, repo_dir)
                elif language == "dart":
                    self._analyze_dart_file(file_path, content, repo_dir)
                elif language == "zig":
                    self._analyze_zig_file(file_path, content, repo_dir)
                elif language == "lean":
                    self._analyze_lean_file(file_path, content, repo_dir)
                elif language == "rust":
                    self._analyze_rust_file(file_path, content, repo_dir)
                elif language == "ruby":
                    self._analyze_ruby_file(file_path, content, repo_dir)
                elif language == "vue":
                    self._analyze_vue_file(file_path, content, repo_dir)
                # else:
                #     logger.warning(
                #         f"Unsupported language for call graph analysis: {language} for file {file_path}"
                #     )

                # Post-pass: extract HTTP/MQ routes for cross-service analysis
                self._extract_routes(str(file_path), content, language)

        except TimeoutError as e:
            logger.warning(f"⏱️  Timeout analyzing {file_path}: {str(e)}")
        except Exception as e:
            if file_info.get("language") == "lean":
                raise
            logger.debug(f"Error analyzing {file_path}: {str(e)}")
            logger.debug(f"Traceback: {traceback.format_exc()}")

    def _analyze_python_file(self, file_path: str, content: str, base_dir: str):
        """
        Analyze Python file using Python AST analyzer.

        Args:
            file_path: Relative path to the Python file
            content: File content string
            base_dir: Repository base directory path
        """
        from codewiki.src.be.dependency_analyzer.analyzers.python import analyze_python_file

        try:
            functions, relationships, external_import_roots = analyze_python_file(
                file_path,
                content,
                repo_path=base_dir,
                project_modules=self._python_project_modules,
            )

            for func in functions:
                func_id = func.id if func.id else f"{file_path}:{func.name}"
                self.functions[func_id] = func

            self.call_relationships.extend(relationships)
            self._python_external_import_roots.update(external_import_roots)
        except Exception as e:
            logger.error(f"Failed to analyze Python file {file_path}: {e}", exc_info=True)

    @staticmethod
    def _collect_python_modules(code_files: List[Dict]) -> set:
        """Dotted module paths for every Python file in the repository."""
        modules = set()
        for file_info in code_files:
            if file_info.get("language") != "python":
                continue
            path = file_info["path"]
            for ext in (".py", ".pyx"):
                if path.endswith(ext):
                    path = path[: -len(ext)]
                    break
            module = path.replace("/", ".").replace("\\", ".")
            if module.endswith(".__init__"):
                module = module[: -len(".__init__")]
            if module:
                modules.add(module)
        return modules

    def _analyze_javascript_file(self, file_path: str, content: str, repo_dir: str):
        """
        Analyze JavaScript file using tree-sitter based AST analyzer

        Args:
            file_path: Relative path to the JavaScript file
            content: File content string
            repo_dir: Repository base directory
        """
        try:
            from codewiki.src.be.dependency_analyzer.analyzers.javascript import (
                analyze_javascript_file_treesitter,
            )

            functions, relationships = analyze_javascript_file_treesitter(
                file_path, content, repo_path=repo_dir
            )

            for func in functions:
                func_id = func.id if func.id else f"{file_path}:{func.name}"
                self.functions[func_id] = func

            self.call_relationships.extend(relationships)

        except Exception as e:
            logger.error(f"Failed to analyze JavaScript file {file_path}: {e}", exc_info=True)

    def _analyze_typescript_file(self, file_path: str, content: str, repo_dir: str):
        """
        Analyze TypeScript file using tree-sitter based AST analyzer

        Args:
            file_path: Relative path to the TypeScript file
            content: File content string
        """
        try:
            from codewiki.src.be.dependency_analyzer.analyzers.typescript import (
                analyze_typescript_file_treesitter,
            )

            functions, relationships = analyze_typescript_file_treesitter(
                file_path, content, repo_path=repo_dir
            )

            for func in functions:
                func_id = func.id if func.id else f"{file_path}:{func.name}"
                self.functions[func_id] = func

            self.call_relationships.extend(relationships)

        except Exception as e:
            logger.error(f"Failed to analyze TypeScript file {file_path}: {e}", exc_info=True)

    def _analyze_c_file(self, file_path: str, content: str, repo_dir: str):
        """
        Analyze C file using tree-sitter based analyzer.

        Args:
            file_path: Relative path to the C file
            content: File content string
            repo_dir: Repository base directory
        """
        from codewiki.src.be.dependency_analyzer.analyzers.c import analyze_c_file

        functions, relationships = analyze_c_file(file_path, content, repo_path=repo_dir)

        for func in functions:
            func_id = func.id if func.id else f"{file_path}:{func.name}"
            self.functions[func_id] = func

        self.call_relationships.extend(relationships)

    def _analyze_cpp_file(self, file_path: str, content: str, repo_dir: str):
        """
        Analyze C++ file using tree-sitter based analyzer.

        Args:
            file_path: Relative path to the C++ file
            content: File content string
        """
        from codewiki.src.be.dependency_analyzer.analyzers.cpp import analyze_cpp_file

        functions, relationships = analyze_cpp_file(file_path, content, repo_path=repo_dir)

        for func in functions:
            func_id = func.id if func.id else f"{file_path}:{func.name}"
            self.functions[func_id] = func

        self.call_relationships.extend(relationships)

    def _analyze_java_file(self, file_path: str, content: str, repo_dir: str):
        """
        Analyze Java file using tree-sitter based analyzer.

        Args:
            file_path: Relative path to the Java file
            content: File content string
            repo_dir: Repository base directory
        """
        from codewiki.src.be.dependency_analyzer.analyzers.java import analyze_java_file

        try:
            functions, relationships = analyze_java_file(file_path, content, repo_path=repo_dir)
            for func in functions:
                func_id = func.id if func.id else f"{file_path}:{func.name}"
                self.functions[func_id] = func

            self.call_relationships.extend(relationships)
        except Exception as e:
            logger.error(f"Failed to analyze Java file {file_path}: {e}", exc_info=True)

    def _analyze_kotlin_file(self, file_path: str, content: str, repo_dir: str):
        """
        Analyze Kotlin file using tree-sitter based analyzer.

        Args:
            file_path: Relative path to the Kotlin file
            content: File content string
            repo_dir: Repository base directory
        """
        from codewiki.src.be.dependency_analyzer.analyzers.kotlin import analyze_kotlin_file

        try:
            functions, relationships = analyze_kotlin_file(file_path, content, repo_path=repo_dir)
            for func in functions:
                func_id = func.id if func.id else f"{file_path}:{func.name}"
                self.functions[func_id] = func

            self.call_relationships.extend(relationships)
        except Exception as e:
            logger.error(f"Failed to analyze Kotlin file {file_path}: {e}", exc_info=True)

    def _analyze_csharp_file(self, file_path: str, content: str, repo_dir: str):
        """
        Analyze C# file using tree-sitter based analyzer.

        Args:
            file_path: Relative path to the C# file
            content: File content string
            repo_dir: Repository base directory
        """
        from codewiki.src.be.dependency_analyzer.analyzers.csharp import analyze_csharp_file

        try:
            functions, relationships = analyze_csharp_file(file_path, content, repo_path=repo_dir)

            for func in functions:
                func_id = func.id if func.id else f"{file_path}:{func.name}"
                self.functions[func_id] = func

            self.call_relationships.extend(relationships)
        except Exception as e:
            logger.error(f"Failed to analyze C# file {file_path}: {e}", exc_info=True)

    def _analyze_php_file(self, file_path: str, content: str, repo_dir: str):
        """
        Analyze PHP file using tree-sitter based analyzer.

        Args:
            file_path: Relative path to the PHP file
            content: File content string
            repo_dir: Repository base directory
        """
        from codewiki.src.be.dependency_analyzer.analyzers.php import analyze_php_file

        try:
            functions, relationships = analyze_php_file(file_path, content, repo_path=repo_dir)

            for func in functions:
                func_id = func.id if func.id else f"{file_path}:{func.name}"
                self.functions[func_id] = func

            self.call_relationships.extend(relationships)
        except Exception as e:
            logger.error(f"Failed to analyze PHP file {file_path}: {e}", exc_info=True)

    def _analyze_go_file(self, file_path: str, content: str, repo_dir: str):
        """
        Analyze Go file using tree-sitter based analyzer.

        Args:
            file_path: Relative path to the Go file
            content: File content string
            repo_dir: Repository base directory
        """
        from codewiki.src.be.dependency_analyzer.analyzers.go import TreeSitterGoAnalyzer

        analyzer = TreeSitterGoAnalyzer(str(file_path), content, repo_path=repo_dir)
        for func in analyzer.nodes:
            func_id = func.id if func.id else f"{file_path}:{func.name}"
            self.functions[func_id] = func
        self.call_relationships.extend(analyzer.call_relationships)
        self._go_visible[analyzer.relative_path] = analyzer.visible_dirs

    def _resolve_go_callee(self, callee: str, caller: Node) -> Optional[str]:
        """Go 名称只在它指向的 directory/package 内解析，不按尾名跨包猜测。"""
        from codewiki.src.be.dependency_analyzer.analyzers.go_package import (
            GoPackageIndex,
            resolve_go_callee,
        )

        if self._go_index is None:
            self._go_index = GoPackageIndex(self.functions)
        return resolve_go_callee(
            callee,
            caller,
            self._go_index,
            self._go_visible.get(Path(caller.relative_path).as_posix()),
        )

    def _analyze_scala_file(self, file_path: str, content: str, repo_dir: str):
        """分析 Scala 源码；跨文件引用留在 package-scoped 解析阶段。"""
        from codewiki.src.be.dependency_analyzer.analyzers.scala import analyze_scala_file

        functions, relationships = analyze_scala_file(file_path, content, repo_path=repo_dir)
        for func in functions:
            func_id = func.id if func.id else f"{file_path}:{func.name}"
            self.functions[func_id] = func
        self.call_relationships.extend(relationships)

    def _resolve_scala_callee(self, callee: str, caller: Node) -> Optional[str]:
        """Scala 引用只在声明的 package 内精确解析，不按尾名猜绑定。"""
        from codewiki.src.be.dependency_analyzer.analyzers.scala import (
            ScalaPackageIndex,
            resolve_scala_callee,
        )

        if self._scala_index is None:
            self._scala_index = ScalaPackageIndex(self.functions)
        return resolve_scala_callee(callee, caller, self._scala_index)

    def _analyze_dart_file(self, file_path: str, content: str, repo_dir: str):
        """分析 Dart 源码；跨 library 引用留在 visible-scope 解析阶段。"""
        from codewiki.src.be.dependency_analyzer.analyzers.dart import analyze_dart_file

        functions, relationships = analyze_dart_file(file_path, content, repo_path=repo_dir)
        for func in functions:
            func_id = func.id if func.id else f"{file_path}:{func.name}"
            self.functions[func_id] = func
        self.call_relationships.extend(relationships)

    def _resolve_dart_callee(self, callee: str, caller: Node) -> Optional[str]:
        from codewiki.src.be.dependency_analyzer.analyzers.dart_imports import resolve_dart_callee

        if self._dart_index is None:
            return None
        return resolve_dart_callee(callee, caller, self._dart_index)

    def _analyze_rust_file(self, file_path: str, content: str, repo_dir: str):
        """分析 Rust 源码并保留既有 component ID 与调用边契约。"""
        from codewiki.src.be.dependency_analyzer.analyzers.rust import analyze_rust_file

        functions, relationships = analyze_rust_file(
            file_path, content, repo_path=repo_dir, impl_bases=self._rust_impls
        )
        for func in functions:
            func_id = func.id if func.id else f"{file_path}:{func.name}"
            self.functions[func_id] = func
        self.call_relationships.extend(relationships)

    def _analyze_ruby_file(self, file_path: str, content: str, repo_dir: str):
        """分析 Ruby 源码，保留命名空间、实例/单例方法与接收者身份。"""
        from codewiki.src.be.dependency_analyzer.analyzers.ruby import analyze_ruby_file

        functions, relationships = analyze_ruby_file(
            file_path, content, repo_path=repo_dir, defer_implicit=True
        )
        for func in functions:
            func_id = func.id if func.id else f"{file_path}:{func.name}"
            self.functions[func_id] = func
        self.call_relationships.extend(relationships)

    def _analyze_zig_file(self, file_path: str, content: str, repo_dir: str):
        """Zig 的 import 闭包由 analyzer 直接解析为完整组件 ID。"""
        from codewiki.src.be.dependency_analyzer.analyzers.zig import analyze_zig_file

        functions, relationships = analyze_zig_file(file_path, content, repo_path=repo_dir)
        for func in functions:
            self.functions[func.id] = func
        self.call_relationships.extend(relationships)

    def _reset_lean_state(self) -> None:
        self._lean_files: dict = {}
        self._lean_scopes: dict = {}
        self._lean_aliases: dict[str, list[str]] = defaultdict(list)
        self._lean_private: set[str] = set()
        self._lean_protected: set[str] = set()
        self._lean_resolver: Optional["LeanNameResolver"] = None

    def _analyze_lean_file(self, file_path: str, content: str, repo_dir: str):
        """记录 Lean 文件级可见域与声明引用，供仓库级精确解析。"""
        from codewiki.src.be.dependency_analyzer.analyzers.lean import TreeSitterLeanAnalyzer

        analyzer = TreeSitterLeanAnalyzer(str(file_path), content, repo_path=repo_dir)
        for func in analyzer.nodes:
            self.functions[func.id] = func
        self.call_relationships.extend(analyzer.call_relationships)
        self._lean_files[analyzer.relative_path] = analyzer.scan
        self._lean_scopes.update(analyzer.scopes)
        for alias, node_id in analyzer.aliases.items():
            self._lean_aliases[alias].append(node_id)
        self._lean_private.update(analyzer.private_ids)
        self._lean_protected.update(analyzer.protected_ids)

    def _resolve_lean_callee(self, callee: str, caller: Node) -> Optional[str]:
        from codewiki.src.be.dependency_analyzer.analyzers.lean_resolution import LeanNameResolver

        if self._lean_resolver is None:
            self._lean_resolver = LeanNameResolver(
                self.functions,
                self._lean_files,
                self._lean_scopes,
                self._lean_aliases,
                self._lean_private,
                self._lean_protected,
            )
        resolved: Optional[str] = self._lean_resolver.resolve(callee, caller)
        return resolved

    def _merge_cached_lean_components(
        self, cached_components: Optional[Dict[str, Node]], repo_dir: str
    ) -> None:
        """非 Lean 增量复用缓存；只保留仍存在文件的组件与仍存在的目标。"""
        if not cached_components:
            return
        for component_id, cached in cached_components.items():
            if component_id in self.functions:
                continue
            if cached.language != "lean" and Path(cached.file_path).suffix.lower() != ".lean":
                continue
            file_path = Path(cached.file_path)
            if not file_path.is_absolute():
                file_path = Path(repo_dir) / file_path
            if not file_path.is_file():
                continue
            self.functions[component_id] = cached.model_copy(deep=True)
        live_ids = set(self.functions)
        for node in self.functions.values():
            if node.language != "lean":
                continue
            original_edges = set(node.depends_on or set())
            node.depends_on = set()
            for callee in sorted(original_edges):
                if callee in live_ids:
                    node.depends_on.add(callee)
                    self.call_relationships.append(
                        CallRelationship(caller=node.id, callee=callee, is_resolved=True)
                    )

    def _analyze_vue_file(self, file_path: str, content: str, repo_dir: str):
        """分析 Vue SFC，保留组件、脚本函数与模板引用的原始身份。"""
        from codewiki.src.be.dependency_analyzer.analyzers.vue import analyze_vue_file

        functions, relationships = analyze_vue_file(file_path, content, repo_path=repo_dir)
        for func in functions:
            func_id = func.id if func.id else f"{file_path}:{func.name}"
            self.functions[func_id] = func
        self.call_relationships.extend(relationships)

    def _merge_cached_go_components(self, cached_components: Optional[Dict[str, Node]]) -> None:
        """让增量解析的变更文件仍能解析到未变更的 Go package。"""
        if not cached_components:
            return
        for component_id, node in cached_components.items():
            if component_id in self.functions:
                continue
            if node.language != "go" and Path(node.file_path).suffix.lower() != ".go":
                continue
            if node.language == "go" and node.node_type in ("struct", "type"):
                # Implicit interface links are recomputed after all changed and
                # cached declarations are visible; cached links may be stale.
                node.base_classes = []
            self.functions[component_id] = node
            for callee in sorted(node.depends_on or set()):
                target = cached_components.get(callee)
                if (
                    node.language == "go"
                    and node.node_type in ("struct", "type")
                    and target is not None
                    and target.language == "go"
                    and target.node_type == "interface"
                ):
                    continue
                self.call_relationships.append(
                    CallRelationship(
                        caller=component_id,
                        callee=callee,
                        is_resolved=True,
                    )
                )

    def _merge_cached_scala_components(self, cached_components: Optional[Dict[str, Node]]) -> None:
        """让增量解析的变更文件仍能解析到未变更的 Scala package。

        缓存只保留已解析 ID，不保留 caller 的 import。新增声明可能使旧
        wildcard 解析变歧义时丢弃旧边；无关新增仍保留精确的旧边。
        """
        from codewiki.src.be.dependency_analyzer.analyzers.scala import scala_node_identity

        if not cached_components:
            return
        reparsed_ids = set(self.functions)
        reparsed_names = {
            scala_node_identity(node)[1]
            for node in self.functions.values()
            if node.language == "scala"
        }
        for component_id, node in cached_components.items():
            if component_id in self.functions:
                continue
            if node.language != "scala" and Path(node.file_path).suffix.lower() not in {
                ".scala",
                ".sc",
            }:
                continue
            self.functions[component_id] = node
            cached_edges = set(node.depends_on or set())
            node.depends_on = set()
            for callee in sorted(cached_edges):
                target = cached_components.get(callee)
                if target is None or target.language != "scala" or callee in reparsed_ids:
                    continue
                _, target_name = scala_node_identity(target)
                if target_name in reparsed_names:
                    continue
                node.depends_on.add(callee)
                self.call_relationships.append(
                    CallRelationship(
                        caller=component_id,
                        callee=callee,
                        is_resolved=True,
                    )
                )

    def _merge_cached_dart_components(self, cached_components: Optional[Dict[str, Node]]) -> None:
        """合并未变更 Dart 组件；旧边在重建 visible scope 后重新裁决。"""
        if not cached_components:
            return
        self._dart_cached_edges = []
        for component_id, node in cached_components.items():
            if component_id in self.functions:
                continue
            if node.language != "dart" and Path(node.file_path).suffix.lower() != ".dart":
                continue
            self.functions[component_id] = node
            self._dart_cached_edges.extend(
                (component_id, callee) for callee in sorted(node.depends_on or set())
            )
            node.depends_on = set()

    def _merge_cached_vue_components(
        self, cached_components: Optional[Dict[str, Node]], repo_dir: str
    ) -> None:
        """复用未变更 Vue 组件，并删除指向已消失 JS/TS/Vue 导出的旧边。"""
        if not cached_components:
            return
        for component_id, cached in cached_components.items():
            if component_id in self.functions:
                continue
            if cached.language != "vue" and Path(cached.file_path).suffix.lower() != ".vue":
                continue
            file_path = Path(cached.file_path)
            if not file_path.is_absolute():
                file_path = Path(repo_dir) / file_path
            if not file_path.is_file():
                continue
            self.functions[component_id] = cached.model_copy(deep=True)
        live_ids = set(self.functions)
        for component_id, cached in cached_components.items():
            if cached.relative_path and Path(cached.relative_path).as_posix() in self._parsed_files:
                continue
            file_path = Path(cached.file_path)
            if not file_path.is_absolute():
                file_path = Path(repo_dir) / file_path
            if file_path.is_file():
                live_ids.add(component_id)
        for node in self.functions.values():
            if node.language != "vue" and Path(node.file_path).suffix.lower() != ".vue":
                continue
            original_edges = set(node.depends_on or set())
            node.depends_on = set()
            for callee in sorted(original_edges):
                if callee in live_ids:
                    node.depends_on.add(callee)
                    self.call_relationships.append(
                        CallRelationship(caller=node.id, callee=callee, is_resolved=True)
                    )

    def _merge_cached_zig_components(
        self, cached_components: Optional[Dict[str, Node]], repo_dir: str
    ) -> None:
        """非 Zig 增量复用缓存；只保留仍存在文件的组件与仍存在的目标。"""
        if not cached_components:
            return
        for component_id, cached in cached_components.items():
            if component_id in self.functions:
                continue
            if cached.language != "zig" and Path(cached.file_path).suffix.lower() != ".zig":
                continue
            file_path = Path(cached.file_path)
            if not file_path.is_absolute():
                file_path = Path(repo_dir) / file_path
            if not file_path.is_file():
                continue
            self.functions[component_id] = cached.model_copy(deep=True)
        live_ids = set(self.functions)
        for node in self.functions.values():
            if node.language != "zig":
                continue
            original_edges = set(node.depends_on or set())
            node.depends_on = set()
            for callee in sorted(original_edges):
                if callee in live_ids:
                    node.depends_on.add(callee)
                    self.call_relationships.append(
                        CallRelationship(caller=node.id, callee=callee, is_resolved=True)
                    )

    def _rebuild_dart_scope(self, repo_dir: str, dart_files: list[str]) -> None:
        from codewiki.src.be.dependency_analyzer.analyzers.dart_imports import DartScopeIndex

        self._dart_index = None
        if not any(node.language == "dart" for node in self.functions.values()):
            return
        self._dart_index = DartScopeIndex.from_repo(repo_dir, dart_files, self.functions)
        for caller_id, callee_id in getattr(self, "_dart_cached_edges", []):
            caller = self.functions.get(caller_id)
            if caller is not None and self._dart_index.cached_edge_is_valid(caller, callee_id):
                caller.depends_on.add(callee_id)
                self.call_relationships.append(
                    CallRelationship(caller=caller_id, callee=callee_id, is_resolved=True)
                )

    def _resolve_rust_impl_bases(self) -> None:
        """跨文件 trait impl 在全部类型可见后回填 base class 与类型边。"""
        by_name: Dict[str, List[str]] = defaultdict(list)
        for func_id, node in self.functions.items():
            if node.language == "rust" and node.name:
                by_name[node.name].append(func_id)
        for owner, trait, line in self._rust_impls:
            owner_matches = by_name.get(owner, [])
            if len(owner_matches) != 1:
                continue
            owner_id = owner_matches[0]
            node = self.functions[owner_id]
            bases = node.base_classes or []
            if trait not in bases:
                node.base_classes = [*bases, trait]
            trait_matches = by_name.get(trait, [])
            resolved = len(trait_matches) == 1
            self.call_relationships.append(
                CallRelationship(
                    caller=owner_id,
                    callee=trait_matches[0] if resolved else trait,
                    call_line=line,
                    is_resolved=resolved,
                )
            )

    def _extract_routes(self, file_path: str, content: str, language: str):
        """Post-pass: extract HTTP/MQ routes for cross-service analysis.

        Dispatches to the language-specific route extractor (if available)
        and the language-agnostic MQ pattern detector.
        """
        ext = Path(file_path).suffix.lower()
        repo_name = self._repo_name

        # HTTP route extraction (language-specific)
        extractor = get_extractor(ext)
        if extractor:
            try:
                routes = extractor(file_path, content, repo_name)
                self.routes.extend(routes)
            except Exception as e:
                logger.debug(f"Route extraction failed for {file_path}: {e}")

        # MQ pattern extraction (language-agnostic)
        try:
            mq_routes = extract_mq_routes(file_path, content, repo_name)
            self.routes.extend(mq_routes)
        except Exception as e:
            logger.debug(f"MQ route extraction failed for {file_path}: {e}")

    def _resolve_call_relationships(self):
        """
        Resolve function call relationships across all languages.

        Attempts to match function calls to actual function definitions,
        handling cross-language calls where possible.
        """
        for func_id, func_info in self.functions.items():
            if not func_info.language:
                file_ext = Path(func_info.file_path).suffix.lower()
                func_info.language = CODE_EXTENSIONS.get(file_ext)

        indexes = self._build_resolution_indexes()
        self._go_index = None
        self._scala_index = None

        resolved_count = 0
        for relationship in self.call_relationships:
            if relationship.is_resolved and relationship.callee in self.functions:
                continue

            resolved_id = self._resolve_callee(relationship, indexes)
            if resolved_id:
                relationship.callee = resolved_id
                relationship.is_resolved = True
                resolved_count += 1

        dotted_packages = self._dotted_project_packages()
        self.call_relationships = [
            relationship
            for relationship in self.call_relationships
            if relationship.is_resolved
            or not self._has_authoritative_resolution(relationship)
            and not self._is_external_callee(
                self._caller_language(relationship.caller),
                relationship.callee,
                dotted_packages,
            )
        ]

    def _has_authoritative_resolution(self, relationship: CallRelationship) -> bool:
        """这些解析器拥有作用域裁决；失败后不得再按裸名回退绑定。"""
        caller = self.functions.get(relationship.caller)
        if caller is None:
            return False
        if caller.language == "go":
            return True
        if caller.language == "scala":
            return True
        if caller.language == "dart":
            return True
        if caller.language == "lean":
            return True
        if caller.language == "zig":
            return True
        return caller.language == "ruby" and relationship.callee.startswith(RUBY_IMPLICIT_PREFIX)

    def _dotted_project_packages(self) -> Dict[str, set]:
        """Project packages/namespaces, partitioned by language. Java and C#
        share the namespace-origin rule: a dotted callee qualified to a package
        with no prefix relation to any project package came from a third-party
        import."""
        packages: Dict[str, set] = defaultdict(set)
        for func_info in self.functions.values():
            if func_info.language in ("java", "csharp"):
                package = self._dotted_package_for_node(func_info)
                if package:
                    packages[func_info.language].add(package)
        return packages

    def _is_external_callee(
        self, language: Optional[str], callee: str, dotted_packages: Dict[str, set]
    ) -> bool:
        """Classify a still-unresolved callee as external, after project
        resolution has had its chance.

        Rules are generic, not name lists: prefix/standard-library knowledge in
        is_external_symbol, the C/C++ ALL_CAPS macro convention (macros are
        never components, so such calls can never resolve), Java/C# package
        origin, and Python import-origin + object-method heuristics.
        """
        if is_external_symbol(language, callee):
            return True
        if language in ("c", "cpp") and is_macro_name(callee):
            return True
        if language in ("java", "csharp") and "." in callee and dotted_packages.get(language):
            package = callee.rsplit(".", 1)[0]
            if not any(
                package == project
                or package.startswith(project + ".")
                or project.startswith(package + ".")
                for project in dotted_packages[language]
            ):
                return True
        if language == "python" and "." in callee:
            return self._is_external_python_callee(callee)
        return False

    def _is_external_python_callee(self, callee: str) -> bool:
        """Classify a still-unresolved dotted Python callee.

        A callee whose dotted prefix aligns with a project module is an
        honest project gap, never external. Otherwise the import-origin rule
        (head was imported from outside the project) and the core-object
        method rule (a tail like ``append``/``endswith`` on an unknowable
        receiver can never be a project component) apply.
        """
        from codewiki.src.be.dependency_analyzer.analyzers.python import is_project_import
        from codewiki.src.be.dependency_analyzer.utils.external_symbols import (
            PYTHON_OBJECT_METHODS,
        )

        parts = callee.split(".")
        if self._python_project_modules:
            for end in range(len(parts) - 1, 0, -1):
                if is_project_import(".".join(parts[:end]), self._python_project_modules):
                    return False
        if parts[0] in self._python_external_import_roots:
            return True
        return parts[-1] in PYTHON_OBJECT_METHODS

    def _build_resolution_indexes(self) -> Dict[str, Dict]:
        """Build exact/simple-name lookup indexes, both globally and per
        language. Resolution prefers the caller's own language partition: a
        name that is unique within the caller's language resolves even when
        another language defines the same name, and names made ambiguous only
        by foreign-language components keep resolving as before."""

        def make() -> Dict[str, Dict[str, List[str]]]:
            return {"exact": defaultdict(list), "simple": defaultdict(list)}

        global_indexes = make()
        by_lang: Dict[str, Dict[str, Dict[str, List[str]]]] = defaultdict(make)

        def add(index: Dict[str, List[str]], key: Optional[str], func_id: str) -> None:
            if key and func_id not in index[key]:
                index[key].append(func_id)

        for func_id, func_info in self.functions.items():
            targets = [global_indexes]
            if func_info.language:
                targets.append(by_lang[func_info.language])

            exact_keys = [
                func_id,
                func_info.component_id,
                func_info.qualified_name,
                func_info.name,
            ]

            names = {func_info.name}
            if func_info.component_id:
                names.add(func_info.component_id.split("::")[-1])
            if func_info.qualified_name:
                names.add(func_info.qualified_name.split(".")[-1])
                parts = func_info.qualified_name.split(".")
                if len(parts) >= 2:
                    names.add(".".join(parts[-2:]))

            for target in targets:
                for key in exact_keys:
                    add(target["exact"], key, func_id)
                for name in names:
                    add(target["simple"], name, func_id)
                    if name and "." in name:
                        add(target["simple"], name.split(".")[-1], func_id)

        return {
            "exact": global_indexes["exact"],
            "simple": global_indexes["simple"],
            "by_lang": dict(by_lang),
        }

    def _resolve_callee(
        self, relationship: CallRelationship, indexes: Dict[str, Dict]
    ) -> Optional[str]:
        caller = self.functions.get(relationship.caller)
        caller_language = caller.language if caller else None

        if caller_language == "go" and caller is not None:
            return self._resolve_go_callee(relationship.callee, caller)

        if caller_language == "scala" and caller is not None:
            return self._resolve_scala_callee(relationship.callee, caller)

        if caller_language == "dart" and caller is not None:
            return self._resolve_dart_callee(relationship.callee, caller)

        if caller_language == "lean" and caller is not None:
            return self._resolve_lean_callee(relationship.callee, caller)

        if caller_language == "zig":
            # analyzer 已按 import/别名/容器作用域裁决；这里只允许完整 ID。
            if "::" not in relationship.callee:
                return None
            return self._unique_match(indexes["exact"], relationship.callee)

        # Vue 模板/脚本通过完整 ``path::symbol`` 显式引用 JS/TS 导出；
        # 这是精确身份匹配，不能放宽成裸名跨语言猜测。
        if caller_language == "vue" and "::" in relationship.callee:
            exact = self._unique_match(indexes["exact"], relationship.callee)
            if exact:
                return exact

        lang_indexes = indexes["by_lang"].get(caller_language) if caller_language else None
        if lang_indexes:
            match = self._resolve_callee_in(
                relationship, lang_indexes["exact"], lang_indexes["simple"]
            )
            if match:
                return match

        # Global fallback — reject cross-language matches when caller language is known
        match = self._resolve_callee_in(relationship, indexes["exact"], indexes["simple"])
        if match and caller_language:
            target = self.functions.get(match)
            if target and target.language and target.language != caller_language:
                return None  # Reject cross-language false positive
        return match

    def _resolve_callee_in(
        self,
        relationship: CallRelationship,
        exact: Dict[str, List[str]],
        simple: Dict[str, List[str]],
    ) -> Optional[str]:
        callee_name = relationship.callee
        caller = self.functions.get(relationship.caller)
        if caller and caller.language == "ruby":
            # Ruby 常量按调用者词法命名空间查找，但绝不把 Missing.run
            # 之类的限定调用降级成裸 run 再跨类绑定。隐式方法候选先保留
            # # / . 身份，跨文件解析失败后由调用图层丢弃。
            implicit = callee_name.startswith(RUBY_IMPLICIT_PREFIX)
            logical_name = (
                callee_name[len(RUBY_IMPLICIT_PREFIX) :] if implicit else callee_name
            ).replace("::", ".")
            namespace = self._ruby_caller_namespace(caller)
            parts = namespace.split(".") if namespace else []
            if logical_name.startswith("."):
                if implicit:
                    for length in range(len(parts), 0, -1):
                        candidate = ".".join(parts[:length]) + logical_name
                        match = self._unique_match(exact, candidate)
                        if match:
                            return match
                    return self._unique_match(exact, logical_name)
                return self._unique_match(exact, logical_name.lstrip("."))
            if logical_name.startswith("#"):
                for length in range(len(parts), 0, -1):
                    candidate = ".".join(parts[:length]) + logical_name
                    match = self._unique_match(exact, candidate)
                    if match:
                        return match
                return self._unique_match(exact, logical_name)
            for length in range(len(parts), 0, -1):
                candidate = ".".join([*parts[:length], logical_name])
                match = self._unique_match(exact, candidate)
                if match:
                    return match
            return self._unique_match(exact, logical_name)

        if caller and caller.language == "rust":
            # Rust 的 :: 路径与接收者类型是身份的一部分，不能按尾名猜绑定。
            logical_name = callee_name.replace("::", ".")
            return self._unique_match(exact, logical_name) or self._unique_match(
                simple, logical_name
            )

        exact_match = self._unique_match(exact, callee_name)
        if exact_match:
            return exact_match

        if "::" in callee_name:
            suffix = callee_name.split("::")[-1]
            exact_match = self._unique_match(exact, suffix)
            if exact_match:
                return exact_match
            simple_match = self._unique_match(simple, suffix)
            if simple_match:
                return simple_match

        if "." in callee_name:
            simple_match = self._unique_match(simple, callee_name)
            if simple_match:
                return simple_match
            tail_match = self._unique_match(simple, callee_name.split(".")[-1])
            if tail_match:
                return tail_match

        if caller and caller.language in ("java", "csharp") and "." not in callee_name:
            package = self._dotted_package_for_node(caller)
            if package:
                same_package_match = self._unique_match(exact, f"{package}.{callee_name}")
                if same_package_match:
                    return same_package_match

        return self._unique_match(simple, callee_name)

    @staticmethod
    def _ruby_caller_namespace(node: Node) -> str:
        if node.class_name:
            return node.class_name
        qualified = (node.qualified_name or node.name).split("#", 1)[0]
        if qualified.startswith(("#", ".")):
            return ""
        return qualified.replace("::", ".")

    def _unique_match(self, index: Dict[str, List[str]], key: str) -> Optional[str]:
        matches = index.get(key, [])
        return matches[0] if len(matches) == 1 else None

    def _dotted_package_for_node(self, node: Node) -> str:
        """The package (Java) / namespace (C#) a node lives in, derived from its
        dotted qualified name. Both languages share the same shape: a type's
        package is its qualified name minus the type, a method's is minus
        ``Type.method``."""
        qualified_name = node.qualified_name or ""
        parts = qualified_name.split(".")
        if len(parts) < 2:
            return ""
        if node.component_type == "method" and len(parts) >= 3:
            return ".".join(parts[:-2])
        return ".".join(parts[:-1])

    def _caller_language(self, caller_id: str) -> Optional[str]:
        caller = self.functions.get(caller_id)
        if caller and caller.language:
            return caller.language
        if caller:
            return CODE_EXTENSIONS.get(Path(caller.file_path).suffix.lower())
        return None

    def _deduplicate_relationships(self):
        """
        Deduplicate call relationships based on caller-callee pairs.

        Removes duplicate relationships while preserving the first occurrence.
        This helps eliminate noise from multiple calls to the same function.
        """
        seen = set()
        unique_relationships = []

        for rel in self.call_relationships:
            key = (rel.caller, rel.callee)
            if key not in seen:
                seen.add(key)
                unique_relationships.append(rel)

        self.call_relationships = unique_relationships

    def _generate_visualization_data(self) -> Dict:
        """
        Generate visualization data for graph rendering.

        Creates Cytoscape.js compatible graph data with nodes and edges.

        Returns:
            Dict: Visualization data with cytoscape elements and summary
        """
        cytoscape_elements = []

        for func_id, func_info in self.functions.items():
            node_classes = []
            if func_info.node_type == "method":
                node_classes.append("node-method")
            else:
                node_classes.append("node-function")

            file_ext = Path(func_info.file_path).suffix.lower()
            language = func_info.language or CODE_EXTENSIONS.get(file_ext, "unknown")
            if file_ext == ".py":
                node_classes.append("lang-python")
            elif file_ext == ".js":
                node_classes.append("lang-javascript")
            elif file_ext == ".ts":
                node_classes.append("lang-typescript")
            elif language == "c":
                node_classes.append("lang-c")
            elif language == "cpp" or file_ext in [
                ".cpp",
                ".cc",
                ".cxx",
                ".c++",
                ".hpp",
                ".hxx",
                ".h++",
            ]:
                node_classes.append("lang-cpp")
            elif file_ext in [".kt", ".kts"]:
                node_classes.append("lang-kotlin")
            elif language == "vue":
                node_classes.append("lang-vue")
            elif file_ext in [".php", ".phtml", ".inc"]:
                node_classes.append("lang-php")

            cytoscape_elements.append(
                {
                    "data": {
                        "id": func_id,
                        "label": func_info.name,
                        "file": func_info.file_path,
                        "type": func_info.node_type or "function",
                        "language": language,
                    },
                    "classes": " ".join(node_classes),
                }
            )

        resolved_rels = [r for r in self.call_relationships if r.is_resolved]
        for rel in resolved_rels:
            cytoscape_elements.append(
                {
                    "data": {
                        "id": f"{rel.caller}->{rel.callee}",
                        "source": rel.caller,
                        "target": rel.callee,
                        "line": rel.call_line,
                    },
                    "classes": "edge-call",
                }
            )

        summary = {
            "total_nodes": len(self.functions),
            "total_edges": len(resolved_rels),
            "unresolved_calls": len(self.call_relationships) - len(resolved_rels),
        }

        return {
            "cytoscape": {"elements": cytoscape_elements},
            "summary": summary,
        }

    def generate_llm_format(self) -> Dict:
        """Generate clean format optimized for LLM consumption."""
        return {
            "functions": [
                {
                    "name": func.name,
                    "file": Path(func.file_path).name,
                    "purpose": (func.docstring.split("\n")[0] if func.docstring else None),
                    "parameters": func.parameters,
                    "is_recursive": func.name
                    in [
                        rel.callee
                        for rel in self.call_relationships
                        if rel.caller.endswith(func.name)
                    ],
                }
                for func in self.functions.values()
            ],
            "relationships": {
                func.name: {
                    "calls": [
                        rel.callee.split(":")[-1]
                        for rel in self.call_relationships
                        if rel.caller.endswith(func.name) and rel.is_resolved
                    ],
                    "called_by": [
                        rel.caller.split(":")[-1]
                        for rel in self.call_relationships
                        if rel.callee.endswith(func.name) and rel.is_resolved
                    ],
                }
                for func in self.functions.values()
            },
        }

    def _select_most_connected_nodes(self, target_count: int):
        """
        Select the most connected nodes from the call graph.

        Args:
            target_count: The number of nodes to select
        """
        if len(self.functions) <= target_count:
            return

        if not self.call_relationships:
            logger.warning("No call relationships found - keeping all functions by name")
            func_ids = list(self.functions.keys())[:target_count]
            self.functions = {fid: func for fid, func in self.functions.items() if fid in func_ids}
            return

        graph: dict[str, set[str]] = {}
        for rel in self.call_relationships:
            if rel.caller in self.functions:
                if rel.caller not in graph:
                    graph[rel.caller] = set()
            if rel.callee in self.functions:
                if rel.callee not in graph:
                    graph[rel.callee] = set()

            if rel.caller in graph and rel.callee in graph:
                graph[rel.caller].add(rel.callee)
                graph[rel.callee].add(rel.caller)

        degree_centrality: dict[str, int] = {}
        for func_id in self.functions.keys():
            degree_centrality[func_id] = len(graph.get(func_id, set()))

        sorted_func_ids = sorted(
            degree_centrality, key=lambda func_id: degree_centrality[func_id], reverse=True
        )

        selected_func_ids = sorted_func_ids[:target_count]

        len(self.functions)
        self.functions = {
            fid: func for fid, func in self.functions.items() if fid in selected_func_ids
        }

        len(self.call_relationships)
        self.call_relationships = [
            rel
            for rel in self.call_relationships
            if rel.caller in selected_func_ids and rel.callee in selected_func_ids
        ]
