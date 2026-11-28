"""Ruby analyzer: namespace identity, ordered receiver inference and dispatch."""

from pathlib import Path

import pytest

from codewiki.cli.utils.repo_validator import SUPPORTED_EXTENSIONS
from codewiki.cli.utils.validation import detect_supported_languages
from codewiki.src.be.dependency_analyzer.analysis.analysis_service import AnalysisService
from codewiki.src.be.dependency_analyzer.analysis.call_graph_analyzer import CallGraphAnalyzer
from codewiki.src.be.dependency_analyzer.analyzers.ruby import analyze_ruby_file
from codewiki.src.be.dependency_analyzer.ast_parser import DependencyParser
from codewiki.src.be.dependency_analyzer.utils import grammars
from codewiki.src.be.dependency_analyzer.utils.grammars import (
    GrammarUnavailableError,
    ensure_grammars,
    get_parser,
)
from codewiki.src.be.prompt_template import EXTENSION_TO_LANGUAGE


SAMPLE = """\
# A namespace with two independent workers.
module Shop
  class Worker
    include Runnable

    def initialize(name)
      @name = name
    end

    def run(logger = Logger.new)
      prepare()
      logger.record(@name)
    end

    def prepare
      notify()
    end

    def notify
      puts("ready")
    end
  end

  class Logger
    def record(message)
      validate(message)
    end

    def validate(message); end
  end
end
"""


def _analyze(tmp_path: Path, source: str = SAMPLE, name: str = "shop.rb"):
    file_path = tmp_path / name
    file_path.write_text(source, encoding="utf-8")
    return analyze_ruby_file(str(file_path), source, repo_path=str(tmp_path))


def _edges(relationships) -> set[tuple[str, str]]:
    return {(relationship.caller, relationship.callee) for relationship in relationships}


@pytest.fixture
def clear_grammar_cache():
    grammars.get_language.cache_clear()
    yield
    grammars.get_language.cache_clear()


def test_components_keep_full_namespace_and_ruby_method_identity(tmp_path: Path) -> None:
    nodes, _ = _analyze(tmp_path)
    by_name = {node.name: node for node in nodes}

    assert "Shop.Worker#run" in by_name
    assert by_name["Shop.Worker#run"].component_type == "method"
    assert by_name["Shop.Worker#run"].class_name == "Shop.Worker"
    assert by_name["Shop.Worker#run"].qualified_name == "Shop::Worker#run"
    assert by_name["Shop.Worker#run"].id == "shop.rb::Shop.Worker#run"


def test_same_bare_class_in_different_namespaces_does_not_collide(tmp_path: Path) -> None:
    source = """\
module A
  class Item
    def run; end
  end
end
module B
  class Item
    def run; end
  end
end
"""
    nodes, _ = _analyze(tmp_path, source)
    names = {node.name for node in nodes}

    assert {"A.Item", "B.Item", "A.Item#run", "B.Item#run"} <= names
    assert len({node.id for node in nodes}) == len(nodes)


def test_reopened_class_keeps_one_component_identity(tmp_path: Path) -> None:
    source = """\
class A
  def first; end
end
class A
  def second; end
end
"""
    nodes, _ = _analyze(tmp_path, source)

    assert sum(node.name == "A" for node in nodes) == 1
    assert {"A#first", "A#second"} <= {node.name for node in nodes}


def test_instance_and_singleton_methods_with_same_name_do_not_collide(tmp_path: Path) -> None:
    source = """\
class A
  def run; end
  def self.run; end
end
"""
    nodes, _ = _analyze(tmp_path, source)

    assert {"A#run", "A.run"} == {node.name for node in nodes if node.component_type == "method"}
    assert len({node.id for node in nodes}) == len(nodes)


def test_singleton_class_and_explicit_owner_methods(tmp_path: Path) -> None:
    source = """\
class A
  class << self
    def build; end
  end
end
def B.run; end
"""
    nodes, _ = _analyze(tmp_path, source)

    assert {"A.build", "B.run"} <= {node.name for node in nodes}


