"""Zig 语言薄适配回归：组件身份、仓库内解析、增量与全入口接入。"""

from pathlib import Path
from typing import cast

import pytest

from codewiki.cli.utils.repo_validator import SUPPORTED_EXTENSIONS
from codewiki.cli.utils.validation import detect_supported_languages
from codewiki.mcp.tools import watch as watch_tools
from codewiki.mcp.tools.artifact_facts import classify_artifact
from codewiki.mcp.tools.change_analysis import _SRC_EXTS
from codewiki.mcp.tools.review_checklist import LANG_BY_EXT
from codewiki.src.be.dependency_analyzer.analysis.analysis_service import AnalysisService
from codewiki.src.be.dependency_analyzer.analysis.call_graph_analyzer import CallGraphAnalyzer
from codewiki.src.be.dependency_analyzer.analysis.service_detector import _has_source_files
from codewiki.src.be.dependency_analyzer.analyzers import zig as zig_analyzer
from codewiki.src.be.dependency_analyzer.analyzers.zig import (
    TreeSitterZigAnalyzer,
    analyze_zig_file,
    is_skipped_zig_file,
)
from codewiki.src.be.dependency_analyzer.ast_parser import DependencyParser
from codewiki.src.be.dependency_analyzer.utils import grammars
from codewiki.src.be.dependency_analyzer.utils.grammars import GrammarUnavailableError
from codewiki.src.be.dependency_analyzer.utils.patterns import CODE_EXTENSIONS
from codewiki.src.be.prompt_template import EXTENSION_TO_LANGUAGE


SAMPLE = """\
const util = @import("util.zig");
const Alias = util.Point;
const std = @import("std");

/// A two-dimensional point.
pub const Point = struct {
    x: f64,
    next: ?*Point,

    pub fn init(x: f64) Point {
        return .{ .x = x };
    }

    pub fn shift(self: *Point, dx: f64) Point {
        helper(dx);
        return self;
    }
};

/// Generic stack.
pub fn List(comptime T: type) type {
    return struct {
        item: ?*T,
        pub fn create() @This() {
            return .{};
        }
    };
}

pub fn helper(value: f64) f64 {
    return value;
}

pub fn main() !void {
    const p = Point.init(1.0);
    p.shift(2.0);
    const alias: Alias = p;
    alias.shift(3.0);
    const items = List(u8){};
    _ = items;
    std.debug.print("external", .{});
}

test "not a component" {
    helper(4.0);
}
"""


@pytest.fixture(autouse=True)
def clear_grammar_cache():
    grammars.get_language.cache_clear()
    yield
    grammars.get_language.cache_clear()


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _analyze(tmp_path: Path, source: str = SAMPLE, rel: str = "src/main.zig"):
    path = _write(tmp_path, rel, source)
    return analyze_zig_file(str(path), source, repo_path=str(tmp_path))


def _files(root: Path) -> list[dict]:
    result = []
    for path in sorted(root.rglob("*.zig")):
        rel = path.relative_to(root).as_posix()
        if is_skipped_zig_file(rel):
            continue
        result.append(
            {
                "path": rel,
                "name": path.name,
                "extension": ".zig",
                "language": "zig",
            }
        )
    return result


def _graph(root: Path, skip: set[str] | None = None, cached: dict | None = None):
    graph = CallGraphAnalyzer()
    graph.analyze_code_files(
        _files(root), str(root), skip_file_paths=skip, cached_components=cached
    )
    return graph


def _edges(graph: CallGraphAnalyzer) -> set[tuple[str, str]]:
    return {(rel.caller, rel.callee) for rel in graph.call_relationships if rel.is_resolved}


def test_extracts_containers_generic_methods_and_docs(tmp_path: Path) -> None:
    nodes, _ = _analyze(tmp_path)
    by_id = {node.id: node for node in nodes}

    assert by_id["src/main.zig::Point"].component_type == "struct"
    assert by_id["src/main.zig::Point"].has_docstring
    assert "two-dimensional point" in by_id["src/main.zig::Point"].docstring
    assert by_id["src/main.zig::Point.init"].component_type == "method"
    assert by_id["src/main.zig::Point.init"].class_name == "Point"
    assert by_id["src/main.zig::Point.init"].parameters == ["x"]
    assert by_id["src/main.zig::List"].node_type == "struct"
    assert "generic struct List" in by_id["src/main.zig::List"].display_name
    assert "src/main.zig::List.create" in by_id
    assert "src/main.zig::main" in by_id
    assert "src/main.zig::test" not in by_id
    assert all(node.language == "zig" for node in nodes)


