"""Rust analyzer and grammar preflight regression tests."""

from pathlib import Path

import pytest

from codewiki.src.be.dependency_analyzer.analysis.analysis_service import AnalysisService
from codewiki.src.be.dependency_analyzer.analysis.call_graph_analyzer import CallGraphAnalyzer
from codewiki.src.be.dependency_analyzer.analyzers.rust import analyze_rust_file
from codewiki.src.be.dependency_analyzer.ast_parser import DependencyParser
from codewiki.src.be.dependency_analyzer.utils import grammars
from codewiki.src.be.dependency_analyzer.utils.grammars import (
    GrammarUnavailableError,
    ensure_grammars,
    get_parser,
)

SAMPLE = """\
use std::collections::HashMap;

/// Base contract for buffers that can be flushed.
pub trait Flushable {
    fn flush(&mut self);
}

/// Structured logger used by buffers.
pub struct Logger;

impl Logger {
    pub fn new() -> Self {
        Logger
    }

    pub fn warn(&self, message: &str) {}
}

pub struct Event {
    pub id: u64,
}

pub enum Signal {
    Stop,
    Emit(Event),
}

/// Buffers events before flushing them downstream.
#[derive(Debug, Clone)]
pub struct Buffer<T> {
    capacity: usize,
    logger: Logger,
    items: Vec<T>,
    index: HashMap<u64, Event>,
}

impl<T> Buffer<T> {
    pub fn new(capacity: usize) -> Self {
        Self::with_logger(capacity, Logger::new())
    }

    fn with_logger(capacity: usize, logger: Logger) -> Self {
        Buffer { capacity, logger, items: Vec::new(), index: HashMap::new() }
    }

    pub fn push(&mut self, item: T) {
        self.validate();
        self.logger.warn("pushed");
        let local = Logger::new();
        local.warn("local");
        let event = Event { id: 1 };
        record(&event);
        external_service::ping();
        self.items.push(item);
        std::mem::drop(event);
    }

    fn validate(&self) -> bool {
        self.items.len().checked_add(1).unwrap() <= self.capacity
    }
}

impl<T> Flushable for Buffer<T> {
    fn flush(&mut self) {
        self.items.clear();
    }
}

pub fn record(event: &Event) {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pushes() {
        let mut buffer: Buffer<u8> = Buffer::new(4);
        buffer.push(1);
    }
}
"""


def _analyze(tmp_path: Path, source: str = SAMPLE, name: str = "buffer.rs"):
    file_path = tmp_path / name
    file_path.write_text(source, encoding="utf-8")
    return analyze_rust_file(str(file_path), source, repo_path=str(tmp_path))


def _edges(relationships) -> set[tuple[str, str]]:
    return {(r.caller, r.callee) for r in relationships}


@pytest.fixture
def clear_grammar_cache():
    grammars.get_language.cache_clear()
    yield
    grammars.get_language.cache_clear()


def test_external_and_unknown_calls_keep_their_identity(tmp_path: Path) -> None:
    source = """\
fn spawn() {}
fn run() {}
fn execute() {
    spawn();
    tokio::spawn();
    unknown.run();
}
"""
    _, relationships = _analyze(tmp_path, source, "execute.rs")
    edges = {(r.caller, r.callee, r.is_resolved) for r in relationships}

    assert ("execute.rs::execute", "execute.rs::spawn", True) in edges
    assert ("execute.rs::execute", "tokio::spawn", False) in edges
    assert not any(callee == "execute.rs::run" for _, callee, _ in edges)

    graph = CallGraphAnalyzer()
    file_path = tmp_path / "execute.rs"
    graph._analyze_rust_file(str(file_path), source, str(tmp_path))
    graph._resolve_call_relationships()
    global_callees = {rel.callee for rel in graph.call_relationships}
    assert "execute.rs::spawn" in global_callees
    assert "tokio::spawn" in global_callees
    assert "execute.rs::run" not in global_callees


def test_qualified_types_modules_and_imports_resolve(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.rs").write_text(
        "pub struct Config {}\npub fn helper() {}\nimpl crate::a::Config { pub fn build() {} }\n",
        encoding="utf-8",
    )
    (src / "b.rs").write_text(
        "pub struct Config {}\npub fn helper() {}\n",
        encoding="utf-8",
    )
    (src / "lib.rs").write_text(
        "mod a;\nmod b;\nuse crate::a::{Config as C, helper};\n"
        "pub fn run() { a::helper(); b::helper(); let c = C {}; c.build(); }\n",
        encoding="utf-8",
    )

    components = DependencyParser(str(tmp_path)).parse_repository()

    assert "src/a.rs::a.Config.build" in components
    run = components["src/lib.rs::run"]
    assert "src/a.rs::a.helper" in run.depends_on
    assert "src/b.rs::b.helper" in run.depends_on
    assert "src/a.rs::a.Config" in run.depends_on
    assert "src/a.rs::a.Config.build" in run.depends_on


