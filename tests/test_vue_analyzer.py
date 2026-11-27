"""Vue SFC 分析器：组件身份、脚本复用、模板边与增量接入。"""

import os
from pathlib import Path

import pytest

from codewiki.cli.utils.repo_validator import SUPPORTED_EXTENSIONS
from codewiki.cli.utils.validation import detect_supported_languages
from codewiki.mcp.tools.artifact_facts import classify_artifact
from codewiki.mcp.tools.review_checklist import LANG_BY_EXT
from codewiki.src.be.dependency_analyzer.analysis.analysis_service import AnalysisService
from codewiki.src.be.dependency_analyzer.analysis.call_graph_analyzer import CallGraphAnalyzer
from codewiki.src.be.dependency_analyzer.analysis.service_detector import _has_source_files
from codewiki.src.be.dependency_analyzer.analyzers.vue import (
    analyze_vue_file,
    pascal_case,
    vue_component_name,
)
from codewiki.src.be.dependency_analyzer.ast_parser import DependencyParser
from codewiki.src.be.dependency_analyzer.utils import grammars
from codewiki.src.be.dependency_analyzer.utils.grammars import GrammarUnavailableError
from codewiki.src.be.prompt_template import EXTENSION_TO_LANGUAGE


OPTIONS_SFC = """\
<template>
  <div class="list">
    <article-preview v-for="a in articles" :article="a" :key="a.slug" />
    <VPagination :pages="pages" @update="setPage" />
    <router-link to="/">home</router-link>
    <button @click="load()">{{ format(count) }}</button>
  </div>
</template>

<script>
import ArticlePreview from "./ArticlePreview";
import VPagination from "@/components/VPagination.vue";
import { fetchArticles as fetchAll } from "@/api/articles";
import { mapGetters } from "vuex";

function format(n) {
  return String(n);
}

export default {
  name: "RwvArticleList",
  components: { ArticlePreview, VPagination, GlobalWidget },
  computed: {
    ...mapGetters(["articles"]),
    pages() {
      return 3;
    },
  },
  watch: {
    type() {
      this.load();
    },
  },
  mounted() {
    this.load();
  },
  methods: {
    load() {
      fetchAll();
      format(1);
    },
    setPage: function (p) {
      this.page = p;
      this.load();
    },
  },
};
</script>

<style scoped>
.list { color: red; }
</style>
"""

SETUP_SFC = """\
<script lang="ts">
export interface Props {
  title: string;
}
</script>

<script setup lang="ts">
import { computed } from "vue";
import TagList from "../components/TagList.vue";

const props = defineProps<Props>();

function shout(text: string): string {
  return text.toUpperCase();
}

const loud = computed(() => shout(props.title));
</script>

<template>
  <h1 @click="shout(props.title)">{{ loud }}</h1>
  <TagList />
</template>
"""


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def vue_repo(tmp_path: Path) -> Path:
    _write(tmp_path, "src/components/ArticleList.vue", OPTIONS_SFC)
    _write(
        tmp_path,
        "src/components/ArticlePreview.vue",
        "<template><p>{{ article.title }}</p></template>\n"
        "<script>\nexport default { props: ['article'] };\n</script>\n",
    )
    _write(tmp_path, "src/components/VPagination.vue", "<template><nav /></template>\n")
    _write(
        tmp_path,
        "src/api/articles.js",
        "export function fetchArticles() {\n  return fetch('/api/articles');\n}\n",
    )
    _write(tmp_path, "src/views/Home.vue", SETUP_SFC)
    _write(tmp_path, "src/components/TagList.vue", "<template><ul /></template>\n")
    return tmp_path


def _analyze(repo: Path, rel: str):
    path = repo / rel
    nodes, rels = analyze_vue_file(str(path), path.read_text(), repo_path=str(repo))
    return {node.id: node for node in nodes}, {(rel.caller, rel.callee): rel for rel in rels}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("article-preview", "ArticlePreview"),
        ("ArticlePreview", "ArticlePreview"),
        ("article_list", "ArticleList"),
        ("app", "App"),
    ],
)
def test_pascal_case(value: str, expected: str) -> None:
    assert pascal_case(value) == expected