def test_container_kinds_nested_containers_and_self(tmp_path: Path) -> None:
    nodes, _ = _analyze(
        tmp_path,
        """\
const Color = enum { red, blue };
const Bits = union { a: u8, b: u16 };
const Opaque = opaque {};
const Outer = struct {
    const Inner = struct {
        const Self = @This();
        pub fn make() Self { return .{}; }
    };
};
""",
    )
    by_id = {node.id: node for node in nodes}
    assert by_id["src/main.zig::Color"].node_type == "enum"
    assert by_id["src/main.zig::Color"].component_type == "class"
    assert by_id["src/main.zig::Bits"].node_type == "union"
    assert by_id["src/main.zig::Opaque"].node_type == "opaque"
    assert "src/main.zig::Outer.Inner.make" in by_id


def test_same_file_calls_constructors_types_and_instances(tmp_path: Path) -> None:
    nodes, relationships = _analyze(tmp_path)
    edges = {(rel.caller, rel.callee, rel.is_resolved) for rel in relationships}

    assert ("src/main.zig::main", "src/main.zig::Point.init", True) in edges
    assert ("src/main.zig::main", "src/main.zig::Point.shift", True) in edges
    assert ("src/main.zig::main", "src/main.zig::List", True) in edges
    assert ("src/main.zig::Point.shift", "src/main.zig::helper", True) in edges
    assert ("src/main.zig::Point.init", "src/main.zig::Point", True) in edges
    assert ("src/main.zig::Point", "src/main.zig::Point", True) not in edges
    assert ("src/main.zig::main", "std.debug.print", False) not in edges
    assert not any(rel.caller.endswith("::test") for rel in relationships)


def test_typed_initializer_keeps_call_and_type_edges(tmp_path: Path) -> None:
    source = """\
const Point = struct {};
fn make() Point { return .{}; }
pub fn main() void {
    const point: Point = make();
    _ = point;
}
"""
    _, relationships = _analyze(tmp_path, source, "main.zig")
    edges = {(rel.caller, rel.callee, rel.is_resolved) for rel in relationships}
    assert ("main.zig::main", "main.zig::make", True) in edges
    assert ("main.zig::main", "main.zig::Point", True) in edges


def test_nested_block_locals_do_not_leak_to_outer_scope(tmp_path: Path) -> None:
    source = """\
const A = struct { pub fn run() void {} };
const B = struct { pub fn run() void {} };
pub fn main() void {
    const value = A{};
    {
        const value = B{};
        value.run();
    }
    value.run();
}
"""
    _, relationships = _analyze(tmp_path, source, "main.zig")
    edges = {(rel.caller, rel.callee, rel.is_resolved) for rel in relationships}
    assert ("main.zig::main", "main.zig::A.run", True) in edges
    assert ("main.zig::main", "main.zig::B.run", True) in edges


def test_unknown_receiver_does_not_bind_by_tail_name(tmp_path: Path) -> None:
    _write(tmp_path, "a.zig", "pub fn run() void {}\n")
    nodes, relationships = _analyze(
        tmp_path,
        "pub fn main() void { unknown.run(); }\n",
        "b.zig",
    )
    assert nodes and relationships == []


def test_import_alias_and_reexport_resolve_to_exact_ids(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/geo.zig",
        "pub const Point = struct { pub fn init() @This() { return .{}; } };\n",
    )
    _write(tmp_path, "src/util.zig", 'pub const Point = @import("geo.zig").Point;\n')
    _analyze(
        tmp_path,
        'const util = @import("src/util.zig");\npub fn main() void { util.Point.init(); }\n',
        "main.zig",
    )
    graph = _graph(tmp_path)

    assert (
        "main.zig::main",
        "src/geo.zig::Point.init",
    ) in _edges(graph)


def test_missing_external_and_outside_repo_imports_are_not_edges(tmp_path: Path) -> None:
    source = """\
const missing = @import("missing.zig");
const outside = @import("../outside.zig");
const std = @import("std");
pub fn main() void { missing.run(); outside.run(); std.debug.print("x", .{}); }
"""
    _write(tmp_path / "repo", "main.zig", source)
    _, relationships = _analyze(tmp_path / "repo", source, rel="main.zig")
    assert relationships == []


