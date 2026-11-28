"""Dart/Flutter package-aware 分析回归：visible scope、调用身份与增量接入。"""

from pathlib import Path

import pytest

from codewiki.cli.utils.repo_validator import SUPPORTED_EXTENSIONS
from codewiki.cli.utils.validation import detect_supported_languages
from codewiki.mcp.tools.artifact_facts import classify_artifact
from codewiki.mcp.tools.review_checklist import LANG_BY_EXT
from codewiki.src.be.dependency_analyzer.analysis.analysis_service import AnalysisService
from codewiki.src.be.dependency_analyzer.analysis.call_graph_analyzer import CallGraphAnalyzer
from codewiki.src.be.dependency_analyzer.analysis.service_detector import (
    _has_source_files,
    detect_services,
)
from codewiki.src.be.dependency_analyzer.analyzers.dart import (
    TreeSitterDartAnalyzer,
    analyze_dart_file,
)
from codewiki.src.be.dependency_analyzer.analyzers.dart_imports import (
    DartPackageResolver,
    build_scopes,
    parse_directives,
)
from codewiki.src.be.dependency_analyzer.ast_parser import DependencyParser
from codewiki.src.be.dependency_analyzer.utils import grammars
from codewiki.src.be.dependency_analyzer.utils.grammars import GrammarUnavailableError
from codewiki.src.be.prompt_template import EXTENSION_TO_LANGUAGE


SAMPLE = """\
library demo;

import 'package:demo/models/car.dart' as car;
export 'src/public.dart' show Public;

/// Logs messages.
mixin Loggable on Object {
  void log(String m) => print(m);
}

abstract class Repo<T> {
  Future<T> fetch();
}

abstract interface class Disposable {
  void dispose();
}

sealed class Shape {}

/// Cars repo.
class CarRepo extends Repo<Car> with Loggable implements Disposable {
  final ApiClient api;
  CarRepo(this.api);
  factory CarRepo.create() => CarRepo(ApiClient());

  /// Loads the car.
  @override
  Future<Car> fetch() async {
    final r = await api.get('/car');
    log('x');
    return car.Car.fromJson(r);
  }

  int get count => 1;
  set count(int v) {}

  @override
  void dispose() {}
}

extension StringX on String {
  String shout() => toUpperCase();
}

extension on int {
  int twice() => this * 2;
}

enum Status {
  idle,
  busy;

  bool get isIdle => this == Status.idle;
}

int helper(int a, {int b = 2}) => a + b;

String get appName => 'demo';
"""


@pytest.fixture
def clear_grammar_cache():
    grammars.get_language.cache_clear()
    yield
    grammars.get_language.cache_clear()


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _files(root: Path):
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "name": path.name,
            "extension": path.suffix,
            "language": "dart",
        }
        for path in sorted(root.rglob("*.dart"))
        if path.is_file()
    ]


def _graph(root: Path, skip_file_paths=None, cached_components=None) -> CallGraphAnalyzer:
    graph = CallGraphAnalyzer()
    graph.analyze_code_files(
        _files(root),
        str(root),
        skip_file_paths=skip_file_paths,
        cached_components=cached_components,
    )
    return graph


def _edges(graph: CallGraphAnalyzer):
    return {(rel.caller, rel.callee) for rel in graph.call_relationships if rel.is_resolved}


def _cache_edges(graph: CallGraphAnalyzer) -> None:
    for relationship in graph.call_relationships:
        if relationship.is_resolved and relationship.callee in graph.functions:
            graph.functions[relationship.caller].depends_on.add(relationship.callee)


def _analyze(tmp_path: Path, source: str = SAMPLE, name: str = "lib/repo.dart"):
    path = _write(tmp_path, name, source)
    return analyze_dart_file(str(path), source, repo_path=str(tmp_path))


