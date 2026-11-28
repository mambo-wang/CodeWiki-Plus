"""语言分析器正确性回归：超时、构造器与 C/C++ 声明符。"""

import signal

import pytest

from codewiki.src.be.dependency_analyzer.analysis.call_graph_analyzer import CallGraphAnalyzer
from codewiki.src.be.dependency_analyzer.analyzers.c import analyze_c_file
from codewiki.src.be.dependency_analyzer.analyzers.cpp import analyze_cpp_file
from codewiki.src.be.dependency_analyzer.analyzers.javascript import (
    analyze_javascript_file_treesitter,
)
from codewiki.src.be.dependency_analyzer.analyzers.typescript import (
    analyze_typescript_file_treesitter,
)


@pytest.mark.skipif(not hasattr(signal, "SIGALRM"), reason="超时依赖 SIGALRM")
def test_parse_timeout_is_not_swallowed_by_analyzer(tmp_path, monkeypatch):
    (tmp_path / "slow.js").write_text("f();\n", encoding="utf-8")
    handlers = []
    outcomes = []

    def capture_handler(signum, handler):
        handlers.append(handler)
        return signal.SIG_DFL

    def swallowing_analyzer(self, file_path, content, repo_dir):
        try:
            handlers[0](signal.SIGALRM, None)
        except Exception:
            outcomes.append("swallowed")
            return
        finally:
            outcomes.append("propagated")

    monkeypatch.setattr(signal, "signal", capture_handler)
    monkeypatch.setattr(signal, "alarm", lambda seconds: None)
    monkeypatch.setattr(CallGraphAnalyzer, "_analyze_javascript_file", swallowing_analyzer)

    CallGraphAnalyzer()._analyze_code_file(
        str(tmp_path), {"path": "slow.js", "language": "javascript"}
    )

    assert outcomes == ["propagated"]


@pytest.mark.parametrize(
    ("analyze", "filename", "source", "constructor", "callee"),
    [
        (
            analyze_javascript_file_treesitter,
            "semver.js",
            """function parse(v) { return v }
class SemVer {
  constructor(version) { this.raw = parse(version) }
  format() { return this.raw }
}
""",
            "SemVer.constructor",
            "parse",
        ),
        (
            analyze_typescript_file_treesitter,
            "struct.ts",
            """function check(x: number): number { return x }
export class Struct {
  value: number
  constructor(v: number) { this.value = check(v) }
}
""",
            "Struct.constructor",
            "check",
        ),
    ],
)
def test_constructor_is_a_component_and_call_source(
    tmp_path, analyze, filename, source, constructor, callee
):
    nodes, edges = analyze(str(tmp_path / filename), source, str(tmp_path))
    by_name = {node.name: node for node in nodes}

    assert constructor in by_name
    assert by_name[constructor].component_type in ("method", "function")
    assert by_name[constructor].id == f"{filename}::{constructor}"
    assert any(
        edge.caller == f"{filename}::{constructor}"
        and edge.callee.split("::")[-1] == callee
        for edge in edges
    )


C_SAMPLE = """\
typedef struct State State;
typedef long lua_Integer;
static int counter;
static State *current;
static char **names;

static State *find (int idx) { return current; }
static char **all_names (void) { counter++; return names; }
const char *tostring (State *L, int idx) { find(idx); return 0; }
API lua_Integer len (State *L) { return (lua_Integer)tostring(L, 1); }
int (*pick (int k)) (int) { all_names(); return 0; }
int ((wrapped)) (int k) { plain(); return 0; }
int plain (void) { return counter; }
"""

CPP_SAMPLE = """\
class Node {
public:
    Node &parent();
    const char *name() const;
};

Node &Node::parent() { return *this; }
const char *Node::name() const { parent(); return "n"; }
static Node **roots(int n) { return 0; }
API size_t count(Node *n) { roots(1); return 0; }
int ((wrapped)) (int k) { count(0); return 0; }
"""

MACRO_SAMPLE = """\
static void helper(void) { }
int CJSON_CDECL main(void)
{
    helper();
    return 0;
}
int EXPORT run(int argc) { helper(); return argc; }
typedef int Count;
int one;
Count two(void) { return 2; }
"""


def _call_pairs(edges):
    return {(edge.caller.split("::")[-1], edge.callee.split("::")[-1]) for edge in edges}


def test_c_functions_with_wrapped_declarators_keep_nodes_and_calls():
    nodes, edges = analyze_c_file("/repo/lapi.c", C_SAMPLE, "/repo")
    by_name = {node.name: node for node in nodes}

    for name in ("find", "all_names", "tostring", "len", "pick", "wrapped", "plain"):
        assert by_name[name].component_type == "function"
    assert "lua_Integer" not in by_name
    assert {
        ("tostring", "find"),
        ("len", "tostring"),
        ("pick", "all_names"),
        ("wrapped", "plain"),
    } <= _call_pairs(edges)


def test_cpp_functions_with_wrapped_declarators_keep_nodes_and_calls():
    nodes, edges = analyze_cpp_file("/repo/tree.cpp", CPP_SAMPLE, "/repo")
    ids = {node.id for node in nodes}

    assert {
        "tree.cpp::Node.parent",
        "tree.cpp::Node.name",
        "tree.cpp::roots",
        "tree.cpp::count",
        "tree.cpp::wrapped",
    } <= ids
    assert not any(node_id.endswith("::size_t") for node_id in ids)
    assert {"Node.name", "count", "wrapped"} <= {
        edge.caller.split("::")[-1] for edge in edges
    }


def test_c_macro_before_function_name_does_not_replace_the_name():
    nodes, edges = analyze_c_file("/repo/test.c", MACRO_SAMPLE, "/repo")
    names = {node.name for node in nodes}

    assert {"helper", "main", "run", "two"} <= names
    assert "Count" not in names
    assert {("main", "helper"), ("run", "helper")} <= _call_pairs(edges)