def test_component_name_from_path() -> None:
    assert vue_component_name("src/components/article-list.vue") == "ArticleList"
    assert vue_component_name("src/views/Settings/index.vue") == "Settings"
    assert vue_component_name("App.vue") == "App"


def test_component_and_options_members(vue_repo: Path) -> None:
    nodes, _ = _analyze(vue_repo, "src/components/ArticleList.vue")
    base = "src/components/ArticleList.vue::"
    component = nodes[base + "ArticleList"]

    assert component.component_type == "class"
    assert component.node_type == "component"
    assert component.language == "vue"
    assert component.start_line == 1
    assert component.end_line == OPTIONS_SFC.count("\n")

    for member in ("load", "setPage", "pages", "type", "mounted"):
        node = nodes[f"{base}ArticleList.{member}"]
        assert node.component_type == "method"
        assert node.class_name == "ArticleList"
    assert not any(
        node_id.endswith(("ArticleList.articles", "ArticleList.name")) for node_id in nodes
    )
    assert base + "format" in nodes


def test_non_function_group_entries_are_not_members(tmp_path: Path) -> None:
    source = """\
<script>
const helper = () => 1;
export default {
  methods: { imported: helper, plain: 1 },
  computed: { value: 2, nested: { enabled: true } },
};
</script>
"""
    _write(tmp_path, "Plain.vue", source)
    nodes, _ = _analyze(tmp_path, "Plain.vue")

    assert not any(
        node.name in {"Plain.imported", "Plain.plain", "Plain.value", "Plain.nested"}
        for node in nodes.values()
    )


def test_line_numbers_follow_original_vue_file(vue_repo: Path) -> None:
    nodes, _ = _analyze(vue_repo, "src/components/ArticleList.vue")
    lines = OPTIONS_SFC.splitlines()
    fmt = nodes["src/components/ArticleList.vue::format"]
    load = nodes["src/components/ArticleList.vue::ArticleList.load"]

    assert lines[fmt.start_line - 1].startswith("function format(n)")
    assert lines[load.start_line - 1].strip() == "load() {"
    assert load.source_code.strip().startswith("load() {")


def test_template_and_import_edges(vue_repo: Path) -> None:
    _, rels = _analyze(vue_repo, "src/components/ArticleList.vue")
    base = "src/components/ArticleList.vue::"
    component = base + "ArticleList"

    edge = rels[(component, "src/components/ArticlePreview.vue::ArticlePreview")]
    assert edge.is_resolved
    assert (component, "src/components/VPagination.vue::VPagination") in rels
    assert (component, "GlobalWidget") in rels
    assert not any(callee in {"RouterLink", "mapGetters"} for _, callee in rels)
    assert (component, base + "ArticleList.setPage") in rels
    assert (component, base + "ArticleList.load") in rels
    assert (component, base + "format") in rels
    assert (component, "src/api/articles.js::fetchArticles") in rels


def test_member_call_edges(vue_repo: Path) -> None:
    _, rels = _analyze(vue_repo, "src/components/ArticleList.vue")
    base = "src/components/ArticleList.vue::ArticleList."

    assert (base + "setPage", base + "load") in rels
    assert (base + "type", base + "load") in rels
    assert (base + "mounted", base + "load") in rels
    assert (base + "load", "src/components/ArticleList.vue::format") in rels
    assert (base + "load", "src/api/articles.js::fetchArticles") in rels


def test_script_setup_typescript(vue_repo: Path) -> None:
    nodes, rels = _analyze(vue_repo, "src/views/Home.vue")
    base = "src/views/Home.vue::"

    assert base + "Home" in nodes
    assert base + "Props" in nodes
    shout = nodes[base + "shout"]
    assert shout.language == "typescript"
    assert SETUP_SFC.splitlines()[shout.start_line - 1].startswith("function shout")
    assert (base + "Home", base + "shout") in rels
    assert (base + "Home", "src/components/TagList.vue::TagList") in rels