def test_extracts_declarations_with_types(tmp_path: Path) -> None:
    nodes, _ = _analyze(tmp_path)
    by_name = {node.name: node for node in nodes}
    expected = {
        "Loggable": ("class", "mixin"),
        "Loggable.log": ("method", "method"),
        "Repo": ("class", "abstract class"),
        "Repo.fetch": ("method", "method"),
        "Disposable": ("interface", "interface"),
        "Disposable.dispose": ("method", "method"),
        "Shape": ("class", "sealed class"),
        "CarRepo": ("class", "class"),
        "CarRepo.fetch": ("method", "method"),
        "CarRepo.count": ("method", "getter"),
        "CarRepo.dispose": ("method", "method"),
        "CarRepo.create": ("method", "constructor"),
        "StringX": ("class", "extension"),
        "StringX.shout": ("method", "method"),
        "extension_on_int": ("class", "extension"),
        "extension_on_int.twice": ("method", "method"),
        "Status": ("class", "enum"),
        "Status.isIdle": ("method", "getter"),
        "helper": ("function", "function"),
        "appName": ("function", "getter"),
    }
    assert {
        name: (node.component_type, node.node_type) for name, node in by_name.items()
    } == expected
    assert "CarRepo.CarRepo" not in by_name
    assert by_name["CarRepo"].id == "lib/repo.dart::CarRepo"
    assert by_name["CarRepo.fetch"].class_name == "CarRepo"
    assert all(node.language == "dart" for node in nodes)


def test_bases_docstrings_parameters_and_spans(tmp_path: Path) -> None:
    by_name = {node.name: node for node in _analyze(tmp_path)[0]}
    assert by_name["CarRepo"].base_classes == ["Repo", "Loggable", "Disposable"]
    assert by_name["Loggable"].base_classes == ["Object"]
    assert by_name["CarRepo"].docstring == "/// Cars repo."
    assert by_name["CarRepo.fetch"].docstring == "/// Loads the car."
    assert by_name["helper"].parameters == ["a", "b"]
    assert by_name["CarRepo.fetch"].source_code.lstrip().startswith("@override")
    assert by_name["CarRepo.fetch"].source_code.rstrip().endswith("}")


def test_directives_preserve_prefix_show_hide_and_part_of_name(tmp_path: Path) -> None:
    source = """\
library demo;
import 'a.dart' as a show One hide Hidden;
import 'b.dart';
export 'c.dart' show Public;
part 'part.dart';
"""
    _write(tmp_path, "lib/repo.dart", source)
    analyzer = TreeSitterDartAnalyzer(str(tmp_path / "lib/repo.dart"), source, str(tmp_path))
    assert analyzer.import_prefixes == {"a"}
    assert [item.kind for item in analyzer.directives] == [
        "library",
        "import",
        "import",
        "export",
        "part",
    ]
    imported = analyzer.directives[1]
    assert imported.prefix == "a"
    assert imported.show == ("One",)
    assert imported.hide == ("Hidden",)

    _write(tmp_path, "lib/part.dart", "part of demo;\nclass Part {}\n")
    tree = grammars.get_parser("dart").parse(b"part of demo;\n")
    directive = next(item for item in parse_directives(tree.root_node) if item.kind == "part_of")
    assert directive.library_name == "demo"


def test_import_alias_show_hide_and_exports_resolve_visible_scope(tmp_path: Path) -> None:
    _write(tmp_path, "pubspec.yaml", "name: demo\n")
    _write(tmp_path, "lib/src/internal.dart", "class Hidden {}\nclass One {}\n")
    _write(tmp_path, "lib/src/public.dart", "export 'internal.dart' show One;\nclass Public {}\n")
    _write(
        tmp_path,
        "lib/main.dart",
        """import 'package:demo/src/public.dart' as api show One, Public;
class Main {
  void run() {
    api.One();
    api.Public();
  }
}
""",
    )
    _write(
        tmp_path,
        "lib/forbidden.dart",
        "import 'src/public.dart' show Public;\nvoid run() { Hidden(); }\n",
    )

    edges = _edges(_graph(tmp_path))
    assert ("lib/main.dart::Main.run", "lib/src/internal.dart::One") in edges
    assert ("lib/main.dart::Main.run", "lib/src/public.dart::Public") in edges
    assert not any(caller == "lib/forbidden.dart::run" for caller, _ in edges)


