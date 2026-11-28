"""Go package-aware 分析回归：包内解析、import 来源与隐式 interface。"""

from pathlib import Path

import pytest

from codewiki.src.be.dependency_analyzer.analysis.call_graph_analyzer import CallGraphAnalyzer
from codewiki.src.be.dependency_analyzer.analyzers.go import TreeSitterGoAnalyzer
from codewiki.src.be.dependency_analyzer.analyzers.go_package import (
    GoPackageIndex,
    go_package_ref,
    is_skipped_go_file,
    link_go_interfaces,
    resolve_go_callee,
    resolve_repository_import,
    split_go_package_ref,
)
from codewiki.src.be.dependency_analyzer.analyzers.route_extractors import get_extractor
from codewiki.src.be.dependency_analyzer.ast_parser import DependencyParser
from codewiki.src.be.dependency_analyzer.utils.grammars import GrammarUnavailableError


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _graph(
    root: Path,
    skip_file_paths: set[str] | None = None,
    cached_components: dict | None = None,
) -> CallGraphAnalyzer:
    files = []
    for path in sorted(root.rglob("*.go")):
        rel = path.relative_to(root).as_posix()
        files.append({"path": rel, "name": path.name, "extension": ".go", "language": "go"})
    graph = CallGraphAnalyzer()
    graph.analyze_code_files(
        files,
        str(root),
        skip_file_paths=skip_file_paths,
        cached_components=cached_components,
    )
    return graph


def _edges(graph: CallGraphAnalyzer) -> set[tuple[str, str]]:
    return {(rel.caller, rel.callee) for rel in graph.call_relationships if rel.is_resolved}


def test_package_refs_and_component_ids_are_stable() -> None:
    assert go_package_ref("", "Run") == "*.go::Run"
    assert go_package_ref("pkg/a", "Run") == "pkg/a/*.go::Run"
    assert split_go_package_ref("*.go::Run") == ("", "Run")
    assert split_go_package_ref("pkg/a/*.go::Run") == ("pkg/a", "Run")
    assert split_go_package_ref("pkg/a.go::Run") is None


def test_same_package_cross_file_function_resolves(tmp_path: Path) -> None:
    _write(tmp_path, "go.mod", "module example.com/m\n\ngo 1.22\n")
    _write(tmp_path, "a/a.go", "package a\nfunc Run() { helper() }\n")
    _write(tmp_path, "a/b.go", "package a\nfunc helper() {}\n")

    graph = _graph(tmp_path)

    assert ("a/a.go::Run", "a/b.go::helper") in _edges(graph)
    assert graph.functions["a/a.go::Run"].qualified_name == "a.Run"
    assert graph.functions["a/b.go::helper"].qualified_name == "a.helper"


def test_root_package_uses_root_package_reference(tmp_path: Path) -> None:
    _write(tmp_path, "main.go", "package main\nfunc main() { run() }\n")
    _write(tmp_path, "run.go", "package main\nfunc run() {}\n")

    graph = _graph(tmp_path)

    assert ("main.go::main", "run.go::run") in _edges(graph)


def test_same_name_in_different_directories_does_not_cross_bind(tmp_path: Path) -> None:
    _write(tmp_path, "go.mod", "module example.com/m\n\ngo 1.22\n")
    _write(tmp_path, "a/a.go", "package a\nfunc Same() {}\n")
    _write(tmp_path, "b/b.go", "package b\nfunc Same() {}\n")
    _write(
        tmp_path,
        "cmd/main.go",
        'package main\nimport "example.com/m/a"\nfunc main() { a.Same() }\n',
    )

    graph = _graph(tmp_path)

    assert ("cmd/main.go::main", "a/a.go::Same") in _edges(graph)
    assert ("cmd/main.go::main", "b/b.go::Same") not in _edges(graph)


def test_local_replace_maps_to_repository_directory(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "modules/app/go.mod",
        "module example.com/app\n\nreplace example.com/lib => ../lib\n",
    )
    _write(
        tmp_path,
        "modules/app/main.go",
        'package main\nimport "example.com/lib"\nfunc main() { lib.Run() }\n',
    )
    _write(tmp_path, "modules/lib/run.go", "package lib\nfunc Run() {}\n")

    assert (
        resolve_repository_import("example.com/lib", "modules/app", str(tmp_path)) == "modules/lib"
    )
    graph = _graph(tmp_path)
    assert ("modules/app/main.go::main", "modules/lib/run.go::Run") in _edges(graph)


