"""ADR-0018: 二进制源 markitdown 转换 sidecar 的行为测试。

覆盖：
- 未装 markitdown 时 fail-open 降级（dependency_missing，导入照常成功）
- 装了 markitdown 时 sidecar 落盘、registry 记 derived_text/convert_error
- 转换产物喂版本去重门（version_sibling 跨格式检测）
- retract remove_refs 把 sidecar 一并移 .trash
- _plain_text 读 sidecar 回退
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.source_ingest import (
    _CONVERTIBLE_SUFFIXES,
    _plain_text,
    handle_ingest_source,
    handle_retract_source,
)


class _Store(SessionStore):
    pass


def _call(fn, **kw) -> dict:
    return json.loads(fn(kw, _Store()))


def _ingest(tmp_path: Path, src: Path, name: str, **extra) -> dict:
    args = {"repo_path": str(tmp_path), "source_ref": str(src), "name": name}
    args.update(extra)
    return _call(handle_ingest_source, **args)


def _registry(tmp_path: Path) -> dict:
    reg = tmp_path / "repowiki" / ".meta" / "source_registry.json"
    return json.loads(reg.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# fail-open: markitdown 未安装
# --------------------------------------------------------------------------- #


def test_dependency_missing_fail_open(tmp_path, monkeypatch):
    """未装 markitdown：导入照常成功，convert_error=dependency_missing。"""
    src = tmp_path / "spec.pdf"
    src.write_bytes(b"%PDF-1.4 fake pdf bytes")
    # 强制 import markitdown 抛 ImportError
    monkeypatch.setitem(sys.modules, "markitdown", None)

    r = _ingest(tmp_path, src, "spec")
    assert r["status"] == "ingested"
    assert r["derived_text"] is None
    assert r["convert_error"] == "dependency_missing"

    reg = _registry(tmp_path)
    entry = reg["sources"]["spec"]
    assert entry["derived_text"] is None
    assert entry["convert_error"] == "dependency_missing"
    # 原始文件保留
    assert (tmp_path / "repowiki" / "raw" / "sources" / "spec.pdf").exists()


def test_binary_without_markitdown_skips_version_gates(tmp_path, monkeypatch):
    """降级路径下二进制源跳过去重门（行为同现状）。"""
    monkeypatch.setitem(sys.modules, "markitdown", None)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 first")
    r = _ingest(tmp_path, src, "doc-a")
    assert r["status"] == "ingested"

    src2 = tmp_path / "b.pdf"
    src2.write_bytes(b"%PDF-1.4 second different bytes")
    r2 = _ingest(tmp_path, src2, "doc-b")
    # 无文本可指纹 → 不触发 version_sibling，直接入库
    assert r2["status"] == "ingested"


# --------------------------------------------------------------------------- #
# markitdown 可用：sidecar 落盘 + registry 记录
# --------------------------------------------------------------------------- #


class _FakeConverted:
    def __init__(self, text: str):
        self.text_content = text


class _FakeMarkItDown:
    def __init__(self, *a, **kw):
        pass

    def convert(self, path: str) -> _FakeConverted:
        p = Path(path)
        if p.suffix == ".pdf":
            return _FakeConverted("# 转换标题\n\n这是从 PDF 转换出的正文内容。\n")
        raise RuntimeError("boom")


def _fake_markitdown_module():
    import types

    mod = types.ModuleType("markitdown")
    mod.MarkItDown = _FakeMarkItDown
    return mod


def test_sidecar_written_and_registered(tmp_path, monkeypatch):
    """装了 markitdown：sidecar 落盘，registry 记 derived_text。"""
    monkeypatch.setitem(sys.modules, "markitdown", _fake_markitdown_module())
    src = tmp_path / "spec.pdf"
    src.write_bytes(b"%PDF-1.4 fake")

    r = _ingest(tmp_path, src, "spec")
    assert r["status"] == "ingested"
    assert r["derived_text"] == "raw/sources/spec.converted.md"
    assert r["convert_error"] is None

    sidecar = tmp_path / "repowiki" / "raw" / "sources" / "spec.converted.md"
    assert sidecar.exists()
    assert "转换标题" in sidecar.read_text(encoding="utf-8")

    reg = _registry(tmp_path)
    entry = reg["sources"]["spec"]
    assert entry["derived_text"] == "raw/sources/spec.converted.md"
    assert entry["convert_error"] is None
    # 指纹来自 sidecar 文本（去重门覆盖二进制）
    assert isinstance(entry["similarity"], dict) and entry["similarity"].get("sketch")


def test_converter_exception_fail_open(tmp_path, monkeypatch):
    """转换器抛异常：fail-open，convert_error=converter_exception。"""

    class _Boom(_FakeMarkItDown):
        def convert(self, path: str):
            raise RuntimeError("boom")

    import types

    mod = types.ModuleType("markitdown")
    mod.MarkItDown = _Boom
    monkeypatch.setitem(sys.modules, "markitdown", mod)

    src = tmp_path / "spec.pdf"
    src.write_bytes(b"%PDF-1.4 fake")
    r = _ingest(tmp_path, src, "spec")
    assert r["status"] == "ingested"
    assert r["derived_text"] is None
    assert r["convert_error"] == "converter_exception"


def test_empty_output_fail_open(tmp_path, monkeypatch):
    """扫描版 PDF 转出空文本：convert_error=empty_output。"""

    class _Empty(_FakeMarkItDown):
        def convert(self, path: str):
            return _FakeConverted("   \n  ")

    import types

    mod = types.ModuleType("markitdown")
    mod.MarkItDown = _Empty
    monkeypatch.setitem(sys.modules, "markitdown", mod)

    src = tmp_path / "scan.pdf"
    src.write_bytes(b"%PDF-1.4 scanned")
    r = _ingest(tmp_path, src, "scan")
    assert r["status"] == "ingested"
    assert r["derived_text"] is None
    assert r["convert_error"] == "empty_output"


# --------------------------------------------------------------------------- #
# 跨格式 version_sibling 门
# --------------------------------------------------------------------------- #


def test_cross_format_version_sibling(tmp_path, monkeypatch):
    """docx 与已注册 md 内容相似 → version_sibling 拦下问用户。"""
    monkeypatch.setitem(sys.modules, "markitdown", _fake_markitdown_module())

    # 先注册一个 md 源
    md_src = tmp_path / "design.md"
    md_src.write_text("# 转换标题\n\n这是从 PDF 转换出的正文内容。\n", encoding="utf-8")
    r = _ingest(tmp_path, md_src, "design-md")
    assert r["status"] == "ingested"

    # 再导入一个 docx，markitdown 转出的文本与上面 md 高度相似
    docx_src = tmp_path / "design.docx"
    docx_src.write_bytes(b"PK fake docx")

    import types

    class _DocxConvert(_FakeMarkItDown):
        def convert(self, path: str):
            if Path(path).suffix == ".docx":
                return _FakeConverted("# 转换标题\n\n这是从 PDF 转换出的正文内容。\n")
            return _FakeConverted("")

    mod = types.ModuleType("markitdown")
    mod.MarkItDown = _DocxConvert
    monkeypatch.setitem(sys.modules, "markitdown", mod)

    r2 = _ingest(tmp_path, docx_src, "design-docx")
    assert r2["status"] == "version_sibling"
    assert r2["requires_user_confirmation"] is True
    assert r2["existing_name"] == "design-md"
    # 不落盘
    assert "design-docx" not in _registry(tmp_path)["sources"]
    # 门拦下时不得留下孤儿 sidecar（评审修复回归）
    assert not (tmp_path / "repowiki" / "raw" / "sources" / "design-docx.converted.md").exists()


# --------------------------------------------------------------------------- #
# retract：sidecar 一并退役
# --------------------------------------------------------------------------- #


def test_retract_moves_sidecar_to_trash(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "markitdown", _fake_markitdown_module())
    src = tmp_path / "spec.pdf"
    src.write_bytes(b"%PDF-1.4 fake")
    r = _ingest(tmp_path, src, "spec")
    assert r["status"] == "ingested"

    sidecar = tmp_path / "repowiki" / "raw" / "sources" / "spec.converted.md"
    assert sidecar.exists()

    rr = _call(
        handle_retract_source,
        repo_path=str(tmp_path),
        name="spec",
        mode="remove_refs",
    )
    assert rr["status"] == "retracted"
    assert not sidecar.exists()
    assert (tmp_path / "repowiki" / ".trash" / "spec.converted.md").exists()
    # 原始文件也进 .trash
    assert (tmp_path / "repowiki" / ".trash" / "spec.pdf").exists()


# --------------------------------------------------------------------------- #
# _plain_text sidecar 回退
# --------------------------------------------------------------------------- #


def test_plain_text_reads_sidecar(tmp_path):
    sidecar = tmp_path / "spec.converted.md"
    sidecar.write_text("# 标题\n\n正文。\n", encoding="utf-8")
    fake_pdf = tmp_path / "spec.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    assert _plain_text(fake_pdf) == "# 标题\n\n正文。\n"
    # 无 sidecar 的二进制 → None
    other = tmp_path / "other.pdf"
    other.write_bytes(b"%PDF-1.4")
    assert _plain_text(other) is None


def test_convertible_suffixes():
    """官方口径与 _CONVERTIBLE_SUFFIXES 严格同步（ADR-0018 决策⑧）。"""
    assert _CONVERTIBLE_SUFFIXES == {".pdf", ".docx", ".xlsx"}
    assert ".md" not in _CONVERTIBLE_SUFFIXES
    assert ".pptx" not in _CONVERTIBLE_SUFFIXES  # 未验证不承诺
    assert ".epub" not in _CONVERTIBLE_SUFFIXES  # 未验证不承诺