def test_calls_stay_within_their_owner(tmp_path: Path) -> None:
    source = """\
class A
  def self.run; helper(); end
  def self.helper; end
end
class B
  def self.run; helper(); end
  def self.helper; end
end
"""
    _, relationships = _analyze(tmp_path, source, "run.rb")
    edges = _edges(relationships)

    assert ("run.rb::A.run", "run.rb::A.helper") in edges
    assert ("run.rb::B.run", "run.rb::B.helper") in edges
    assert ("run.rb::A.run", "run.rb::B.helper") not in edges
    assert ("run.rb::B.run", "run.rb::A.helper") not in edges


def test_receiver_uses_latest_preceding_assignment(tmp_path: Path) -> None:
    source = """\
class A
  def go; end
end
class B
  def go; end
end
def run
  x = A.new
  x.go
  x = B.new
  x.go
end
"""
    _, relationships = _analyze(tmp_path, source, "run.rb")
    edges = _edges(relationships)

    assert ("run.rb::#run", "run.rb::A#go") in edges
    assert ("run.rb::#run", "run.rb::B#go") in edges


def test_call_before_assignment_does_not_bind_future_type(tmp_path: Path) -> None:
    source = """\
class A
  def go; end
end
def run
  x.go
  x = A.new
end
"""
    _, relationships = _analyze(tmp_path, source)

    assert not any(callee == "run.rb::A#go" for _, callee in _edges(relationships))


def test_unknown_reassignment_clears_previous_type(tmp_path: Path) -> None:
    source = """\
class A
  def go; end
end
def run
  x = A.new
  x = unknown
  x.go
end
"""
    _, relationships = _analyze(tmp_path, source)

    assert not any(callee == "run.rb::A#go" for _, callee in _edges(relationships))


def test_block_parameter_shadows_outer_receiver(tmp_path: Path) -> None:
    source = """\
class A
  def go; end
end
def run
  x = A.new
  [1].each do |x|
    x.go
  end
  x.go
end
"""
    _, relationships = _analyze(tmp_path, source, "run.rb")
    edges = _edges(relationships)

    assert ("run.rb::#run", "run.rb::A#go") in edges
    assert sum(callee == "run.rb::A#go" for _, callee in edges) == 1


def test_conditional_assignment_is_not_treated_as_definite(tmp_path: Path) -> None:
    source = """\
class A
  def go; end
end
def run(flag)
  if flag
    x = A.new
  end
  x.go
end
"""
    _, relationships = _analyze(tmp_path, source)

    assert not any(callee == "run.rb::A#go" for _, callee in _edges(relationships))


def test_constructor_chain_and_constant_receiver_edges(tmp_path: Path) -> None:
    source = """\
class A
  def go; end
  def self.build; A.new; end
end
def run
  A.new.go
  A.build
end
"""
    _, relationships = _analyze(tmp_path, source, "run.rb")
    edges = _edges(relationships)

    assert ("run.rb::#run", "run.rb::A") in edges
    assert ("run.rb::#run", "run.rb::A#go") in edges
    assert ("run.rb::#run", "run.rb::A.build") in edges


def test_project_names_that_look_like_ruby_core_are_kept(tmp_path: Path) -> None:
    source = """\
class String
  def map; end
end
class JSON
  def send; end
end
def run
  String.new.map
  JSON.new.send
end
"""
    _, relationships = _analyze(tmp_path, source, "run.rb")
    edges = _edges(relationships)

    assert ("run.rb::#run", "run.rb::String#map") in edges
    assert ("run.rb::#run", "run.rb::JSON#send") in edges


def test_qualified_calls_do_not_fall_back_to_another_class(tmp_path: Path) -> None:
    source = """\
class A
  def self.run; end
end
class B
  def self.run; end
end
def execute
  Missing.run
end
"""
    analyzer = CallGraphAnalyzer()
    nodes, relationships = _analyze(tmp_path, source)
    for node in nodes:
        analyzer.functions[node.id] = node
    analyzer.call_relationships.extend(relationships)
    analyzer._resolve_call_relationships()

    assert not any(
        relationship.callee in {"run.rb::A.run", "run.rb::B.run"}
        for relationship in analyzer.call_relationships
    )


def test_cross_file_qualified_names_resolve_without_tail_guessing(tmp_path: Path) -> None:
    (tmp_path / "a.rb").write_text("class A; def self.run; end; end\n", encoding="utf-8")
    (tmp_path / "b.rb").write_text("class B; def self.run; end; end\n", encoding="utf-8")
    (tmp_path / "main.rb").write_text("def execute; A.run; end\n", encoding="utf-8")
    components = DependencyParser(str(tmp_path)).parse_repository()

    assert "a.rb::A" in components
    assert "a.rb::A.run" in components["main.rb::#execute"].depends_on