def test_external_import_and_builtins_do_not_create_project_edges(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "main.go",
        'package main\nimport "fmt"\nfunc main() { fmt.Println("x"); println("y") }\n',
    )

    graph = _graph(tmp_path)

    assert not graph.call_relationships


def test_import_alias_resolves_repository_package(tmp_path: Path) -> None:
    _write(tmp_path, "go.mod", "module example.com/m\n\ngo 1.22\n")
    _write(
        tmp_path,
        "main.go",
        'package main\nimport alias "example.com/m/a"\nfunc main() { alias.Run() }\n',
    )
    _write(tmp_path, "a/a.go", "package a\nfunc Run() {}\n")

    graph = _graph(tmp_path)

    assert ("main.go::main", "a/a.go::Run") in _edges(graph)


def test_dot_and_blank_imports_remain_conservative(tmp_path: Path) -> None:
    _write(tmp_path, "go.mod", "module example.com/m\n\ngo 1.22\n")
    _write(
        tmp_path,
        "main.go",
        'package main\nimport (_ "example.com/m/a"; . "example.com/m/b")\nfunc main() { Run() }\n',
    )
    _write(tmp_path, "a/a.go", "package a\nfunc Hidden() {}\n")
    _write(tmp_path, "b/b.go", "package b\nfunc Run() {}\n")

    graph = _graph(tmp_path)

    assert not _edges(graph)


def test_implicit_interface_implementation_uses_cross_file_method_set(tmp_path: Path) -> None:
    _write(tmp_path, "iface.go", "package p\ntype Runner interface { Run() }\n")
    _write(
        tmp_path,
        "service.go",
        "package p\ntype Service struct{}\nfunc (Service) Run() {}\n",
    )

    graph = _graph(tmp_path)

    assert ("service.go::Service", "iface.go::Runner") in _edges(graph)
    assert "Runner" in (graph.functions["service.go::Service"].base_classes or [])


def test_incomplete_method_set_is_not_an_implementation(tmp_path: Path) -> None:
    _write(tmp_path, "iface.go", "package p\ntype Runner interface { Run(); Stop() }\n")
    _write(
        tmp_path,
        "service.go",
        "package p\ntype Service struct{}\nfunc (Service) Run() {}\n",
    )

    graph = _graph(tmp_path)

    assert ("service.go::Service", "iface.go::Runner") not in _edges(graph)


def test_unknown_receiver_method_resolves_only_when_visible_and_unique(tmp_path: Path) -> None:
    _write(tmp_path, "go.mod", "module example.com/m\n\ngo 1.22\n")
    _write(
        tmp_path,
        "app/main.go",
        'package app\nimport "example.com/m/lib"\nfunc Call(x interface{}) { x.Run() }\n',
    )
    _write(tmp_path, "lib/lib.go", "package lib\ntype Thing struct{}\nfunc (Thing) Run() {}\n")

    graph = _graph(tmp_path)

    assert ("app/main.go::Call", "lib/lib.go::Thing.Run") in _edges(graph)


def test_unknown_receiver_does_not_guess_unimported_package(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "app/main.go",
        "package app\nfunc Call(x interface{}) { x.Run() }\n",
    )
    _write(
        tmp_path, "other/other.go", "package other\ntype Thing struct{}\nfunc (Thing) Run() {}\n"
    )

    graph = _graph(tmp_path)

    assert ("app/main.go::Call", "other/other.go::Thing.Run") not in _edges(graph)


def test_test_and_vendor_files_are_skipped(tmp_path: Path) -> None:
    assert is_skipped_go_file("pkg/a_test.go")
    assert is_skipped_go_file("vendor/example.com/lib/lib.go")
    assert not is_skipped_go_file("pkg/a.go")

    _write(tmp_path, "a.go", "package p\nfunc Real() {}\n")
    _write(tmp_path, "a_test.go", "package p\nfunc TestOnly() {}\n")
    _write(tmp_path, "vendor/example.com/lib/lib.go", "package lib\nfunc Vendored() {}\n")

    graph = _graph(tmp_path)

    assert set(graph.functions) == {"a.go::Real"}