def test_export_diamond_preserves_each_path_name_filter(tmp_path: Path) -> None:
    _write(tmp_path, "lib/d.dart", "class Foo {}\nclass Bar {}\n")
    _write(tmp_path, "lib/b.dart", "export 'd.dart' show Foo;\n")
    _write(tmp_path, "lib/c.dart", "export 'd.dart' show Bar;\n")
    _write(tmp_path, "lib/a.dart", "export 'b.dart';\nexport 'c.dart';\n")
    _write(tmp_path, "lib/main.dart", "import 'a.dart';\nvoid run() { Foo(); Bar(); }\n")

    edges = _edges(_graph(tmp_path))
    assert ("lib/main.dart::run", "lib/d.dart::Foo") in edges
    assert ("lib/main.dart::run", "lib/d.dart::Bar") in edges


def test_parts_share_library_scope_and_private_members_stay_private(tmp_path: Path) -> None:
    _write(tmp_path, "lib/app.dart", "library app; import 'dep.dart'; part 'part.dart';\n")
    _write(
        tmp_path, "lib/part.dart", "part of 'app.dart';\nclass Part { void run() => helper(); }\n"
    )
    _write(tmp_path, "lib/dep.dart", "void helper() {}\nclass _Secret {}\n")
    _write(tmp_path, "lib/outside.dart", "import 'dep.dart';\nvoid leak() => _Secret();\n")

    edges = _edges(_graph(tmp_path))
    assert ("lib/part.dart::Part.run", "lib/dep.dart::helper") in edges
    assert not any(caller == "lib/outside.dart::leak" for caller, _ in edges)


def test_authoritative_part_overrides_conflicting_part_of(tmp_path: Path) -> None:
    _write(tmp_path, "lib/app.dart", "library named; part 'part.dart';\nvoid helper() {}\n")
    _write(tmp_path, "lib/part.dart", "part of 'wrong.dart';\nvoid run() => helper();\n")

    assert ("lib/part.dart::run", "lib/app.dart::helper") in _edges(_graph(tmp_path))


def test_bare_calls_do_not_cross_files_without_import(tmp_path: Path) -> None:
    _write(tmp_path, "lib/a.dart", "void run() => helper();\n")
    _write(tmp_path, "lib/b.dart", "void helper() {}\n")
    assert ("lib/a.dart::run", "lib/b.dart::helper") not in _edges(_graph(tmp_path))


def test_ambiguous_imports_are_not_resolved_by_first_wins(tmp_path: Path) -> None:
    _write(tmp_path, "lib/a.dart", "import 'b.dart';\nimport 'c.dart';\nvoid run() => Same();\n")
    _write(tmp_path, "lib/b.dart", "class Same {}\n")
    _write(tmp_path, "lib/c.dart", "class Same {}\n")
    assert not any(caller == "lib/a.dart::run" for caller, _ in _edges(_graph(tmp_path)))


def test_unknown_receiver_and_private_imported_method_do_not_bind(tmp_path: Path) -> None:
    _write(tmp_path, "lib/api.dart", "class Api { void work() {} void _hidden() {} }\n")
    _write(
        tmp_path,
        "lib/main.dart",
        "import 'api.dart';\nvoid run(Unknown u, Api api) { u.work(); api._hidden(); }\n",
    )
    assert not any(caller == "lib/main.dart::run" for caller, _ in _edges(_graph(tmp_path)))


def test_typed_parameters_fields_and_local_variables_resolve_members(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "lib/api.dart",
        "class Api { void work() {} }\nclass Box { final Api api; Box(this.api); }\n",
    )
    _write(
        tmp_path,
        "lib/main.dart",
        """import 'api.dart';
void run(Api api, Box box) {
  final Api local = api;
  box.api.work();
  local.work();
}
""",
    )
    relationships = _graph(tmp_path).call_relationships
    edges = {(item.caller, item.callee) for item in relationships}
    assert ("lib/main.dart::run", "lib/api.dart::Api.work") in edges
    work_calls = [
        item
        for item in relationships
        if item.caller == "lib/main.dart::run" and item.callee == "lib/api.dart::Api.work"
    ]
    assert len(work_calls) == 1
    # 调用图按 caller-callee 去重；首条必须来自多段字段链。
    assert work_calls[0].call_line == 4