@pytest.mark.parametrize(
    "root_expression",
    [
        '.{ .root_source_file = b.path("../outside.zig") }',
        '.{ .root_source_file = .{ .path = "../outside.zig" } }',
    ],
)
def test_build_module_rejects_relative_outside_root(tmp_path: Path, root_expression: str) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(tmp_path, "outside.zig", "pub fn outside() void {}\n")
    _write(
        repo,
        "build.zig",
        f'pub fn build(b: anytype) void {{ b.addModule("app", {root_expression}); }}\n',
    )
    _analyze(repo, 'const app = @import("app");\npub fn main() void { app.outside(); }\n')

    graph = _graph(repo)

    assert not any(callee.endswith("::outside") for _, callee in _edges(graph))


def test_build_module_rejects_absolute_outside_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = _write(tmp_path, "outside.zig", "pub fn outside() void {}\n")
    _write(
        repo,
        "build.zig",
        f'pub fn build(b: anytype) void {{ b.addModule("app", .{{ .root_source_file = b.path("{outside}") }}); }}\n',
    )
    _analyze(repo, 'const app = @import("app");\npub fn main() void { app.outside(); }\n')

    graph = _graph(repo)

    assert not any(callee.endswith("::outside") for _, callee in _edges(graph))


def test_build_module_rejects_symlink_outside_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = _write(tmp_path, "outside.zig", "pub fn outside() void {}\n")
    try:
        (repo / "link.zig").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    _write(
        repo,
        "build.zig",
        'pub fn build(b: anytype) void { b.addModule("app", .{ .root_source_file = b.path("link.zig") }); }\n',
    )
    _analyze(repo, 'const app = @import("app");\npub fn main() void { app.outside(); }\n')

    graph = _graph(repo)

    assert not any(callee.endswith("::outside") for _, callee in _edges(graph))