def test_inline_modules_keep_outer_to_inner_order(tmp_path: Path) -> None:
    source = """\
mod a {
    mod b { pub fn f() {} }
    pub fn run() { b::f(); }
}
"""
    nodes, relationships = _analyze(tmp_path, source, "nested_modules.rs")
    names = {node.name for node in nodes}

    assert {"a.b.f", "a.run"} <= names
    assert ("nested_modules.rs::a.run", "nested_modules.rs::a.b.f") in _edges(relationships)


def test_imports_are_scoped_to_their_module(tmp_path: Path) -> None:
    source = """\
mod a {
    use crate::x::Foo;
    pub fn make() { let _ = Foo {}; }
}
mod b {
    use crate::y::Foo;
    pub fn make() { let _ = Foo {}; }
}
mod x { pub struct Foo; }
mod y { pub struct Foo; }
"""
    nodes, relationships = _analyze(tmp_path, source, "scoped_imports.rs")
    names = {node.name for node in nodes}
    edges = _edges(relationships)

    assert {"x.Foo", "y.Foo", "a.make", "b.make"} <= names
    assert ("scoped_imports.rs::a.make", "scoped_imports.rs::x.Foo") in edges
    assert ("scoped_imports.rs::b.make", "scoped_imports.rs::y.Foo") in edges
    assert ("scoped_imports.rs::b.make", "scoped_imports.rs::x.Foo") not in edges


def test_nested_function_is_not_an_impl_method(tmp_path: Path) -> None:
    source = """\
struct S;
impl S {
    fn outer(&self) {
        fn inner() {}
        inner();
    }
}
"""
    nodes, relationships = _analyze(tmp_path, source, "nested_function.rs")
    inner = next(node for node in nodes if node.name.endswith(".inner"))
    edges = _edges(relationships)

    assert inner.name == "S.outer.inner"
    assert inner.component_type == "function"
    assert inner.class_name is None
    assert ("nested_function.rs::S.outer", "nested_function.rs::S.outer.inner") in edges


def test_public_use_alias_is_recorded(tmp_path: Path) -> None:
    source = """\
mod x { pub struct Foo; impl Foo { pub fn new() -> Self { Foo } } }
pub use crate::x::Foo as Bar;
pub fn make() { let _ = Bar::new(); }
"""
    nodes, relationships = _analyze(tmp_path, source, "public_use.rs")
    names = {node.name for node in nodes}

    assert "x.Foo.new" in names
    assert ("public_use.rs::make", "public_use.rs::x.Foo.new") in _edges(relationships)


def test_cross_file_trait_impl_attaches_to_type(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "item.rs").write_text("pub struct Item;\n", encoding="utf-8")
    (src / "lib.rs").write_text(
        "mod item;\ntrait Speak { fn speak(&self); }\n"
        "impl Speak for crate::item::Item { fn speak(&self) {} }\n",
        encoding="utf-8",
    )

    components = DependencyParser(str(tmp_path)).parse_repository()

    assert components["src/item.rs::item.Item"].base_classes == ["Speak"]
    assert "src/lib.rs::Speak" in components["src/item.rs::item.Item"].depends_on


def test_trait_impl_methods_have_unique_ids(tmp_path: Path) -> None:
    source = """\
trait First { fn run(&self); }
trait Second { fn run(&self); }
struct Worker;
impl First for Worker { fn run(&self) { first(); } }
impl Second for Worker { fn run(&self) { second(); } }
fn first() {}
fn second() {}
"""
    nodes, relationships = _analyze(tmp_path, source, "trait_ids.rs")
    names = {node.name for node in nodes}
    methods = [node for node in nodes if node.name.endswith(".run")]

    assert len(methods) == 4
    assert {"First.run", "Second.run", "Worker.First.run", "Worker.Second.run"} <= names
    edges = {(r.caller, r.callee) for r in relationships}
    assert ("trait_ids.rs::Worker.First.run", "trait_ids.rs::first") in edges
    assert ("trait_ids.rs::Worker.Second.run", "trait_ids.rs::second") in edges