def test_inheritance_mixins_and_require_relative(tmp_path: Path) -> None:
    source = """\
module App
  class Base; end
  module Runnable; end
  class Worker < Base
    include Runnable
    require_relative "support/helper"
    def run; end
  end
end
"""
    _, relationships = _analyze(tmp_path, source, "app.rb")
    edges = _edges(relationships)

    assert ("app.rb::App.Worker", "app.rb::App.Base") in edges
    assert ("app.rb::App.Worker", "app.rb::App.Runnable") in edges
    assert any(callee == "require_relative:support/helper" for _, callee in edges)


def test_parameters_docstring_and_source_locations(tmp_path: Path) -> None:
    nodes, _ = _analyze(tmp_path)
    run = next(node for node in nodes if node.name == "Shop.Worker#run")

    assert run.parameters == ["logger = Logger.new"]
    assert run.language == "ruby"
    assert run.file_path.endswith("shop.rb")
    assert run.relative_path == "shop.rb"
    assert run.start_line == 10
    assert run.end_line == 13
    assert "def run" in run.source_code
    worker = next(node for node in nodes if node.name == "Shop")
    assert worker.has_docstring
    assert "namespace" in worker.docstring


def test_implicit_bare_identifier_resolves_only_known_method(tmp_path: Path) -> None:
    source = """\
class A
  def run
    helper
    unknown_name
  end
  def helper; end
end
"""
    _, relationships = _analyze(tmp_path, source, "bare.rb")
    edges = _edges(relationships)

    assert ("bare.rb::A#run", "bare.rb::A#helper") in edges
    assert not any(callee.endswith("unknown_name") for _, callee in edges)


def test_dynamic_dispatch_and_attribute_macros_do_not_invent_methods(tmp_path: Path) -> None:
    source = """\
class A
  attr_accessor :name
  define_method(:run) { helper }
  def execute(target)
    target.send(:run)
    public_send(:run)
  end
end
"""
    nodes, relationships = _analyze(tmp_path, source)
    names = {node.name for node in nodes}

    assert "A#name" not in names
    assert "A#run" not in names
    assert not any(callee.endswith("#run") for _, callee in _edges(relationships))


def test_conditional_unknown_reassignment_clears_previous_type(tmp_path: Path) -> None:
    source = """\
class A
  def go; end
end
def run(flag)
  x = A.new
  x = unknown if flag
  x.go
end
"""
    _, relationships = _analyze(tmp_path, source, "conditional_reassign.rb")

    assert not any(callee == "conditional_reassign.rb::A#go" for _, callee in _edges(relationships))


def test_method_does_not_capture_class_body_local(tmp_path: Path) -> None:
    source = """\
class A
  def go; end
end
class B
  x = A.new
  def run
    x.go
  end
end
"""
    _, relationships = _analyze(tmp_path, source, "def_boundary.rb")

    assert not any(callee == "def_boundary.rb::A#go" for _, callee in _edges(relationships))


def test_relative_qualified_constant_prefers_lexical_namespace(tmp_path: Path) -> None:
    source = """\
module C
  module A
    class B
      def self.go; end
    end
  end
  def self.run
    A::B.go
  end
end
module A
  class B
    def self.go; end
  end
end
"""
    _, relationships = _analyze(tmp_path, source, "lexical.rb")
    edges = _edges(relationships)

    assert ("lexical.rb::C.run", "lexical.rb::C.A.B.go") in edges
    assert ("lexical.rb::C.run", "lexical.rb::A.B.go") not in edges


def test_singleton_class_with_explicit_object_uses_that_owner(tmp_path: Path) -> None:
    source = """\
class A
  class << Other
    def go; end
  end
end
"""
    nodes, _ = _analyze(tmp_path, source, "singleton_object.rb")

    assert "Other.go" in {node.name for node in nodes}
    assert "A.go" not in {node.name for node in nodes}


def test_destructured_block_parameter_shadows_all_names(tmp_path: Path) -> None:
    source = """\
class A
  def go; end
end
def run
  y = A.new
  [1].each { |(x, y)| y.go }
end
"""
    _, relationships = _analyze(tmp_path, source, "destructured.rb")

    assert not any(callee == "destructured.rb::A#go" for _, callee in _edges(relationships))