def test_direct_analyzer_does_not_swallow_missing_grammar(tmp_path: Path, monkeypatch) -> None:
    from codewiki.src.be.dependency_analyzer.analyzers import go as go_module

    def unavailable(_language: str):
        raise GrammarUnavailableError("go", RuntimeError("offline"))

    path = _write(tmp_path, "main.go", "package main\nfunc main() {}\n")
    monkeypatch.setattr(go_module, "get_parser", unavailable)

    with pytest.raises(GrammarUnavailableError, match="go"):
        TreeSitterGoAnalyzer(str(path), path.read_text(), repo_path=str(tmp_path))


def test_route_extractor_remains_registered(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "main.go",
        'package main\nimport "github.com/gin-gonic/gin"\nfunc main() { r := gin.Default(); r.GET("/health", ok) }\nfunc ok(c *gin.Context) {}\n',
    )
    extractor = get_extractor(".go")
    assert extractor is not None
    routes = extractor(str(path), path.read_text(), "demo")
    assert any(route.path == "/health" and route.framework == "gin" for route in routes)


def test_incremental_change_resolves_into_cached_go_package(tmp_path: Path) -> None:
    _write(tmp_path, "go.mod", "module example.com/m\n\ngo 1.22\n")
    _write(
        tmp_path,
        "app/main.go",
        'package app\nimport "example.com/m/lib"\nfunc Call() {}\n',
    )
    lib_path = _write(tmp_path, "lib/lib.go", "package lib\nfunc Run() {}\n")
    full = _graph(tmp_path)

    _write(
        tmp_path,
        "app/main.go",
        'package app\nimport "example.com/m/lib"\nfunc Call() { lib.Run() }\n',
    )
    incremental = _graph(
        tmp_path,
        skip_file_paths={str(lib_path)},
        cached_components=full.functions,
    )

    assert "lib/lib.go::Run" in incremental.functions
    assert ("app/main.go::Call", "lib/lib.go::Run") in _edges(incremental)


def test_dependency_parser_preserves_go_package_identity(tmp_path: Path) -> None:
    _write(tmp_path, "go.mod", "module example.com/m\n\ngo 1.22\n")
    _write(tmp_path, "a/a.go", "package a\nfunc Run() { helper() }\n")
    _write(tmp_path, "a/b.go", "package a\nfunc helper() {}\n")

    components = DependencyParser(str(tmp_path)).parse_repository()

    assert components["a/a.go::Run"].qualified_name == "a.Run"
    assert "a/b.go::helper" in components["a/a.go::Run"].depends_on


def test_go_package_index_is_directory_scoped() -> None:
    first = TreeSitterGoAnalyzer(
        "/repo/a/a.go", "package a\ntype Thing struct{}\nfunc (Thing) Run() {}\n", "/repo"
    )
    second = TreeSitterGoAnalyzer(
        "/repo/b/b.go", "package b\ntype Thing struct{}\nfunc (Thing) Run() {}\n", "/repo"
    )
    functions = {node.id: node for node in [*first.nodes, *second.nodes]}
    index = GoPackageIndex(functions)
    caller = next(node for node in first.nodes if node.component_type == "method")

    assert index.lookup("a", "Thing.Run") == "a/a.go::Thing.Run"
    assert index.lookup("b", "Thing.Run") == "b/b.go::Thing.Run"
    assert resolve_go_callee("Run", caller, index, {"a", "b"}) is None
    assert resolve_go_callee("Run", caller, index, {"a"}) == "a/a.go::Thing.Run"


def test_package_function_does_not_bind_same_named_method(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "a.go",
        "package p\ntype Thing struct{}\nfunc (Thing) Run() {}\n",
    )
    _write(
        tmp_path,
        "z.go",
        "package p\nfunc Run() {}\n",
    )
    _write(
        tmp_path,
        "call.go",
        "package p\nfunc Call() { Run() }\n",
    )

    graph = _graph(tmp_path)

    assert ("call.go::Call", "z.go::Run") in _edges(graph)
    assert ("call.go::Call", "a.go::Thing.Run") not in _edges(graph)


