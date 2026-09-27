"""init_wiki: schema.yaml 幂等语义（ADR：只首次拷贝，重跑绝不覆盖用户自定义）。"""

from pathlib import Path

from codewiki.mcp.tools.init_wiki import handle_init_wiki, initialize_wiki_tree

import json


def _run(repo: Path, **kwargs) -> dict:
    res = handle_init_wiki({"repo_path": str(repo), **kwargs})
    return json.loads(res)


def test_first_run_copies_template(tmp_path):
    repo = tmp_path / "fresh"
    repo.mkdir()
    r = _run(repo)
    assert r["status"] == "ok"
    schema = repo / "repowiki" / "schema.yaml"
    assert schema.exists()
    assert "purpose:" in schema.read_text(encoding="utf-8")


def test_rerun_preserves_customized_schema(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _run(repo)["status"] == "ok"

    # 用户自定义 purpose（模拟已填写）
    schema = repo / "repowiki" / "schema.yaml"
    customized = 'purpose: "my custom purpose 自定义"'
    schema.write_text(
        schema.read_text(encoding="utf-8").replace('purpose: ""', customized, 1), encoding="utf-8"
    )

    # 重跑 init_wiki —— 必须保留自定义，不得被模板覆盖
    r = _run(repo)
    assert r["status"] == "ok"
    assert "(already exists, skipped)" in r["schema_yaml"]
    assert customized in schema.read_text(encoding="utf-8")


def test_initialize_wiki_tree_overwrite_flag(tmp_path):
    dest = tmp_path / "repowiki"
    dest.mkdir()
    # 预置一个"已自定义"的 schema.yaml
    (dest / "schema.yaml").write_text('purpose: "keep me"\n', encoding="utf-8")

    tree = initialize_wiki_tree(tmp_path, dest)  # 默认 overwrite_schema=False
    assert "(already exists, skipped)" in tree["schema_yaml"]
    assert "keep me" in (dest / "schema.yaml").read_text(encoding="utf-8")

    tree = initialize_wiki_tree(tmp_path, dest, overwrite_schema=True)  # 显式覆盖
    assert "keep me" not in (dest / "schema.yaml").read_text(encoding="utf-8")