def test_direct_analyzer_does_not_swallow_missing_grammar(tmp_path: Path, monkeypatch) -> None:
    from codewiki.src.be.dependency_analyzer.analyzers import ruby as ruby_module

    def unavailable(_language):
        raise GrammarUnavailableError("ruby", RuntimeError("offline"))

    monkeypatch.setattr(ruby_module, "get_parser", unavailable)
    with pytest.raises(GrammarUnavailableError, match="ruby"):
        analyze_ruby_file(str(tmp_path / "main.rb"), "puts 'ok'\n", str(tmp_path))


def test_bad_syntax_and_empty_file_do_not_crash(tmp_path: Path) -> None:
    assert _analyze(tmp_path, "", "empty.rb") == ([], [])
    nodes, _ = _analyze(tmp_path, "class Broken( {{{ def", "broken.rb")
    assert isinstance(nodes, list)


def test_ruby_is_registered_across_entry_points() -> None:
    assert ".rb" in SUPPORTED_EXTENSIONS
    assert EXTENSION_TO_LANGUAGE[".rb"] == "ruby"
    assert "ruby" in AnalysisService()._get_supported_languages()


def test_cli_detects_ruby(tmp_path: Path) -> None:
    (tmp_path / "main.rb").write_text("puts 'ok'\n", encoding="utf-8")

    assert detect_supported_languages(tmp_path) == [("Ruby", 1)]


def test_grammar_preflight_loads_ruby_once(clear_grammar_cache, monkeypatch) -> None:
    loaded = []
    original = grammars.get_parser

    def tracking(language):
        loaded.append(language)
        return original(language)

    monkeypatch.setattr(grammars, "get_parser", tracking)
    ensure_grammars(["ruby", "rust", "ruby", "unknown"])

    assert loaded == ["ruby", "rust"]
    assert get_parser("ruby") is not None


def test_missing_ruby_grammar_fails_before_first_file(
    clear_grammar_cache, tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "main.rb").write_text("puts 'ok'\n", encoding="utf-8")

    def unavailable(language):
        raise GrammarUnavailableError(language, RuntimeError("offline"))

    monkeypatch.setattr(grammars, "get_parser", unavailable)
    analyzer = CallGraphAnalyzer()
    with pytest.raises(GrammarUnavailableError, match="ruby"):
        analyzer.analyze_code_files([{"path": "main.rb", "language": "ruby"}], str(tmp_path))


def test_qualified_declaration_keeps_lexical_namespace(tmp_path: Path) -> None:
    source = """\
module A
  class B; end
  class B::C
    def run; end
  end
end
class B
  class C
    def run; end
  end
end
"""
    nodes, _ = _analyze(tmp_path, source, "qualified_decl.rb")
    names = {node.name for node in nodes}

    assert {"A.B.C", "B.C", "A.B.C#run", "B.C#run"} <= names
    assert len({node.id for node in nodes}) == len(nodes)


def test_absolute_qualified_declaration_stays_at_top_level(tmp_path: Path) -> None:
    source = """\
module A
  class ::B
    def run; end
  end
end
"""
    nodes, _ = _analyze(tmp_path, source, "absolute_decl.rb")

    assert {"B", "B#run"} <= {node.name for node in nodes}
    assert "A.B" not in {node.name for node in nodes}


def test_top_level_instance_and_singleton_methods_do_not_collide(tmp_path: Path) -> None:
    nodes, _ = _analyze(
        tmp_path,
        "def run; end\ndef self.run; end\n",
        "top_level.rb",
    )

    assert {"#run", ".run"} == {node.name for node in nodes if node.component_type == "method"}
    assert len({node.id for node in nodes}) == len(nodes)


def test_cross_file_bare_instance_call_keeps_instance_identity(tmp_path: Path) -> None:
    (tmp_path / "a.rb").write_text("class A; def helper; end; end\n", encoding="utf-8")
    (tmp_path / "b.rb").write_text("class A; def run; helper; end; end\n", encoding="utf-8")
    components = DependencyParser(str(tmp_path)).parse_repository()

    assert "a.rb::A#helper" in components["b.rb::A#run"].depends_on