def test_external_qualified_field_type_does_not_bind_local_type(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "main.go",
        'package p\nimport "context"\ntype Holder struct { Ctx context.Context }\ntype Context struct{}\n',
    )

    graph = _graph(tmp_path)

    assert ("main.go::Holder", "main.go::Context") not in _edges(graph)


def test_repository_qualified_field_type_resolves_to_imported_package(tmp_path: Path) -> None:
    _write(tmp_path, "go.mod", "module example.com/m\n\ngo 1.22\n")
    _write(
        tmp_path,
        "main.go",
        'package p\nimport "example.com/m/lib"\ntype Holder struct { Value lib.Thing }\n',
    )
    _write(tmp_path, "lib/lib.go", "package lib\ntype Thing struct{}\n")

    graph = _graph(tmp_path)

    assert ("main.go::Holder", "lib/lib.go::Thing") in _edges(graph)


def test_incremental_interface_change_drops_cached_implementation_edge(tmp_path: Path) -> None:
    iface_path = _write(tmp_path, "iface.go", "package p\ntype Runner interface { Run() }\n")
    service_path = _write(
        tmp_path,
        "service.go",
        "package p\ntype Service struct{}\nfunc (Service) Run() {}\n",
    )
    full = _graph(tmp_path)
    assert ("service.go::Service", "iface.go::Runner") in _edges(full)

    iface_path.write_text(
        "package p\ntype Runner interface { Run(); Stop() }\n",
        encoding="utf-8",
    )
    incremental = _graph(
        tmp_path,
        skip_file_paths={str(service_path)},
        cached_components=full.functions,
    )

    assert ("service.go::Service", "iface.go::Runner") not in _edges(incremental)
    assert "Runner" not in (incremental.functions["service.go::Service"].base_classes or [])


def test_incremental_refresh_preserves_cached_unknown_receiver_edge(tmp_path: Path) -> None:
    _write(tmp_path, "go.mod", "module example.com/m\n\ngo 1.22\n")
    caller_path = _write(
        tmp_path,
        "app/main.go",
        'package app\nimport "example.com/m/lib"\nfunc Call(x interface{}) { x.Run() }\n',
    )
    lib_path = _write(
        tmp_path,
        "lib/lib.go",
        "package lib\ntype Thing struct{}\nfunc (Thing) Run() {}\n",
    )
    full = _graph(tmp_path)
    assert ("app/main.go::Call", "lib/lib.go::Thing.Run") in _edges(full)
    for relationship in full.call_relationships:
        if relationship.is_resolved and relationship.callee in full.functions:
            full.functions[relationship.caller].depends_on.add(relationship.callee)

    _write(tmp_path, "app/other.go", "package app\nfunc Other() {}\n")
    incremental = _graph(
        tmp_path,
        skip_file_paths={str(caller_path), str(lib_path)},
        cached_components=full.functions,
    )

    assert ("app/main.go::Call", "lib/lib.go::Thing.Run") in _edges(incremental)