def test_sfc_scanner_handles_nested_templates_comments_and_quoted_angles(tmp_path: Path) -> None:
    source = """\
<!-- <script>const fake = 1;</script> </template> -->
<template :data-json="'>'">
  <section>
    <template v-for="item in items">
      <article-card :title="item.title" @select="choose(item)" />
    </template>
  </section>
</template>
<script>
function choose(item) { return item; }
</script>
"""
    _write(tmp_path, "Nested.vue", source)
    nodes, rels = _analyze(tmp_path, "Nested.vue")
    component = "Nested.vue::Nested"

    assert component in nodes
    assert "Nested.vue::choose" in nodes
    assert (component, "ArticleCard") in rels
    assert (component, "Nested.vue::choose") in rels
    assert not any(node_id.endswith("::fake") for node_id in nodes)


def test_interpolation_strings_do_not_change_sfc_block_structure(tmp_path: Path) -> None:
    source = """\
<template>{{ '<template>' }}<button @click="run">run</button></template>
<script>
function run() { return 1; }
</script>
"""
    _write(tmp_path, "Interpolation.vue", source)
    nodes, rels = _analyze(tmp_path, "Interpolation.vue")

    assert "Interpolation.vue::run" in nodes
    assert ("Interpolation.vue::Interpolation", "Interpolation.vue::run") in rels


def test_script_function_with_component_name_keeps_separate_id(tmp_path: Path) -> None:
    source = """\
<script>
function Foo() { helper(); }
function helper() {}
</script>
<template><button @click="Foo">run</button></template>
"""
    _write(tmp_path, "Foo.vue", source)
    nodes, rels = _analyze(tmp_path, "Foo.vue")

    assert "Foo.vue::Foo" in nodes
    assert "Foo.vue::script.Foo" in nodes
    assert ("Foo.vue::Foo", "Foo.vue::script.Foo") in rels
    assert ("Foo.vue::script.Foo", "Foo.vue::helper") in rels


def test_utf8_mask_keeps_original_line_numbers(tmp_path: Path) -> None:
    source = """\
<template>
  <p>中文说明</p>
  <button @click="run">执行</button>
</template>
<script>
function run() {
  return "完成";
}
</script>
"""
    _write(tmp_path, "Unicode.vue", source)
    nodes, _ = _analyze(tmp_path, "Unicode.vue")
    run = nodes["Unicode.vue::run"]

    assert run.start_line == 6
    assert source.splitlines()[run.start_line - 1] == "function run() {"


def test_file_without_script(vue_repo: Path) -> None:
    nodes, rels = _analyze(vue_repo, "src/components/VPagination.vue")

    assert list(nodes) == ["src/components/VPagination.vue::VPagination"]
    assert not rels


def test_broken_file_does_not_raise(tmp_path: Path) -> None:
    path = _write(tmp_path, "Broken.vue", "<template><div></template>\n<script>export default {")
    nodes, _ = analyze_vue_file(str(path), path.read_text(), repo_path=str(tmp_path))

    assert "Broken.vue::Broken" in {node.id for node in nodes}


def test_direct_analyzer_does_not_swallow_missing_grammar(tmp_path: Path, monkeypatch) -> None:
    from codewiki.src.be.dependency_analyzer.analyzers import vue as vue_module

    def unavailable(_language: str):
        raise GrammarUnavailableError("javascript", RuntimeError("offline"))

    path = _write(tmp_path, "Main.vue", "<script>function run() {}</script>\n")
    monkeypatch.setattr(vue_module, "get_parser", unavailable)

    with pytest.raises(GrammarUnavailableError, match="javascript"):
        analyze_vue_file(str(path), path.read_text(), repo_path=str(tmp_path))


