"""Scala package-aware 分析回归：类型身份、调用解析与增量接入。"""

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
from codewiki.src.be.dependency_analyzer.analyzers.scala import (
    ScalaPackageIndex,
    TreeSitterScalaAnalyzer,
    analyze_scala_file,
    resolve_scala_callee,
    scala_package_ref,
    split_scala_package_ref,
)
from codewiki.src.be.dependency_analyzer.ast_parser import DependencyParser
from codewiki.src.be.dependency_analyzer.utils import grammars
from codewiki.src.be.dependency_analyzer.utils.grammars import GrammarUnavailableError
from codewiki.src.be.prompt_template import EXTENSION_TO_LANGUAGE


SAMPLE = """\
package pipeline

import other.{Logger => Log}

/** Base contract for buffers that can be flushed. */
trait Flushable {
  def flush(): Unit
}

/** Buffers events before flushing them downstream. */
class Buffer(capacity: Int, log: Log) extends BaseBuffer with Flushable {
  def push(item: Int): Unit = {
    validate(item)
    log.warn("pushed")
    ExternalService.ping()
  }

  def validate(item: Int): Unit = {
    require(item >= 0)
  }

  def flush(): Unit = {
    println("flushing")
  }
}

/** Companion object for Buffer. */
object Buffer {
  def apply(capacity: Int): Buffer = new Buffer(capacity, new Log(0))
}

def standaloneHelper(value: Int): Int = value + 1
"""

SCALA3_SAMPLE = """\
package shapes

enum Color:
  case Red, Green, Blue

trait Shape:
  def area: Double

case class Circle(radius: Double) extends Shape:
  def area: Double = Math.PI * radius * radius
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


def _analyze(tmp_path: Path, source: str = SAMPLE, rel: str = "buffer.scala"):
    path = _write(tmp_path, rel, source)
    return analyze_scala_file(str(path), source, repo_path=str(tmp_path))


def _files(root: Path) -> list[dict]:
    result = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".scala", ".sc"}:
            continue
        rel = path.relative_to(root).as_posix()
        result.append(
            {
                "path": rel,
                "name": path.name,
                "extension": path.suffix.lower(),
                "language": "scala",
            }
        )
    return result


def _graph(
    root: Path,
    skip_file_paths: set[str] | None = None,
    cached_components: dict | None = None,
) -> CallGraphAnalyzer:
    graph = CallGraphAnalyzer()
    graph.analyze_code_files(
        _files(root),
        str(root),
        skip_file_paths=skip_file_paths,
        cached_components=cached_components,
    )
    return graph


def _edges(graph: CallGraphAnalyzer) -> set[tuple[str, str]]:
    return {(rel.caller, rel.callee) for rel in graph.call_relationships if rel.is_resolved}


def test_package_reference_round_trip() -> None:
    ref = scala_package_ref("pipeline", "Buffer.push")
    assert ref == "scala:pipeline::Buffer.push"
    assert split_scala_package_ref(ref) == ("pipeline", "Buffer.push")
    assert split_scala_package_ref("buffer.scala::Buffer.push") is None


def test_extracts_scala_types_methods_and_companion_identity(tmp_path: Path) -> None:
    nodes, _ = _analyze(tmp_path)
    by_id = {node.id: node for node in nodes}

    assert by_id["buffer.scala::Flushable"].component_type == "interface"
    assert by_id["buffer.scala::Flushable"].node_type == "trait"
    assert by_id["buffer.scala::Buffer"].component_type == "class"
    assert by_id["buffer.scala::Buffer"].base_classes == ["BaseBuffer", "Flushable"]
    assert by_id["buffer.scala::Buffer.push"].class_name == "Buffer"
    assert by_id["buffer.scala::Buffer$"].node_type == "object"
    assert by_id["buffer.scala::Buffer$.apply"].class_name == "Buffer$"
    assert by_id["buffer.scala::standaloneHelper"].component_type == "function"
    assert by_id["buffer.scala::Buffer"].qualified_name == "pipeline.Buffer"
    assert all(node.language == "scala" for node in nodes)


def test_extracts_docstrings_parameters_and_curried_groups(tmp_path: Path) -> None:
    nodes, _ = _analyze(
        tmp_path,
        """\