def test_watch_incremental_refresh_resolves_cached_go_package(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.mcp.tools.watch import _incremental_refresh

    _write(tmp_path, "go.mod", "module example.com/m\n\ngo 1.22\n")
    _write(
        tmp_path,
        "app/main.go",
        'package app\nimport "example.com/m/lib"\nfunc Call() {}\n',
    )
    lib_path = _write(tmp_path, "lib/lib.go", "package lib\nfunc Run() {}\n")
    full = _graph(tmp_path)
    cache = AnalysisCache(str(tmp_path), db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.batch_insert_components(full.functions, [], incremental=False)
        _write(
            tmp_path,
            "app/main.go",
            'package app\nimport "example.com/m/lib"\nfunc Call() { lib.Run() }\n',
        )
        components, _, _ = _incremental_refresh(
            str(tmp_path),
            str(tmp_path / "repowiki"),
            cache,
            ["app/main.go"],
        )

        assert "lib/lib.go::Run" in components
        assert "lib/lib.go::Run" in components["app/main.go::Call"].depends_on
        assert lib_path.exists()
    finally:
        cache.close()


def test_fingerprint_detection_ignores_non_participating_nested_go_manifests(
    tmp_path: Path,
) -> None:
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.mcp.tools.analysis import _go_analysis_paths

    _write(tmp_path, "main.go", "package main\nfunc main() {}\n")
    _write(tmp_path, "vendor/example.com/lib/go.mod", "module example.com/lib\n")
    _write(tmp_path, "testdata/fixture/go.mod", "module example.com/fixture\n")
    cache = AnalysisCache(str(tmp_path), db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.update_file_fingerprints(["main.go", *_go_analysis_paths(tmp_path)])
        assert cache.detect_changes() == {
            "changed_files": [],
            "method": "fingerprint",
            "no_changes": True,
        }
    finally:
        cache.close()


def test_go_mod_replace_only_change_reparses_cached_callers(tmp_path: Path) -> None:
    import json

    from codewiki.mcp.session import SessionStore
    from codewiki.mcp.tools.analysis import handle_analyze_repo

    _write(
        tmp_path,
        "go.mod",
        "module example.com/m\n\ngo 1.22\n\nrequire example.com/lib v0.0.0\n"
        "replace example.com/lib => ./lib-a\n",
    )
    _write(
        tmp_path,
        "app/main.go",
        'package app\nimport "example.com/lib"\nfunc Call() { lib.Run() }\n',
    )
    _write(tmp_path, "lib-a/lib.go", "package lib\nfunc Run() {}\n")
    _write(tmp_path, "lib-b/lib.go", "package lib\nfunc Run() {}\n")
    store = SessionStore()
    first = json.loads(
        handle_analyze_repo({"repo_path": str(tmp_path), "incremental": False}, store)
    )
    assert "error" not in first, first
    cache = store.get_cache(str(tmp_path))
    assert "lib-a/lib.go::Run" in cache.get_all_metas()["app/main.go::Call"].depends_on

    _write(
        tmp_path,
        "go.mod",
        "module example.com/m\n\ngo 1.22\n\nrequire example.com/lib v0.0.0\n"
        "replace example.com/lib => ./lib-b\n",
    )
    second = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert "error" not in second, second
    assert "app/main.go" in second["changes"]["changed_files"]
    caller = store.get_cache(str(tmp_path)).get_all_metas()["app/main.go::Call"]
    assert "lib-b/lib.go::Run" in caller.depends_on
    assert "lib-a/lib.go::Run" not in caller.depends_on


def test_watch_go_mod_replace_only_change_reparses_cached_callers(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.mcp.tools.watch import _incremental_refresh

    _write(
        tmp_path,
        "go.mod",
        "module example.com/m\n\ngo 1.22\n\nrequire example.com/lib v0.0.0\n"
        "replace example.com/lib => ./lib-a\n",
    )
    _write(
        tmp_path,
        "app/main.go",
        'package app\nimport "example.com/lib"\nfunc Call() { lib.Run() }\n',
    )
    _write(tmp_path, "lib-a/lib.go", "package lib\nfunc Run() {}\n")
    _write(tmp_path, "lib-b/lib.go", "package lib\nfunc Run() {}\n")
    full = _graph(tmp_path)
    for relationship in full.call_relationships:
        if relationship.is_resolved and relationship.callee in full.functions:
            full.functions[relationship.caller].depends_on.add(relationship.callee)
    cache = AnalysisCache(str(tmp_path), db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.batch_insert_components(full.functions, [], incremental=False)
        _write(
            tmp_path,
            "go.mod",
            "module example.com/m\n\ngo 1.22\n\nrequire example.com/lib v0.0.0\n"
            "replace example.com/lib => ./lib-b\n",
        )
        components, _, _ = _incremental_refresh(
            str(tmp_path), str(tmp_path / "repowiki"), cache, ["go.mod"]
        )

        caller = components["app/main.go::Call"]
        assert "lib-b/lib.go::Run" in caller.depends_on
        assert "lib-a/lib.go::Run" not in caller.depends_on
    finally:
        cache.close()


def test_link_go_interfaces_ignores_foreign_language_nodes() -> None:
    assert link_go_interfaces({}) == []