def test_pipeline_preflights_script_grammar_before_first_file(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "main.vue").write_text("<script>function main() {}</script>\n", encoding="utf-8")
    analyzed = []

    def unavailable(_language: str):
        raise GrammarUnavailableError("javascript", RuntimeError("offline"))

    monkeypatch.setattr(grammars, "get_parser", unavailable)
    monkeypatch.setattr(
        CallGraphAnalyzer, "_analyze_code_file", lambda self, base, info: analyzed.append(info)
    )

    with pytest.raises(GrammarUnavailableError, match="javascript"):
        CallGraphAnalyzer().analyze_code_files(
            [{"path": "main.vue", "language": "vue"}], str(tmp_path)
        )
    assert analyzed == []


def test_pipeline_preflights_both_script_grammars(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "main.vue").write_text("<script>function main() {}</script>\n", encoding="utf-8")
    loaded = []

    def tracking(language: str):
        loaded.append(language)
        return object()

    monkeypatch.setattr(grammars, "get_parser", tracking)
    monkeypatch.setattr(CallGraphAnalyzer, "_analyze_code_file", lambda *args: None)

    CallGraphAnalyzer().analyze_code_files([{"path": "main.vue", "language": "vue"}], str(tmp_path))

    assert loaded == ["javascript", "typescript"]


def test_vue_is_registered_across_entry_points(tmp_path: Path) -> None:
    assert ".vue" in SUPPORTED_EXTENSIONS
    assert EXTENSION_TO_LANGUAGE[".vue"] == "vue"
    assert "vue" in AnalysisService()._get_supported_languages()
    assert LANG_BY_EXT[".vue"] == "vue"
    assert classify_artifact("src/App.vue") is None

    _write(tmp_path, "main.vue", "<template><p>ok</p></template>\n")
    assert detect_supported_languages(tmp_path) == [("Vue", 1)]
    assert _has_source_files(tmp_path)


def test_cross_language_named_import_resolves_in_call_graph(tmp_path: Path) -> None:
    vue_path = _write(
        tmp_path,
        "App.vue",
        '<script>import { fetchArticles } from "./api.js";</script>\n',
    )
    js_path = _write(
        tmp_path,
        "api.js",
        "export function fetchArticles() { return []; }\n",
    )
    graph = CallGraphAnalyzer()
    graph._analyze_vue_file(str(vue_path), vue_path.read_text(), str(tmp_path))
    graph._analyze_javascript_file(str(js_path), js_path.read_text(), str(tmp_path))
    graph._resolve_call_relationships()

    edge = next(
        rel
        for rel in graph.call_relationships
        if rel.caller == "App.vue::App" and rel.callee == "api.js::fetchArticles"
    )
    assert edge.is_resolved


def test_cached_vue_edge_is_dropped_when_javascript_export_disappears(tmp_path: Path) -> None:
    vue_path = _write(
        tmp_path,
        "App.vue",
        '<script>import { fetchArticles } from "./api.js";</script>\n',
    )
    js_path = _write(
        tmp_path,
        "api.js",
        "export function fetchArticles() { return []; }\n",
    )
    files = [
        {"path": "App.vue", "name": "App.vue", "extension": ".vue", "language": "vue"},
        {"path": "api.js", "name": "api.js", "extension": ".js", "language": "javascript"},
    ]
    full = CallGraphAnalyzer()
    full.analyze_code_files(files, str(tmp_path))
    for relationship in full.call_relationships:
        if relationship.is_resolved and relationship.callee in full.functions:
            full.functions[relationship.caller].depends_on.add(relationship.callee)
    assert "api.js::fetchArticles" in full.functions["App.vue::App"].depends_on

    js_path.write_text("export const renamed = 1;\n", encoding="utf-8")
    incremental = CallGraphAnalyzer()
    incremental.analyze_code_files(
        files,
        str(tmp_path),
        skip_file_paths={str(vue_path)},
        cached_components=full.functions,
    )

    assert "App.vue::App" in incremental.functions
    assert "api.js::fetchArticles" not in incremental.functions["App.vue::App"].depends_on
    assert not any(
        relationship.caller == "App.vue::App" and relationship.callee == "api.js::fetchArticles"
        for relationship in incremental.call_relationships
    )