def test_lexical_locals_shadow_globals_and_outer_block_types(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "lib/main.dart",
        """void helper() {}
class Other { void remote() {} }
class Api { void remote() {} }
void run(Api a) {
  { Other a; a.remote(); }
  a.remote();
  var helper = () => 1;
  helper();
}
void localShadow() { void helper() {} helper(); }
""",
    )

    edges = _edges(_graph(tmp_path))
    assert ("lib/main.dart::run", "lib/main.dart::Api.remote") in edges
    assert ("lib/main.dart::run", "lib/main.dart::Other.remote") in edges
    assert ("lib/main.dart::run", "lib/main.dart::helper") not in edges
    assert ("lib/main.dart::localShadow", "lib/main.dart::helper") not in edges
    assert ("lib/main.dart::run", "lib/main.dart::helper") not in edges
    assert ("lib/main.dart::localShadow", "lib/main.dart::helper") not in edges


def test_local_variable_shadows_import_prefix(tmp_path: Path) -> None:
    _write(tmp_path, "lib/dep.dart", "class Api { void work() {} }\n")
    _write(
        tmp_path,
        "lib/main.dart",
        """import 'dep.dart' as api;
class Local { void work() {} }
void run(Local api) { api.work(); }
""",
    )

    assert _edges(_graph(tmp_path)) == {("lib/main.dart::run", "lib/main.dart::Local.work")}


def test_prefixed_receiver_type_keeps_import_namespace(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "lib/api.dart",
        "class Api { void work() {} }\nclass Box { final Api api; Box(this.api); }\n",
    )
    _write(
        tmp_path,
        "lib/main.dart",
        "import 'api.dart' as api;\nvoid run(api.Box box) { box.api.work(); }\n",
    )

    assert ("lib/main.dart::run", "lib/api.dart::Api.work") in _edges(_graph(tmp_path))


def test_constructor_inheritance_and_named_constructor_calls(tmp_path: Path) -> None:
    _write(tmp_path, "lib/base.dart", "class Base {}\n")
    _write(
        tmp_path,
        "lib/main.dart",
        "import 'base.dart';\nclass Child extends Base { Child.named() {} }\nvoid run() { Child.named(); }\n",
    )
    edges = _edges(_graph(tmp_path))
    assert ("lib/main.dart::Child", "lib/base.dart::Base") in edges
    assert ("lib/main.dart::run", "lib/main.dart::Child.named") in edges


def test_incremental_change_resolves_cached_package_and_unchanged_edges(tmp_path: Path) -> None:
    _write(tmp_path, "pubspec.yaml", "name: demo\n")
    caller = _write(tmp_path, "lib/main.dart", "import 'package:demo/api.dart';\nvoid run() {}\n")
    api = _write(tmp_path, "lib/api.dart", "class Api { void work() {} }\n")
    full = _graph(tmp_path)
    _cache_edges(full)
    _write(
        tmp_path,
        "lib/main.dart",
        "import 'package:demo/api.dart';\nvoid run(Api api) { api.work(); }\n",
    )

    incremental = _graph(tmp_path, {str(api)}, full.functions)
    assert "lib/api.dart::Api" in incremental.functions
    assert ("lib/main.dart::run", "lib/api.dart::Api.work") in _edges(incremental)

    _cache_edges(incremental)
    unchanged = _graph(tmp_path, {str(api), str(caller)}, incremental.functions)
    assert ("lib/main.dart::run", "lib/api.dart::Api.work") in _edges(unchanged)