def test_variable_shadowing_uses_nearest_binding(tmp_path: Path) -> None:
    source = """\
struct A; struct B;
impl A { fn go(&self) {} }
impl B { fn go(&self) {} }
fn execute(x: A) { let x = B; x.go(); }
"""
    _, relationships = _analyze(tmp_path, source, "shadowing.rs")
    go_edges = {(r.caller, r.callee) for r in relationships if r.callee.endswith(".go")}

    assert go_edges == {("shadowing.rs::execute", "shadowing.rs::B.go")}


def test_known_project_method_named_like_std_is_kept(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "item.rs").write_text(
        "pub struct Item;\nimpl Item { pub fn push(&self) {} }\n", encoding="utf-8"
    )
    (src / "lib.rs").write_text(
        "mod item;\nuse crate::item::Item;\n"
        "pub fn run() { let item = Item::new(); item.push(); }\n",
        encoding="utf-8",
    )

    components = DependencyParser(str(tmp_path)).parse_repository()

    assert "src/item.rs::item.Item.push" in components["src/lib.rs::run"].depends_on


def test_cfg_feature_containing_test_is_not_skipped(tmp_path: Path) -> None:
    source = """\
#[cfg(feature = "contest")]
mod production { pub fn run() {} }
#[cfg(test)]
mod tests { fn helper() {} }
"""
    nodes, _ = _analyze(tmp_path, source)
    names = {node.name for node in nodes}

    assert "production.run" in names
    assert "tests.helper" not in names


def test_analysis_service_advertises_rust() -> None:
    assert "rust" in AnalysisService()._get_supported_languages()


def test_grammar_failure_is_explicit(clear_grammar_cache, monkeypatch) -> None:
    def fail(_language: str):
        raise RuntimeError("grammar shared library missing")

    monkeypatch.setattr(grammars, "_load_language", fail)
    with pytest.raises(GrammarUnavailableError) as info:
        get_parser("rust")
    assert info.value.language == "rust"
    assert "tree-sitter-rust" in str(info.value)
    assert "grammar shared library missing" in str(info.value)
    assert isinstance(info.value.__cause__, RuntimeError)


def test_preflight_loads_only_requested_grammars(clear_grammar_cache, monkeypatch) -> None:
    loaded = []
    monkeypatch.setattr(grammars, "_load_language", lambda name: loaded.append(name) or object())
    monkeypatch.setattr(grammars, "Parser", lambda _language: object())
    ensure_grammars(["python", "rust", "rust", "unknown"])
    assert loaded == ["rust"]