def test_cross_file_bare_singleton_call_keeps_singleton_identity(tmp_path: Path) -> None:
    (tmp_path / "a.rb").write_text("class A; def self.helper; end; end\n", encoding="utf-8")
    (tmp_path / "b.rb").write_text("class A; def self.run; helper; end; end\n", encoding="utf-8")
    components = DependencyParser(str(tmp_path)).parse_repository()

    assert "a.rb::A.helper" in components["b.rb::A.run"].depends_on
    assert "a.rb::A#helper" not in components["b.rb::A.run"].depends_on


def test_cross_file_top_level_bare_call_keeps_instance_identity(tmp_path: Path) -> None:
    (tmp_path / "a.rb").write_text("def helper; end\n", encoding="utf-8")
    (tmp_path / "b.rb").write_text("def run; helper; end\n", encoding="utf-8")
    components = DependencyParser(str(tmp_path)).parse_repository()

    assert "a.rb::#helper" in components["b.rb::#run"].depends_on


def test_destructured_assignment_names_are_not_calls(tmp_path: Path) -> None:
    source = """\
def y; end
def run
  x, y = 1, 2
end
"""
    _, relationships = _analyze(tmp_path, source, "destructured_assignment.rb")

    assert not any(
        callee in {"destructured_assignment.rb::y", "destructured_assignment.rb::#y"}
        for _, callee in _edges(relationships)
    )


def test_operator_assignment_does_not_preserve_definite_receiver_type(
    tmp_path: Path,
) -> None:
    source = """\
class A
  def go; end
end
class B
  def go; end
end
def run
  x = A.new
  x &&= B.new
  x.go
end
"""
    _, relationships = _analyze(tmp_path, source, "operator_assignment.rb")

    assert not any(
        callee in {"operator_assignment.rb::A#go", "operator_assignment.rb::B#go"}
        for _, callee in _edges(relationships)
    )


def test_cross_file_superclass_uses_enclosing_namespace(tmp_path: Path) -> None:
    (tmp_path / "a.rb").write_text(
        "class Base; end\nmodule Derived; class Base; end; end\n",
        encoding="utf-8",
    )
    (tmp_path / "b.rb").write_text("class Derived < Base; end\n", encoding="utf-8")
    components = DependencyParser(str(tmp_path)).parse_repository()

    assert "a.rb::Base" in components["b.rb::Derived"].depends_on
    assert "a.rb::Derived.Base" not in components["b.rb::Derived"].depends_on
    nodes, _ = _analyze(tmp_path, "class Derived < Base; end\n", "b.rb")
    assert next(node for node in nodes if node.name == "Derived").base_classes == ["Base"]


def test_splat_block_parameter_shadows_outer_receiver(tmp_path: Path) -> None:
    source = """\
class A
  def go; end
end
def run
  x = A.new
  [1].each { |*x| x.go }
end
"""
    _, relationships = _analyze(tmp_path, source, "splat_block.rb")

    assert not any(callee == "splat_block.rb::A#go" for _, callee in _edges(relationships))


def test_known_lexical_namespace_does_not_fall_back_to_global_nested_constant(
    tmp_path: Path,
) -> None:
    source = """\
module C
  module A; end
  def self.run
    A::B.go
  end
end
module A
  class B
    def self.go; end
  end
end
"""
    _, relationships = _analyze(tmp_path, source, "namespace_fallback.rb")

    assert not any(callee == "namespace_fallback.rb::A.B.go" for _, callee in _edges(relationships))


@pytest.mark.parametrize("suffix", [".rb", ".rs"])
def test_new_languages_participate_in_fingerprint_cache(tmp_path: Path, suffix: str) -> None:
    from codewiki.mcp.cache import AnalysisCache

    repo = tmp_path / "repo"
    repo.mkdir()
    main = repo / f"main{suffix}"
    other = repo / f"other{suffix}"
    main.write_text("def main; end\n", encoding="utf-8")
    other.write_text("def other; end\n", encoding="utf-8")
    cache = AnalysisCache(repo, db_path=repo / ".codewiki" / "analysis_cache.db")
    try:
        cache.update_file_fingerprints([main.name, other.name])
        assert cache.detect_changes() == {
            "changed_files": [],
            "method": "fingerprint",
            "no_changes": True,
        }

        other.write_text("def other; helper; end\n", encoding="utf-8")
        assert cache.detect_changes() == {
            "changed_files": [other.name],
            "method": "fingerprint",
        }
    finally:
        cache.close()