def test_pubspec_only_change_reparses_cached_package_callers(tmp_path: Path) -> None:
    import json

    from codewiki.mcp.session import SessionStore
    from codewiki.mcp.tools.analysis import handle_analyze_repo

    _write(tmp_path, "pubspec.yaml", "name: demo\n")
    _write(
        tmp_path,
        "lib/main.dart",
        "import 'package:demo/api.dart';\nvoid run() { Api(); }\n",
    )
    _write(tmp_path, "lib/api.dart", "class Api {}\n")
    store = SessionStore()
    first = json.loads(
        handle_analyze_repo({"repo_path": str(tmp_path), "incremental": False}, store)
    )
    assert "error" not in first, first
    cache = store.get_cache(str(tmp_path))
    assert "lib/api.dart::Api" in cache.get_all_metas()["lib/main.dart::run"].depends_on

    _write(tmp_path, "pubspec.yaml", "name: renamed\n")
    second = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert "error" not in second, second
    assert "lib/main.dart" in second["changes"]["changed_files"]
    caller = store.get_cache(str(tmp_path)).get_all_metas()["lib/main.dart::run"]
    assert "lib/api.dart::Api" not in caller.depends_on


def test_watch_pubspec_only_change_reparses_cached_package_callers(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.mcp.tools.watch import _incremental_refresh

    _write(tmp_path, "pubspec.yaml", "name: demo\n")
    _write(
        tmp_path,
        "lib/main.dart",
        "import 'package:demo/api.dart';\nvoid run() { Api(); }\n",
    )
    _write(tmp_path, "lib/api.dart", "class Api {}\n")
    full = _graph(tmp_path)
    _cache_edges(full)
    cache = AnalysisCache(str(tmp_path), db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.batch_insert_components(full.functions, [], incremental=False)
        _write(tmp_path, "pubspec.yaml", "name: renamed\n")
        components, _, _ = _incremental_refresh(
            str(tmp_path), str(tmp_path / "repowiki"), cache, ["pubspec.yaml"]
        )

        caller = components["lib/main.dart::run"]
        assert "lib/api.dart::Api" not in caller.depends_on
    finally:
        cache.close()


def test_nested_export_hide_propagates_through_transitive_exports(tmp_path: Path) -> None:
    _write(tmp_path, "lib/c.dart", "class Foo {}\nclass Bar {}\n")
    _write(tmp_path, "lib/b.dart", "export 'c.dart';\n")
    _write(tmp_path, "lib/a.dart", "export 'b.dart' hide Foo;\n")
    _write(tmp_path, "lib/main.dart", "import 'a.dart';\nvoid run() { Foo(); Bar(); }\n")
    edges = _edges(_graph(tmp_path))
    assert ("lib/main.dart::run", "lib/c.dart::Bar") in edges
    assert not any(target.endswith("::Foo") for _, target in edges)


def test_prefixed_static_call_and_local_type_name_shadowing(tmp_path: Path) -> None:
    _write(tmp_path, "lib/api.dart", "class Api { static void work() {} }\n")
    _write(
        tmp_path,
        "lib/main.dart",
        "import 'api.dart' as api;\n"
        "void run() { api.Api.work(); }\n"
        "void shadow() { var Api = () => 1; Api(); }\n",
    )
    edges = _edges(_graph(tmp_path))
    assert ("lib/main.dart::run", "lib/api.dart::Api.work") in edges
    assert not any(source == "lib/main.dart::shadow" for source, _ in edges)


def test_part_cycles_and_conflicting_claims_do_not_merge_libraries(tmp_path: Path) -> None:
    _write(tmp_path, "lib/a.dart", "part of 'b.dart';\nvoid fromA() {}\n")
    _write(tmp_path, "lib/b.dart", "part of 'a.dart';\nvoid fromB() { fromA(); }\n")
    _write(tmp_path, "lib/root1.dart", "part 'shared.dart';\nvoid one() {}\n")
    _write(tmp_path, "lib/root2.dart", "part 'shared.dart';\nvoid two() {}\n")
    _write(tmp_path, "lib/shared.dart", "void run() { one(); two(); }\n")
    edges = _edges(_graph(tmp_path))
    assert ("lib/b.dart::fromB", "lib/a.dart::fromA") not in edges
    assert not any(source == "lib/shared.dart::run" for source, _ in edges)


def test_export_hide_and_super_call_use_visible_base(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "lib/api.dart",
        "class Base { void work() {} }\nclass Hidden {}\n",
    )
    _write(tmp_path, "lib/public.dart", "export 'api.dart' hide Hidden;\n")
    _write(
        tmp_path,
        "lib/main.dart",
        "import 'public.dart';\n"
        "class Child extends Base { void run() { super.work(); Hidden(); } }\n",
    )
    edges = _edges(_graph(tmp_path))
    assert ("lib/main.dart::Child.run", "lib/api.dart::Base.work") in edges
    assert not any(target.endswith("::Hidden") for _, target in edges)


def test_legacy_cached_dart_nodes_are_reparsed_once(tmp_path: Path) -> None:
    api = _write(tmp_path, "lib/api.dart", "class Api { void work() {} }\n")
    caller = _write(
        tmp_path,
        "lib/main.dart",
        "import 'api.dart';\nvoid run(Api api) { api.work(); }\n",
    )
    full = _graph(tmp_path)
    _cache_edges(full)
    for node in full.functions.values():
        node.metadata.pop("dart_raw_dependencies", None)
    migrated = _graph(tmp_path, {str(api), str(caller)}, full.functions)
    assert ("lib/main.dart::run", "lib/api.dart::Api.work") in _edges(migrated)
    assert "dart_raw_dependencies" in migrated.functions["lib/main.dart::run"].metadata


def test_cached_raw_references_survive_sqlite_roundtrip(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache

    _write(
        tmp_path,
        "lib/api.dart",
        "class Api { void work() {} }\nclass Box { final Api api; Box(this.api); }\n",
    )
    _write(
        tmp_path,
        "lib/main.dart",
        "import 'api.dart';\nvoid run(Box box) { box.api.work(); }\n",
    )
    full = _graph(tmp_path)
    _cache_edges(full)
    cache = AnalysisCache(tmp_path)
    cache.batch_insert_components(full.functions, [])
    restored = cache.get_components_by_files({"lib/main.dart"})
    assert restored["lib/main.dart::run"].metadata["dart_raw_dependencies"] == {
        "dart:Box.api.work": ["Box.api.work"]
    }


def test_old_sqlite_schema_migrates_dart_metadata(tmp_path: Path) -> None:
    import sqlite3

    from codewiki.mcp.cache import AnalysisCache

    db = tmp_path / ".codewiki" / "analysis_cache.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE components (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            component_type TEXT NOT NULL DEFAULT '', file_path TEXT NOT NULL DEFAULT '',
            relative_path TEXT NOT NULL DEFAULT '', start_line INTEGER DEFAULT 0,
            end_line INTEGER DEFAULT 0, language TEXT DEFAULT '', node_type TEXT,
            base_classes TEXT, class_name TEXT, display_name TEXT, qualified_name TEXT,
            has_docstring INTEGER DEFAULT 0, docstring TEXT DEFAULT '',
            parameters TEXT, depends_on TEXT NOT NULL DEFAULT '[]',
            content_hash TEXT DEFAULT '')"""
    )
    conn.commit()
    conn.close()

    _write(tmp_path, "main.dart", "void main() {}\n")
    cache = AnalysisCache(tmp_path)
    try:
        columns = {row["name"] for row in cache.conn.execute("PRAGMA table_info(components)")}
        assert "metadata_json" in columns
        graph = _graph(tmp_path)
        cache.batch_insert_components(graph.functions, [])
        assert cache.get_all_metas()["main.dart::main"].metadata == {"dart_raw_dependencies": {}}
    finally:
        cache.close()


def test_bare_call_resolves_inherited_method(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "main.dart",
        "class Base { void work() {} }\nclass Child extends Base { void run() { work(); } }\n",
    )
    graph = _graph(tmp_path)
    assert ("main.dart::Child.run", "main.dart::Base.work") in _edges(graph)
    _cache_edges(graph)
    incremental = _graph(tmp_path, {str(tmp_path / "main.dart")}, graph.functions)
    assert ("main.dart::Child.run", "main.dart::Base.work") in _edges(incremental)


def test_cached_edge_is_dropped_when_receiver_field_type_changes(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "lib/api.dart",
        "class Api { void work() {} }\n"
        "class Other { void work() {} }\n"
        "class Box { final Api api; Box(this.api); }\n",
    )
    caller = _write(
        tmp_path,
        "lib/main.dart",
        "import 'api.dart';\nvoid run(Box box) { box.api.work(); }\n",
    )
    full = _graph(tmp_path)
    assert ("lib/main.dart::run", "lib/api.dart::Api.work") in _edges(full)
    _cache_edges(full)

    _write(
        tmp_path,
        "lib/api.dart",
        "class Api { void work() {} }\n"
        "class Other { void work() {} }\n"
        "class Box { final Other api; Box(this.api); }\n",
    )
    incremental = _graph(tmp_path, {str(caller)}, full.functions)
    assert ("lib/main.dart::run", "lib/api.dart::Api.work") not in _edges(incremental)


def test_new_visible_duplicate_invalidates_cached_bare_call(tmp_path: Path) -> None:
    _write(tmp_path, "lib/a.dart", "void helper() {}\n")
    _write(tmp_path, "lib/main.dart", "import 'a.dart';\nvoid run() => helper();\n")
    full = _graph(tmp_path)
    _cache_edges(full)
    _write(tmp_path, "lib/b.dart", "void helper() {}\n")
    _write(
        tmp_path, "lib/main.dart", "import 'a.dart';\nimport 'b.dart';\nvoid run() => helper();\n"
    )

    incremental = _graph(tmp_path, {str(tmp_path / "lib/a.dart")}, full.functions)
    assert ("lib/main.dart::run", "lib/a.dart::helper") not in _edges(incremental)


def test_direct_analyzer_does_not_swallow_missing_grammar(tmp_path: Path, monkeypatch) -> None:
    from codewiki.src.be.dependency_analyzer.analyzers import dart as dart_module

    def unavailable(_language: str):
        raise GrammarUnavailableError("dart", RuntimeError("offline"))

    path = _write(tmp_path, "main.dart", "void main() {}\n")
    monkeypatch.setattr(dart_module, "get_parser", unavailable)
    with pytest.raises(GrammarUnavailableError, match="dart"):
        TreeSitterDartAnalyzer(str(path), path.read_text(), str(tmp_path))


def test_grammar_failure_and_preflight_are_explicit(
    clear_grammar_cache, tmp_path, monkeypatch
) -> None:
    def fail(_language: str):
        raise RuntimeError("grammar shared library missing")

    monkeypatch.setattr(grammars, "_load_language", fail)
    with pytest.raises(GrammarUnavailableError) as info:
        grammars.get_parser("dart")
    assert "tree-sitter-dart" in str(info.value)

    _write(tmp_path, "main.dart", "void main() {}\n")
    with pytest.raises(GrammarUnavailableError):
        CallGraphAnalyzer().analyze_code_files(
            [{"path": "main.dart", "language": "dart"}], str(tmp_path)
        )


def test_dart_is_registered_across_entry_points(tmp_path: Path) -> None:
    assert ".dart" in SUPPORTED_EXTENSIONS
    assert EXTENSION_TO_LANGUAGE[".dart"] == "dart"
    assert "dart" in AnalysisService()._get_supported_languages()
    assert LANG_BY_EXT[".dart"] == "dart"
    assert classify_artifact("lib/main.dart") is None
    assert classify_artifact("pubspec.yaml") == "manifest"
    _write(tmp_path, "lib/main.dart", "void main() {}\n")
    assert detect_supported_languages(tmp_path) == [("Dart", 1)]
    assert _has_source_files(tmp_path)


def test_pubspec_identifies_flutter_services(tmp_path: Path) -> None:
    _write(
        tmp_path, "apps/a/pubspec.yaml", "name: a\ndependencies:\n  flutter:\n    sdk: flutter\n"
    )
    _write(tmp_path, "apps/a/lib/main.dart", "void main() {}\n")
    _write(tmp_path, "apps/b/pubspec.yaml", "name: b\n")
    _write(tmp_path, "apps/b/lib/main.dart", "void main() {}\n")
    services = detect_services(tmp_path)
    assert set(services) == {"a", "b"}
    assert all("build-manifest:pubspec" in service.source for service in services.values())


def test_dart_fingerprint_cache_and_generated_files(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache

    repo = tmp_path / "repo"
    repo.mkdir()
    main = _write(repo, "main.dart", "void main() {}\n")
    pubspec = _write(repo, "pubspec.yaml", "name: demo\n")
    _write(repo, "model.g.dart", "class _$Model {}\n")
    cache = AnalysisCache(repo, db_path=repo / ".codewiki" / "analysis_cache.db")
    try:
        cache.update_file_fingerprints([main.name, pubspec.name, "model.g.dart"])
        assert cache.detect_changes()["no_changes"] is True
        main.write_text("void main() { print('x'); }\n", encoding="utf-8")
        _write(repo, "added.dart", "void added() {}\n")
        changed = cache.detect_changes()
        assert set(changed["changed_files"]) == {"main.dart", "added.dart"}
    finally:
        cache.close()

    components = DependencyParser(str(repo)).parse_repository()
    assert "model.g.dart::_$Model" not in components


def test_flutter_classification_and_provider_reference(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "lib/main.dart",
        """import 'package:flutter/material.dart';
class Counter extends StatefulWidget { @override State createState() => _CounterState(); }
class _CounterState extends State<Counter> { void build() { final x = counterProvider; } }
@riverpod int counter() => 1;
""",
    )
    nodes = _graph(tmp_path).functions
    assert nodes["lib/main.dart::Counter"].node_type == "widget"
    assert nodes["lib/main.dart::_CounterState"].node_type == "state"
    assert nodes["lib/main.dart::counter"].node_type == "riverpod provider"


def test_bad_syntax_and_empty_files_do_not_crash(tmp_path: Path) -> None:
    assert _analyze(tmp_path, "", "lib/empty.dart") == ([], [])
    nodes, relationships = _analyze(tmp_path, "class Broken( {{{ void (", "lib/broken.dart")
    assert isinstance(nodes, list)
    assert isinstance(relationships, list)


def test_package_resolver_rejects_external_and_escaping_uris(tmp_path: Path) -> None:
    _write(tmp_path, "pubspec.yaml", "name: demo\n")
    resolver = DartPackageResolver.from_files(str(tmp_path), ["lib/main.dart"])
    assert resolver.resolve("package:demo/api.dart", "lib/main.dart") == "lib/api.dart"
    assert resolver.resolve("dart:async", "lib/main.dart") is None
    assert resolver.resolve("package:other/api.dart", "lib/main.dart") is None
    assert resolver.resolve("../../outside.dart", "lib/main.dart") is None


def test_duplicate_package_names_are_ambiguous(tmp_path: Path) -> None:
    _write(tmp_path, "a/pubspec.yaml", "name: same\n")
    _write(tmp_path, "a/lib/a.dart", "class A {}\n")
    _write(tmp_path, "b/pubspec.yaml", "name: same\n")
    _write(tmp_path, "b/lib/b.dart", "class B {}\n")
    resolver = DartPackageResolver.from_files(str(tmp_path), ["a/lib/a.dart", "b/lib/b.dart"])

    assert resolver.resolve("package:same/a.dart", "a/lib/a.dart") is None
    assert resolver.resolve("package:same/b.dart", "b/lib/b.dart") is None


def test_scope_export_cycles_terminate(tmp_path: Path) -> None:
    resolver = DartPackageResolver({})
    scopes = build_scopes(
        {
            "a.dart": [
                next(
                    d
                    for d in parse_directives(
                        grammars.get_parser("dart").parse(b"export 'b.dart';").root_node
                    )
                    if d.kind == "export"
                )
            ],
            "b.dart": [
                next(
                    d
                    for d in parse_directives(
                        grammars.get_parser("dart").parse(b"export 'a.dart';").root_node
                    )
                    if d.kind == "export"
                )
            ],
            "consumer.dart": [
                next(
                    d
                    for d in parse_directives(
                        grammars.get_parser("dart").parse(b"import 'a.dart';").root_node
                    )
                    if d.kind == "import"
                )
            ],
        },
        resolver,
        {"a.dart", "b.dart", "consumer.dart"},
    )
    assert scopes.visible["consumer.dart"] == {"a.dart", "b.dart", "consumer.dart"}