def test_analysis_preflights_before_first_file(clear_grammar_cache, tmp_path, monkeypatch) -> None:
    (tmp_path / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    analyzed = []

    def fail(_language: str):
        raise GrammarUnavailableError("rust", RuntimeError("offline"))

    monkeypatch.setattr(grammars, "get_parser", fail)
    monkeypatch.setattr(
        CallGraphAnalyzer, "_analyze_code_file", lambda self, base, info: analyzed.append(info)
    )
    with pytest.raises(GrammarUnavailableError, match="rust"):
        CallGraphAnalyzer().analyze_code_files(
            [{"path": "main.rs", "language": "rust"}], str(tmp_path)
        )
    assert analyzed == []


def test_extracts_structs_enums_traits_and_methods(tmp_path: Path) -> None:
    nodes, _ = _analyze(tmp_path)
    by_name = {node.name: node for node in nodes}

    assert by_name["Buffer"].component_type == "struct"
    assert by_name["Buffer"].node_type == "struct"
    assert by_name["Flushable"].component_type == "interface"
    assert by_name["Flushable"].node_type == "trait"
    assert by_name["Signal"].component_type == "class"
    assert by_name["Signal"].node_type == "enum"
    assert by_name["Flushable.flush"].component_type == "method"
    assert by_name["Buffer.Flushable.flush"].class_name == "Buffer"
    assert by_name["Buffer.new"].component_type == "method"
    assert by_name["Logger.warn"].class_name == "Logger"
    assert by_name["record"].component_type == "function"
    assert by_name["Buffer"].id == "buffer.rs::Buffer"
    assert all(node.language == "rust" for node in nodes)


def test_trait_impl_is_recorded_as_base_class(tmp_path: Path) -> None:
    nodes, relationships = _analyze(tmp_path)
    buffer = next(n for n in nodes if n.name == "Buffer")
    assert buffer.base_classes == ["Flushable"]
    assert ("buffer.rs::Buffer", "buffer.rs::Flushable") in _edges(relationships)


def test_docstrings_parameters_and_line_numbers(tmp_path: Path) -> None:
    nodes, _ = _analyze(tmp_path)
    by_name = {node.name: node for node in nodes}

    assert by_name["Buffer"].docstring == "/// Buffers events before flushing them downstream."
    assert by_name["Flushable"].has_docstring
    assert not by_name["Event"].has_docstring
    assert by_name["Logger.warn"].parameters == ["&self", "message: &str"]
    assert by_name["Buffer"].start_line == 30
    assert by_name["Buffer"].end_line == 35
    assert "pub struct Buffer<T>" in by_name["Buffer"].source_code


def test_cfg_test_module_is_skipped(tmp_path: Path) -> None:
    nodes, relationships = _analyze(tmp_path)
    assert not any("pushes" in node.name for node in nodes)
    assert not any("pushes" in r.caller for r in relationships)


def test_type_edges(tmp_path: Path) -> None:
    _, relationships = _analyze(tmp_path)
    edges = _edges(relationships)

    assert ("buffer.rs::Buffer", "buffer.rs::Logger") in edges
    assert ("buffer.rs::Buffer", "buffer.rs::Event") in edges
    assert ("buffer.rs::Signal", "buffer.rs::Event") in edges
    assert not any(callee in ("T", "Vec", "HashMap", "u64") for _, callee in edges)


def test_call_edges(tmp_path: Path) -> None:
    _, relationships = _analyze(tmp_path)
    edges = _edges(relationships)

    assert ("buffer.rs::Buffer.new", "buffer.rs::Buffer.with_logger") in edges
    assert ("buffer.rs::Buffer.new", "buffer.rs::Logger.new") in edges
    assert ("buffer.rs::Buffer.with_logger", "buffer.rs::Buffer") in edges
    assert ("buffer.rs::Buffer.push", "buffer.rs::Event") in edges
    assert ("buffer.rs::Buffer.push", "buffer.rs::Buffer.validate") in edges
    assert ("buffer.rs::Buffer.push", "buffer.rs::Logger.warn") in edges
    assert ("buffer.rs::Buffer.push", "buffer.rs::record") in edges


def test_noise_and_std_calls_are_dropped(tmp_path: Path) -> None:
    _, relationships = _analyze(tmp_path)
    callees = {r.callee for r in relationships}

    for noise in ("unwrap", "len", "clear", "push", "drop", "Vec.new", "HashMap.new"):
        assert noise not in callees
    assert not any(c.startswith("std") for c in callees)
    unresolved = {r.callee for r in relationships if not r.is_resolved}
    assert "external_service::ping" in unresolved
    assert "checked_add" not in unresolved


def test_inline_modules_prefix_logical_names(tmp_path: Path) -> None:
    source = """\
mod alpha {
    pub fn run() { helper(); }
    fn helper() {}
}
mod beta {
    pub fn run() {}
}
"""
    nodes, relationships = _analyze(tmp_path, source, "mods.rs")
    names = {node.name for node in nodes}
    assert {"alpha.run", "alpha.helper", "beta.run"} <= names
    assert ("mods.rs::alpha.run", "mods.rs::alpha.helper") in _edges(relationships)


def test_empty_and_broken_files_do_not_crash(tmp_path: Path) -> None:
    assert _analyze(tmp_path, "", "empty.rs") == ([], [])
    nodes, _ = _analyze(tmp_path, "fn broken( {{{ struct", "broken.rs")
    assert isinstance(nodes, list)


def test_dependency_parser_end_to_end(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "util.rs").write_text(
        "pub struct Config { pub name: String }\n\npub fn helper(config: &Config) {}\n",
        encoding="utf-8",
    )
    (src / "lib.rs").write_text(
        "mod util;\n"
        "use crate::util::Config;\n\n"
        "pub struct App { config: Config }\n\n"
        "impl App {\n"
        "    pub fn run(&self) { util::helper(&self.config); }\n"
        "}\n",
        encoding="utf-8",
    )

    components = DependencyParser(str(tmp_path)).parse_repository()

    assert "src/lib.rs::App" in components
    assert "src/lib.rs::App.run" in components
    assert "src/util.rs::util.Config" in components
    assert "src/util.rs::util.Config" in components["src/lib.rs::App"].depends_on
    assert "src/util.rs::util.helper" in components["src/lib.rs::App.run"].depends_on