def test_cached_vue_edge_to_unchanged_javascript_export_is_preserved(tmp_path: Path) -> None:
    vue_path = _write(
        tmp_path,
        "App.vue",
        '<script>import { fetchArticles } from "./api.js";</script>\n',
    )
    _write(
        tmp_path,
        "api.js",
        "export function fetchArticles() { return []; }\n",
    )
    files = [
        {"path": "App.vue", "name": "App.vue", "extension": ".vue", "language": "vue"},
        {"path": "api.js", "name": "api.js", "extension": ".js", "language": "javascript"},
    ]
    full = CallGraphAnalyzer()
    full.analyze_code_files(files, str(tmp_path))
    for relationship in full.call_relationships:
        if relationship.is_resolved and relationship.callee in full.functions:
            full.functions[relationship.caller].depends_on.add(relationship.callee)
    assert "api.js::fetchArticles" in full.functions["App.vue::App"].depends_on

    incremental = CallGraphAnalyzer()
    incremental.analyze_code_files(
        files,
        str(tmp_path),
        skip_file_paths={str(vue_path), str(tmp_path / "api.js")},
        cached_components=full.functions,
    )

    assert "App.vue::App" in incremental.functions
    assert "api.js::fetchArticles" in incremental.functions["App.vue::App"].depends_on
    assert any(
        relationship.caller == "App.vue::App"
        and relationship.callee == "api.js::fetchArticles"
        and relationship.is_resolved
        for relationship in incremental.call_relationships
    )


def test_dependency_parser_resolves_across_files(vue_repo: Path) -> None:
    components = DependencyParser(str(vue_repo)).parse_repository()
    article_list = components["src/components/ArticleList.vue::ArticleList"]

    assert "src/components/ArticlePreview.vue::ArticlePreview" in article_list.depends_on
    assert "src/components/VPagination.vue::VPagination" in article_list.depends_on
    assert "src/api/articles.js::fetchArticles" in article_list.depends_on
    assert "src/components/TagList.vue::TagList" in (
        components["src/views/Home.vue::Home"].depends_on
    )


def test_vue_participates_in_fingerprint_cache(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache

    repo = tmp_path / "repo"
    repo.mkdir()
    main = repo / "App.vue"
    other = repo / "Other.vue"
    main.write_text("<template><p>main</p></template>\n", encoding="utf-8")
    other.write_text("<template><p>other</p></template>\n", encoding="utf-8")
    cache = AnalysisCache(repo, db_path=repo / ".codewiki" / "analysis_cache.db")
    try:
        cache.update_file_fingerprints([main.name, other.name])
        assert cache.detect_changes() == {
            "changed_files": [],
            "method": "fingerprint",
            "no_changes": True,
        }

        other.write_text("<template><p>changed</p></template>\n", encoding="utf-8")
        assert cache.detect_changes() == {
            "changed_files": [other.name],
            "method": "fingerprint",
        }
    finally:
        cache.close()


def test_vue_fingerprint_detects_same_size_tail_edit_with_old_mtime(tmp_path: Path) -> None:
    from codewiki.mcp.cache import AnalysisCache

    repo = tmp_path / "repo"
    repo.mkdir()
    large = repo / "Large.vue"
    original = "<template>" + ("a" * 70000) + "</template>\n"
    large.write_text(original, encoding="utf-8")
    cache = AnalysisCache(repo, db_path=repo / ".codewiki" / "analysis_cache.db")
    try:
        cache.update_file_fingerprints([large.name])
        stat = large.stat()
        large.write_text(original[:-20] + "b" + original[-19:], encoding="utf-8")
        os.utime(large, ns=(stat.st_atime_ns, stat.st_mtime_ns))

        assert cache.detect_changes() == {
            "changed_files": [large.name],
            "method": "fingerprint",
        }
    finally:
        cache.close()