package p
/** Curried docs. */
class Curried {
  def add(x: Int)(y: Int): Int = x + y
}
""",
    )
    by_id = {node.id: node for node in nodes}

    assert by_id["buffer.scala::Curried"].has_docstring
    assert "Curried docs" in by_id["buffer.scala::Curried"].docstring
    assert by_id["buffer.scala::Curried.add"].parameters == ["x: Int", "y: Int"]


def test_scala3_enum_and_indentation_syntax(tmp_path: Path) -> None:
    nodes, _ = _analyze(tmp_path, SCALA3_SAMPLE, "shapes.scala")
    by_id = {node.id: node for node in nodes}

    assert by_id["shapes.scala::Color"].node_type == "enum"
    assert by_id["shapes.scala::Shape"].component_type == "interface"
    assert by_id["shapes.scala::Circle"].base_classes == ["Shape"]
    assert by_id["shapes.scala::Circle.area"].component_type == "method"


def test_package_object_and_nested_package_block_keep_scope(tmp_path: Path) -> None:
    nodes, _ = _analyze(
        tmp_path,
        """\
package outer.inner {
  import other.Logger
  package object tools { def helper(): Unit = () }
  class Uses(log: Logger) { def run(): Unit = tools.helper() }
}
""",
    )
    by_id = {node.id: node for node in nodes}

    assert by_id["buffer.scala::tools"].node_type == "object"
    assert by_id["buffer.scala::tools"].qualified_name == "outer.inner.tools"
    assert by_id["buffer.scala::tools.helper"].class_name == "tools"
    assert by_id["buffer.scala::Uses"].qualified_name == "outer.inner.Uses"


def test_direct_analyzer_emits_package_scoped_type_and_call_refs(tmp_path: Path) -> None:
    _, relationships = _analyze(tmp_path)
    edges = {(rel.caller, rel.callee, rel.is_resolved) for rel in relationships}

    assert (
        "buffer.scala::Buffer",
        scala_package_ref("pipeline", "@type:Flushable"),
        False,
    ) in edges
    assert (
        "buffer.scala::Buffer",
        scala_package_ref("other", "@type:Logger"),
        False,
    ) in edges
    assert (
        "buffer.scala::Buffer.push",
        scala_package_ref("pipeline", "Buffer.validate"),
        False,
    ) in edges
    assert (
        "buffer.scala::Buffer.push",
        scala_package_ref("other", "Logger.warn"),
        False,
    ) in edges
    assert (
        "buffer.scala::Buffer$.apply",
        scala_package_ref("pipeline", "@type:Buffer"),
        False,
    ) in edges
    assert not any(rel.callee.endswith("require") for rel in relationships)
    assert not any(rel.callee.endswith("println") for rel in relationships)


def test_cross_file_inheritance_constructor_and_calls_resolve(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "base.scala",
        "package pipeline\nclass BaseBuffer {}\n",
    )
    _write(
        tmp_path, "logger.scala", "package other\nclass Logger { def warn(s: String): Unit = () }\n"
    )
    _write(tmp_path, "buffer.scala", SAMPLE)

    graph = _graph(tmp_path)
    edges = _edges(graph)

    assert ("buffer.scala::Buffer", "base.scala::BaseBuffer") in edges
    assert ("buffer.scala::Buffer", "buffer.scala::Flushable") in edges
    assert ("buffer.scala::Buffer", "logger.scala::Logger") in edges
    assert ("buffer.scala::Buffer.push", "buffer.scala::Buffer.validate") in edges
    assert ("buffer.scala::Buffer.push", "logger.scala::Logger.warn") in edges
    assert ("buffer.scala::Buffer$.apply", "buffer.scala::Buffer") in edges
    assert ("buffer.scala::Buffer$.apply", "logger.scala::Logger") in edges


def test_same_package_cross_file_bare_call_resolves(tmp_path: Path) -> None:
    _write(tmp_path, "a.scala", "package p\ndef run(): Unit = helper()\n")
    _write(tmp_path, "b.scala", "package p\ndef helper(): Unit = ()\n")

    graph = _graph(tmp_path)

    assert ("a.scala::run", "b.scala::helper") in _edges(graph)


def test_explicit_import_does_not_cross_bind_same_simple_name(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "app/Caller.scala",
        "package app\nimport a.Same\nclass Caller(x: Same) { def run(): Unit = x.work() }\n",
    )
    _write(tmp_path, "a/Same.scala", "package a\nclass Same { def work(): Unit = () }\n")
    _write(tmp_path, "b/Same.scala", "package b\nclass Same { def work(): Unit = () }\n")

    graph = _graph(tmp_path)

    assert ("app/Caller.scala::Caller.run", "a/Same.scala::Same.work") in _edges(graph)
    assert ("app/Caller.scala::Caller.run", "b/Same.scala::Same.work") not in _edges(graph)


def test_same_package_does_not_fall_back_to_other_package(tmp_path: Path) -> None:
    _write(
        tmp_path, "app/Caller.scala", "package app\nclass Caller { def run(): Unit = helper() }\n"
    )
    _write(tmp_path, "other/Helper.scala", "package other\ndef helper(): Unit = ()\n")

    assert not _edges(_graph(tmp_path))


def test_external_import_does_not_bind_repository_tail_name(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Caller.scala",
        "package app\nimport external.Same\nclass Caller(x: Same) { def run(): Unit = x.work() }\n",
    )
    _write(tmp_path, "rogue.scala", "package rogue\nclass Same { def work(): Unit = () }\n")

    assert not _edges(_graph(tmp_path))


def test_wildcard_import_resolves_only_unique_visible_symbol(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Caller.scala",
        "package app\nimport a._\nclass Caller(x: Same) { def run(): Unit = x.work() }\n",
    )
    _write(tmp_path, "a/Same.scala", "package a\nclass Same { def work(): Unit = () }\n")
    graph = _graph(tmp_path)
    assert ("Caller.scala::Caller.run", "a/Same.scala::Same.work") in _edges(graph)

    _write(
        tmp_path,
        "Caller.scala",
        "package app\nimport a._\nimport b._\nclass Caller(x: Same) { def run(): Unit = x.work() }\n",
    )
    _write(tmp_path, "b/Same.scala", "package b\nclass Same { def work(): Unit = () }\n")
    assert not _edges(_graph(tmp_path))


def test_unknown_receiver_is_not_guessed_across_packages(tmp_path: Path) -> None:
    _write(
        tmp_path, "Caller.scala", "package app\nclass Caller { def run(x: Any): Unit = x.work() }\n"
    )
    _write(tmp_path, "a.scala", "package a\nclass A { def work(): Unit = () }\n")
    _write(tmp_path, "b.scala", "package b\nclass B { def work(): Unit = () }\n")

    assert not _edges(_graph(tmp_path))


def test_package_index_keeps_package_identity() -> None:
    first = TreeSitterScalaAnalyzer(
        "/repo/a.scala", "package a\nclass Same { def work(): Unit = () }\n", "/repo"
    )
    second = TreeSitterScalaAnalyzer(
        "/repo/b.scala", "package b\nclass Same { def work(): Unit = () }\n", "/repo"
    )
    functions = {node.id: node for node in [*first.nodes, *second.nodes]}
    index = ScalaPackageIndex(functions)
    caller = next(node for node in first.nodes if node.component_type == "method")

    assert index.lookup("a", "Same.work") == "a.scala::Same.work"
    assert index.lookup("b", "Same.work") == "b.scala::Same.work"
    assert resolve_scala_callee(scala_package_ref("a", "Same.work"), caller, index) == (
        "a.scala::Same.work"
    )
    assert resolve_scala_callee(scala_package_ref("missing", "Same.work"), caller, index) is None


def test_sc_extension_reaches_scala_analyzer(tmp_path: Path) -> None:
    _write(tmp_path, "script.sc", 'object Hello { def greet(): String = "hi" }\n')

    components = DependencyParser(str(tmp_path)).parse_repository()

    assert "script.sc::Hello$" in components
    assert "script.sc::Hello$.greet" in components


def test_dependency_parser_preserves_scala_package_identity(tmp_path: Path) -> None:
    _write(tmp_path, "a.scala", "package p\ndef run(): Unit = helper()\n")
    _write(tmp_path, "b.scala", "package p\ndef helper(): Unit = ()\n")

    components = DependencyParser(str(tmp_path)).parse_repository()

    assert components["a.scala::run"].qualified_name == "p.run"
    assert "b.scala::helper" in components["a.scala::run"].depends_on


def test_incremental_change_resolves_into_cached_scala_package(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "app/Caller.scala",
        "package app\nimport lib.Same\nclass Caller { def run(): Unit = () }\n",
    )
    lib_path = _write(
        tmp_path, "lib/Same.scala", "package lib\nclass Same { def work(): Unit = () }\n"
    )
    full = _graph(tmp_path)
    for relationship in full.call_relationships:
        if relationship.is_resolved and relationship.callee in full.functions:
            full.functions[relationship.caller].depends_on.add(relationship.callee)

    _write(
        tmp_path,
        "app/Caller.scala",
        "package app\nimport lib.Same\nclass Caller(x: Same) { def run(): Unit = x.work() }\n",
    )
    incremental = _graph(
        tmp_path,
        skip_file_paths={str(lib_path)},
        cached_components=full.functions,
    )

    assert "lib/Same.scala::Same" in incremental.functions
    assert ("app/Caller.scala::Caller.run", "lib/Same.scala::Same.work") in _edges(incremental)


def test_unchanged_scala_cached_relationships_survive(tmp_path: Path) -> None:
    caller_path = _write(
        tmp_path,
        "Caller.scala",
        "package app\nimport lib.Same\nclass Caller(x: Same) { def run(): Unit = x.work() }\n",
    )
    lib_path = _write(
        tmp_path, "lib/Same.scala", "package lib\nclass Same { def work(): Unit = () }\n"
    )
    full = _graph(tmp_path)
    for relationship in full.call_relationships:
        if relationship.is_resolved and relationship.callee in full.functions:
            full.functions[relationship.caller].depends_on.add(relationship.callee)
    _write(tmp_path, "Other.scala", "package app\nclass Other {}\n")

    incremental = _graph(
        tmp_path,
        skip_file_paths={str(caller_path), str(lib_path)},
        cached_components=full.functions,
    )

    assert ("Caller.scala::Caller.run", "lib/Same.scala::Same.work") in _edges(incremental)


def test_direct_analyzer_does_not_swallow_missing_grammar(tmp_path: Path, monkeypatch) -> None:
    from codewiki.src.be.dependency_analyzer.analyzers import scala as scala_module

    def unavailable(_language: str):
        raise GrammarUnavailableError("scala", RuntimeError("offline"))

    path = _write(tmp_path, "Main.scala", "object Main {}\n")
    monkeypatch.setattr(scala_module, "get_parser", unavailable)

    with pytest.raises(GrammarUnavailableError, match="scala"):
        TreeSitterScalaAnalyzer(str(path), path.read_text(), repo_path=str(tmp_path))


def test_grammar_failure_is_explicit(clear_grammar_cache, monkeypatch) -> None:
    def fail(_language: str):
        raise RuntimeError("grammar shared library missing")

    monkeypatch.setattr(grammars, "_load_language", fail)
    with pytest.raises(GrammarUnavailableError) as info:
        grammars.get_parser("scala")
    assert info.value.language == "scala"
    assert "tree-sitter-scala" in str(info.value)
    assert isinstance(info.value.__cause__, RuntimeError)


def test_analysis_preflights_scala_before_first_file(
    clear_grammar_cache, tmp_path, monkeypatch
) -> None:
    _write(tmp_path, "Main.scala", "object Main {}\n")
    analyzed = []

    def unavailable(_language: str):
        raise GrammarUnavailableError("scala", RuntimeError("offline"))

    monkeypatch.setattr(grammars, "get_parser", unavailable)
    monkeypatch.setattr(
        CallGraphAnalyzer, "_analyze_code_file", lambda self, base, info: analyzed.append(info)
    )
    with pytest.raises(GrammarUnavailableError, match="scala"):
        CallGraphAnalyzer().analyze_code_files(
            [{"path": "Main.scala", "language": "scala"}], str(tmp_path)
        )
    assert analyzed == []


def test_scala_is_registered_across_entry_points(tmp_path: Path) -> None:
    assert {".scala", ".sc"} <= SUPPORTED_EXTENSIONS
    assert EXTENSION_TO_LANGUAGE[".scala"] == "scala"
    assert EXTENSION_TO_LANGUAGE[".sc"] == "scala"
    assert "scala" in AnalysisService()._get_supported_languages()
    assert LANG_BY_EXT[".scala"] == "scala"
    assert classify_artifact("src/main/scala/App.scala") is None
    assert classify_artifact("build.sbt") == "manifest"

    _write(tmp_path, "Main.scala", "object Main {}\n")
    assert detect_supported_languages(tmp_path) == [("Scala", 1)]
    assert _has_source_files(tmp_path)


def test_sbt_manifests_identify_scala_services(tmp_path: Path) -> None:
    _write(tmp_path, "services/a/build.sbt", 'name := "a"\n')
    _write(tmp_path, "services/a/src/main/scala/A.scala", "package a\nobject A {}\n")
    _write(tmp_path, "services/b/build.sbt", 'name := "b"\n')
    _write(tmp_path, "services/b/src/main/scala/B.scala", "package b\nobject B {}\n")

    services = detect_services(tmp_path)

    assert set(services) == {"a", "b"}
    assert all("build-manifest:sbt" in service.source for service in services.values())


def test_scala_fingerprint_cache_detects_added_and_changed_files(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache

    repo = tmp_path / "repo"
    repo.mkdir()
    main = _write(repo, "Main.scala", "object Main {}\n")
    cache = AnalysisCache(repo, db_path=repo / ".codewiki" / "analysis_cache.db")
    try:
        cache.update_file_fingerprints([main.name])
        assert cache.detect_changes() == {
            "changed_files": [],
            "method": "fingerprint",
            "no_changes": True,
        }

        main.write_text("object Main { val x = 1 }\n", encoding="utf-8")
        _write(repo, "Script.sc", "object Script {}\n")
        changed = cache.detect_changes()
        assert changed["method"] == "fingerprint"
        assert set(changed["changed_files"]) == {"Main.scala", "Script.sc"}
    finally:
        cache.close()


def test_scala_mtime_fallback_and_manifest_source_references(tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone

    from codewiki.mcp.tools.analysis import _detect_mtime_from_meta
    from codewiki.mcp.tools.artifact_facts import analyze_artifact_facts

    source = _write(tmp_path, "src/main/scala/App.scala", "object App {}\n")
    _write(tmp_path, "build.sbt", 'Compile / sources += file("src/main/scala/App.scala")\n')
    timestamp = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    changed = _detect_mtime_from_meta(tmp_path, {"generation_info": {"timestamp": timestamp}})
    assert changed == {"changed_files": ["src/main/scala/App.scala"], "method": "mtime"}
    assert source.exists()

    facts = analyze_artifact_facts(tmp_path)
    manifest = next(fact for fact in facts["facts"] if fact["path"] == "build.sbt")
    assert manifest["kind"] == "manifest"
    assert "src/main/scala/App.scala" in {
        reference["value"] for reference in manifest.get("references", [])
    }
    assert all(fact["path"] != "src/main/scala/App.scala" for fact in facts["facts"])


def test_static_style_call_uses_companion_not_class_instance_method(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Caller.scala",
        'package app\nimport lib.Logger\nobject Caller { def run(): Unit = Logger.warn("x") }\n',
    )
    _write(
        tmp_path,
        "lib/Logger.scala",
        "package lib\nclass Logger { def warn(s: String): Unit = () }\n",
    )

    assert not _edges(_graph(tmp_path))

    _write(
        tmp_path,
        "lib/Logger.scala",
        "package lib\nclass Logger { def warn(s: String): Unit = () }\nobject Logger { def warn(s: String): Unit = () }\n",
    )
    graph = _graph(tmp_path)
    assert ("Caller.scala::Caller$.run", "lib/Logger.scala::Logger$.warn") in _edges(graph)
    assert ("Caller.scala::Caller$.run", "lib/Logger.scala::Logger.warn") not in _edges(graph)


def test_wildcard_bare_call_does_not_bind_ambiguous_packages(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Caller.scala",
        "package app\nimport a._\nimport b._\ndef run(): Unit = helper()\n",
    )
    _write(tmp_path, "a.scala", "package a\ndef helper(): Unit = ()\n")
    _write(tmp_path, "b.scala", "package b\ndef helper(): Unit = ()\n")

    assert not _edges(_graph(tmp_path))


def test_watch_incremental_refresh_resolves_cached_scala_package(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.mcp.tools.watch import _incremental_refresh

    _write(
        tmp_path,
        "app/Caller.scala",
        "package app\nimport lib.Same\nclass Caller { def run(): Unit = () }\n",
    )
    lib_path = _write(
        tmp_path, "lib/Same.scala", "package lib\nclass Same { def work(): Unit = () }\n"
    )
    full = _graph(tmp_path)
    cache = AnalysisCache(tmp_path, db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.batch_insert_components(full.functions, [], incremental=False)
        _write(
            tmp_path,
            "app/Caller.scala",
            "package app\nimport lib.Same\nclass Caller(x: Same) { def run(): Unit = x.work() }\n",
        )
        components, _, routes = _incremental_refresh(
            str(tmp_path),
            str(tmp_path / "repowiki"),
            cache,
            ["app/Caller.scala"],
        )

        assert "lib/Same.scala::Same" in components
        assert "lib/Same.scala::Same.work" in components["app/Caller.scala::Caller.run"].depends_on
        assert routes == []
        assert lib_path.exists()
    finally:
        cache.close()


def test_cached_scala_edge_is_dropped_when_target_package_changes(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.mcp.tools.watch import _incremental_refresh

    _write(
        tmp_path,
        "app/Caller.scala",
        "package app\nimport lib.Same\nclass Caller(x: Same) { def run(): Unit = x.work() }\n",
    )
    _write(tmp_path, "lib/Same.scala", "package lib\nclass Same { def work(): Unit = () }\n")
    full = _graph(tmp_path)
    cache = AnalysisCache(tmp_path, db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.batch_insert_components(full.functions, [], incremental=False)
        _write(
            tmp_path,
            "lib/Same.scala",
            "package moved\nclass Same { def work(): Unit = () }\n",
        )
        components, _, _ = _incremental_refresh(
            str(tmp_path),
            str(tmp_path / "repowiki"),
            cache,
            ["lib/Same.scala"],
        )

        assert components["lib/Same.scala::Same.work"].qualified_name == "moved.Same.work"
        assert "lib/Same.scala::Same" not in components["app/Caller.scala::Caller"].depends_on
        assert (
            "lib/Same.scala::Same.work" not in components["app/Caller.scala::Caller.run"].depends_on
        )
    finally:
        cache.close()


def test_overloaded_methods_do_not_collide_or_bind(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Overload.scala",
        "class Overload { def f(x: Int): Int = x; def f(s: String): String = s }\n",
    )
    _write(
        tmp_path,
        "Caller.scala",
        "class Caller { def run(o: Overload): Int = o.f(1) }\n",
    )

    graph = _graph(tmp_path)
    assert "Overload.scala::Overload.f" not in graph.functions
    assert not any(rel.callee == "Overload.scala::Overload.f" for rel in graph.call_relationships)


def test_block_local_receiver_types_follow_lexical_scope(tmp_path: Path) -> None:
    _write(tmp_path, "A.scala", "class A { def go(): Unit = () }\n")
    _write(tmp_path, "B.scala", "class B { def go(): Unit = () }\n")
    _write(
        tmp_path,
        "Caller.scala",
        "class Caller { def run(): Unit = { { val x: A = new A; x.go() }; { val x: B = new B; x.go() } } }\n",
    )

    edges = _edges(_graph(tmp_path))
    assert ("Caller.scala::Caller.run", "A.scala::A.go") in edges
    assert ("Caller.scala::Caller.run", "B.scala::B.go") in edges


def test_explicitly_imported_bare_call_resolves(tmp_path: Path) -> None:
    _write(tmp_path, "util.scala", "package util\ndef helper(): Unit = ()\n")
    _write(
        tmp_path,
        "Caller.scala",
        "package app\nimport util.helper\ndef run(): Unit = helper()\n",
    )

    assert ("Caller.scala::run", "util.scala::helper") in _edges(_graph(tmp_path))


def test_cached_nested_type_and_companion_keep_logical_identity(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.mcp.tools.watch import _incremental_refresh

    _write(
        tmp_path,
        "Outer.scala",
        "package lib\nclass Outer { trait Base; object Inner { def run(): Unit = () } }\n",
    )
    _write(tmp_path, "Consumer.scala", "package app\nclass Consumer\n")
    full = _graph(tmp_path)
    cache = AnalysisCache(tmp_path, db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.batch_insert_components(full.functions, [], incremental=False)
        _write(
            tmp_path,
            "Consumer.scala",
            "package app\nimport lib.Outer\nclass Consumer extends Outer.Base { def run(): Unit = Outer.Inner.run() }\n",
        )
        components, _, _ = _incremental_refresh(
            str(tmp_path), str(tmp_path / "repowiki"), cache, ["Consumer.scala"]
        )

        assert "Outer.scala::Outer.Base" in components["Consumer.scala::Consumer"].depends_on
        assert (
            "Outer.scala::Outer.Inner$.run" in components["Consumer.scala::Consumer.run"].depends_on
        )
    finally:
        cache.close()


def test_new_wildcard_symbol_invalidates_cached_bare_call_edge(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.mcp.tools.watch import _incremental_refresh

    _write(
        tmp_path,
        "Caller.scala",
        "package app\nimport a._\nimport b._\ndef run(): Unit = helper()\n",
    )
    _write(tmp_path, "a/Helper.scala", "package a\ndef helper(): Unit = ()\n")
    full = _graph(tmp_path)
    for relationship in full.call_relationships:
        if relationship.is_resolved:
            full.functions[relationship.caller].depends_on.add(relationship.callee)
    cache = AnalysisCache(tmp_path, db_path=tmp_path / ".codewiki" / "analysis_cache.db")
    try:
        cache.batch_insert_components(full.functions, [], incremental=False)
        _write(tmp_path, "b/Helper.scala", "package b\ndef helper(): Unit = ()\n")
        components, _, _ = _incremental_refresh(
            str(tmp_path), str(tmp_path / "repowiki"), cache, ["b/Helper.scala"]
        )

        assert "a/Helper.scala::helper" not in components["Caller.scala::run"].depends_on
    finally:
        cache.close()


def test_inherited_bare_method_precedes_top_level_function(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Caller.scala",
        "trait B { def f(): Unit = () }; class C extends B { def run(): Unit = f() }; def f(): Unit = ()\n",
    )

    edges = _edges(_graph(tmp_path))
    assert ("Caller.scala::C.run", "Caller.scala::B.f") in edges
    assert ("Caller.scala::C.run", "Caller.scala::f") not in edges


def test_super_call_resolves_base_not_overriding_child(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Caller.scala",
        "class B { def f(): Unit = () }; class C extends B { override def f(): Unit = (); def run(): Unit = super.f() }\n",
    )

    edges = _edges(_graph(tmp_path))
    assert ("Caller.scala::C.run", "Caller.scala::B.f") in edges
    assert ("Caller.scala::C.run", "Caller.scala::C.f") not in edges


def test_fully_qualified_inherited_base_keeps_package_identity(tmp_path: Path) -> None:
    _write(tmp_path, "app/B.scala", "package app\nclass B { def f(): Unit = () }\n")
    _write(tmp_path, "lib/B.scala", "package lib\ntrait B { def f(): Unit = () }\n")
    _write(
        tmp_path,
        "app/Caller.scala",
        "package app\nclass B { def f(): Unit = () }\nclass C extends lib.B { def run(): Unit = f() }\n",
    )

    edges = _edges(_graph(tmp_path))
    assert ("app/Caller.scala::C.run", "lib/B.scala::B.f") in edges
    assert ("app/Caller.scala::C.run", "app/B.scala::B.f") not in edges


def test_inherited_base_without_method_falls_back_to_top_level(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Caller.scala",
        "trait B {}; class C extends B { def run(): Unit = f() }; def f(): Unit = ()\n",
    )

    assert ("Caller.scala::C.run", "Caller.scala::f") in _edges(_graph(tmp_path))


def test_wildcard_inherited_base_fallback_keeps_candidate_group(tmp_path: Path) -> None:
    _write(tmp_path, "a/B.scala", "package a\ntrait B { def f(): Unit = () }\n")
    _write(
        tmp_path,
        "app/Caller.scala",
        "package app\nimport a._\nimport b._\nclass C extends B { def run(): Unit = f() }; def f(): Unit = ()\n",
    )

    edges = _edges(_graph(tmp_path))
    assert ("app/Caller.scala::C.run", "a/B.scala::B.f") in edges
    assert ("app/Caller.scala::C.run", "app/Caller.scala::f") not in edges


def test_overloaded_companion_apply_does_not_fall_back_to_class(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Factory.scala",
        "class F; object F { def apply(x: Int): F = new F; def apply(s: String): F = new F }\n",
    )
    _write(tmp_path, "Caller.scala", "class Caller { def run(): Unit = { F(1); () } }\n")

    assert not _edges(_graph(tmp_path))


def test_typed_receiver_field_chain_is_not_a_package_path(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Types.scala",
        "package app\nclass Child { def go(): Unit = () }; class H(val c: Child)\n",
    )
    _write(
        tmp_path,
        "Caller.scala",
        "package app\nclass Caller { def run(h: H): Unit = h.c.go() }\n",
    )

    assert ("Caller.scala::Caller.run", "Types.scala::Child.go") in _edges(_graph(tmp_path))


def test_imported_constructor_field_chain_keeps_package_identity(tmp_path: Path) -> None:
    _write(tmp_path, "other/Child.scala", "package other\nclass Child { def go(): Unit = () }\n")
    _write(
        tmp_path,
        "Types.scala",
        "package app\nimport other.Child\nclass Child { def go(): Unit = () }; class H(val c: Child)\n",
    )
    _write(
        tmp_path,
        "Caller.scala",
        "package app\nclass Caller { def run(h: H): Unit = h.c.go() }\n",
    )

    edges = _edges(_graph(tmp_path))
    assert ("Caller.scala::Caller.run", "other/Child.scala::Child.go") in edges
    assert ("Caller.scala::Caller.run", "Types.scala::Child.go") not in edges


def test_empty_and_bad_syntax_do_not_crash(tmp_path: Path) -> None:
    assert _analyze(tmp_path, "", "empty.scala") == ([], [])
    nodes, relationships = _analyze(tmp_path, "class Broken( {{{ def", "broken.scala")
    assert isinstance(nodes, list)
    assert isinstance(relationships, list)