def test_direct_symlink_import_outside_repo_is_not_edge(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = _write(tmp_path, "outside.zig", "pub fn outside() void {}\n")
    try:
        (repo / "link.zig").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    _analyze(repo, 'const ext = @import("link.zig");\npub fn main() void { ext.outside(); }\n')

    graph = _graph(repo)

    assert not any(callee.endswith("::outside") for _, callee in _edges(graph))


def test_direct_symlink_import_inside_repo_uses_canonical_component_id(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = _write(repo, "src/real.zig", "pub fn run() void {}\n")
    try:
        (repo / "link.zig").symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    _analyze(
        repo,
        'const linked = @import("link.zig");\npub fn main() void { linked.run(); }\n',
        rel="main.zig",
    )

    graph = _graph(repo)

    assert ("main.zig::main", "src/real.zig::run") in _edges(graph)
    assert not any(callee.startswith("link.zig::") for _, callee in _edges(graph))


def test_build_module_symlink_inside_repo_uses_canonical_component_id(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = _write(repo, "src/real.zig", "pub fn run() void {}\n")
    try:
        (repo / "link.zig").symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    _write(
        repo,
        "build.zig",
        'pub fn build(b: anytype) void { b.addModule("app", .{ .root_source_file = b.path("link.zig") }); }\n',
    )
    _analyze(
        repo,
        'const app = @import("app");\npub fn main() void { app.run(); }\n',
        rel="main.zig",
    )

    graph = _graph(repo)

    assert ("main.zig::main", "src/real.zig::run") in _edges(graph)
    assert not any(callee.startswith("link.zig::") for _, callee in _edges(graph))


@pytest.mark.parametrize(
    "expression",
    [
        'b.addModule("app", .{ .root_source_file = b.path("src/app.zig") });',
        'b.addModule("app", .{ .root_source_file = .{ .path = "src/app.zig" } });',
    ],
)
def test_build_zig_module_mapping(tmp_path: Path, expression: str) -> None:
    _write(tmp_path, "src/app.zig", "pub fn run() void {}\n")
    _write(tmp_path, "build.zig", f"pub fn build(b: anytype) void {{ {expression} }}\n")
    _analyze(
        tmp_path, 'const app = @import("app");\npub fn main() void { app.run(); }\n', "main.zig"
    )
    graph = _graph(tmp_path)
    assert ("main.zig::main", "src/app.zig::run") in _edges(graph)


def test_cache_directories_and_bad_syntax_are_safe(tmp_path: Path) -> None:
    path = _write(tmp_path, "zig-cache/generated.zig", "pub fn cached() void {}\n")
    analyzer = TreeSitterZigAnalyzer(str(path), path.read_text(), str(tmp_path))
    assert analyzer.nodes == []
    assert is_skipped_zig_file(".zig-cache/x.zig")
    assert is_skipped_zig_file("zig-out/bin/x.zig")
    assert not is_skipped_zig_file("src/zig-cache.zig")

    nodes, relationships = _analyze(tmp_path, "pub fn broken( { ???\n", "broken.zig")
    assert isinstance(nodes, list)
    assert isinstance(relationships, list)


def test_grammar_failure_is_not_swallowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write(tmp_path, "main.zig", "pub fn main() void {}\n")

    def fail(_language):
        raise GrammarUnavailableError("zig", RuntimeError("zig grammar unavailable"))

    monkeypatch.setattr(zig_analyzer, "get_parser", fail)
    with pytest.raises(GrammarUnavailableError):
        analyze_zig_file(str(path), path.read_text(), str(tmp_path))


def test_incremental_zig_change_reparses_all_zig_files(tmp_path: Path, monkeypatch) -> None:
    _write(tmp_path, "a.zig", "pub fn a() void {}\n")
    _write(tmp_path, "b.zig", "pub fn b() void {}\n")
    full = _graph(tmp_path)
    cached = dict(full.functions)
    seen: list[str] = []
    original = TreeSitterZigAnalyzer._analyze

    def record(self):
        seen.append(self.relative_path)
        return original(self)

    monkeypatch.setattr(TreeSitterZigAnalyzer, "_analyze", record)
    _write(tmp_path, "a.zig", 'const b = @import("b.zig");\npub fn a() void { b.b(); }\n')
    graph = _graph(tmp_path, {str(tmp_path / "a.zig"), "b.zig"}, cached)
    assert set(seen) == {"a.zig", "b.zig"}
    assert ("a.zig::a", "b.zig::b") in _edges(graph)


def test_non_zig_increment_merges_only_live_zig_targets(tmp_path: Path) -> None:
    _write(tmp_path, "a.zig", 'const b = @import("b.zig");\npub fn a() void { b.b(); }\n')
    _write(tmp_path, "b.zig", "pub fn b() void {}\n")
    _write(tmp_path, "helper.py", "def helper(): pass\n")
    full = _graph(tmp_path)
    cached = dict(full.functions)
    graph = _graph(tmp_path, {str(tmp_path / "a.zig"), str(tmp_path / "b.zig")}, cached)
    assert ("a.zig::a", "b.zig::b") in _edges(graph)

    (tmp_path / "b.zig").unlink()
    (tmp_path / "helper.py").write_text("def helper(): return 1\n")
    stale_cache = {key: value.model_copy(deep=True) for key, value in cached.items()}
    graph = _graph(tmp_path, {str(tmp_path / "a.zig")}, stale_cache)
    assert "b.zig::b" not in graph.functions
    assert ("a.zig::a", "b.zig::b") not in _edges(graph)


def test_language_registration_and_file_selection(tmp_path: Path) -> None:
    assert CODE_EXTENSIONS[".zig"] == "zig"
    assert grammars._GRAMMAR_MODULES["zig"] == "tree_sitter_zig"
    assert ".zig" in SUPPORTED_EXTENSIONS
    assert ".zig" in _SRC_EXTS
    assert LANG_BY_EXT[".zig"] == "zig"
    assert EXTENSION_TO_LANGUAGE[".zig"] == "zig"
    assert _has_source_files(tmp_path) is False
    _write(tmp_path, "main.zig", "pub fn main() void {}\n")
    _write(tmp_path, "build.zig", "pub fn build(b: anytype) void {}\n")
    assert detect_supported_languages(tmp_path) == [("Zig", 2)]
    service = AnalysisService()
    assert "zig" in service._get_supported_languages()
    _write(tmp_path, "main.zig", "pub fn main() void {}\n")
    assert _has_source_files(tmp_path) is True
    parser = DependencyParser(str(tmp_path))
    assert parser._file_to_module_path("src/main.zig") == "src.main"


def test_watch_zig_change_reparses_all_zig(tmp_path: Path, monkeypatch) -> None:
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.src.be import dependency_analyzer

    _write(tmp_path, "a.zig", "pub fn a() void {}\n")
    _write(tmp_path, "b.zig", "pub fn b() void {}\n")
    captured = {}

    class FakeCache:
        def get_cached_file_paths(self):
            return {"a.zig", "b.zig"}

        def get_components_by_files(self, paths):
            return {}

        def remove_by_file(self, path):
            return None

        def remove_routes_by_file(self, path):
            return None

        def batch_insert_components(self, *args, **kwargs):
            return None

        def update_file_fingerprints(self, paths):
            return None

        def remove_file_fingerprints(self, paths):
            return None

    def build(self, **kwargs):
        captured.update(kwargs)
        return {}, [], []

    monkeypatch.setattr(dependency_analyzer.DependencyGraphBuilder, "build_dependency_graph", build)
    watch_tools._incremental_refresh(
        str(tmp_path), str(tmp_path), cast(AnalysisCache, FakeCache()), ["a.zig"]
    )
    assert captured["skip_file_paths"] == set()


def test_fingerprints_include_alias_only_zig_files(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.mcp.tools.analysis import _zig_analysis_paths

    _write(tmp_path, "src/geo.zig", "pub const Point = struct {};\n")
    _write(tmp_path, "src/alias.zig", 'pub const Point = @import("geo.zig").Point;\n')
    _write(tmp_path, "zig-cache/generated.zig", "pub fn cached() void {}\n")
    _write(tmp_path, "zig-out/bin.zig", "pub fn output() void {}\n")

    paths = set(_zig_analysis_paths(tmp_path))
    assert paths == {"src/geo.zig", "src/alias.zig"}

    cache = AnalysisCache(tmp_path)
    try:
        cache.update_file_fingerprints(list(paths))
        detected = cache._fp_detect()
        assert detected is not None and detected["no_changes"] is True
    finally:
        cache.close()


def test_deleted_alias_only_zig_fingerprint_converges(tmp_path: Path) -> None:
    import json

    from codewiki.mcp.session import SessionStore
    from codewiki.mcp.tools.analysis import handle_analyze_repo

    alias = _write(tmp_path, "src/alias.zig", 'pub const Point = @import("geo.zig").Point;\n')
    _write(tmp_path, "src/geo.zig", "pub const Point = struct {};\n")
    store = SessionStore()
    first = json.loads(
        handle_analyze_repo({"repo_path": str(tmp_path), "incremental": False}, store)
    )
    assert "error" not in first, first

    alias.unlink()
    second = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert second["changes"]["changed_files"] == ["src/alias.zig"]

    third = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert third["changes"]["no_changes"] is True
    assert third["changes"]["changed_files"] == []


def test_fingerprint_and_mtime_ignore_zig_build_outputs(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.mcp.tools.analysis import _detect_mtime_from_meta

    _write(tmp_path, "src/main.zig", "pub fn main() void {}\n")
    _write(tmp_path, ".zig-cache/cache.zig", "pub fn cached() void {}\n")
    _write(tmp_path, "zig-out/out.zig", "pub fn out() void {}\n")
    cache = AnalysisCache(tmp_path)
    try:
        cache.update_file_fingerprints(["src/main.zig"])
        detected = cache._fp_detect()
        assert detected is not None and detected["no_changes"] is True
    finally:
        cache.close()
    metadata = {"generation_info": {"timestamp": "2000-01-01T00:00:00"}}
    mtime_changes = _detect_mtime_from_meta(tmp_path, metadata)
    assert mtime_changes is not None and mtime_changes["changed_files"] == ["src/main.zig"]


def test_build_zig_is_an_artifact_but_plain_zig_source_is_not(tmp_path: Path) -> None:
    _write(tmp_path, "build.zig", "pub fn build(b: anytype) void {}\n")
    _write(tmp_path, "src/main.zig", "pub fn main() void {}\n")
    assert classify_artifact("build.zig") == "build"
    assert classify_artifact("src/main.zig") is None


def test_build_zig_artifact_extracts_source_references(tmp_path: Path) -> None:
    from codewiki.mcp.tools.artifact_facts import analyze_artifact_facts

    _write(
        tmp_path,
        "build.zig",
        "pub fn build(b: anytype) void {\n"
        '    _ = b.addModule("app", .{ .root_source_file = b.path("src/main.zig") });\n'
        "}\n",
    )
    result = analyze_artifact_facts(tmp_path)
    build_fact = next(fact for fact in result["facts"] if fact["kind"] == "build")
    assert {"kind": "path", "value": "src/main.zig"} in build_fact["references"]
