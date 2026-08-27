"""General-axis checklists for ``review_changes`` — data-only module.

Two layers:

* **Language-agnostic** — engineering baseline items every change must pass
  (``BUILTIN["all"]``).
* **Per-language** — items selected by the changed file's extension
  (``BUILTIN[lang]``, currently Python only; more languages are P1).

Project override: if ``<repo>/repowiki/review_checklist.yaml`` exists it is
merged at prepare time — an entry with the same ``id`` replaces the builtin
one, unknown ids are appended.  The file is bootstrapped by ``init_wiki``
from the template at ``codewiki/templates/review_checklist.yaml`` (copied
only when absent, so user edits survive re-runs).  Shape of the YAML::

    # repowiki/review_checklist.yaml
    all:
      - id: err-handling
        title: 错误处理
        questions: ["..."]

    python:
      - id: ...
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Extension → checklist language key (lowercased suffix, no dot).
LANG_BY_EXT = {
    ".py": "python",
    ".go": "go",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "c",
    ".hpp": "c",
    ".cc": "c",
    ".php": "php",
    ".rb": "ruby",
    ".rs": "rust",
}

BUILTIN_CHECKLISTS: Dict[str, List[Dict[str, Any]]] = {
    "all": [
        {
            "id": "err-handling",
            "title": "错误处理与资源释放",
            "questions": [
                "异常/错误是否被吞掉（空 except、忽略返回值、丢失 error）？",
                "文件、连接、锁等资源是否在 finally / with / defer 中释放？",
                "错误是否丢失上下文（原始异常、关键参数未随错误传播）？",
            ],
        },
        {
            "id": "input-validation",
            "title": "输入校验",
            "questions": [
                "外部输入（参数、用户数据、文件内容）是否在入口处校验？",
                "边界值（空、超长、负数、零、越界）是否处理？",
                "类型/格式假设是否显式而非依赖调用方自觉？",
            ],
        },
        {
            "id": "logging",
            "title": "日志",
            "questions": [
                "关键路径（错误、慢路径、状态变更）是否有日志？",
                "日志是否含定位所需上下文（id、参数摘要）而非只有堆栈？",
                "是否避免了在循环/热路径中打印高频日志？",
            ],
        },
        {
            "id": "security",
            "title": "安全",
            "questions": [
                "是否存在注入风险（SQL/命令/模板拼接外部输入）？",
                "密钥、token、密码是否硬编码或写进日志？",
                "路径拼接是否存在穿越风险（未校验相对路径）？",
            ],
        },
        {
            "id": "concurrency",
            "title": "并发安全",
            "questions": [
                "共享可变状态是否有锁或同步机制？",
                "是否存在竞态（先查后写、非原子更新）？",
                "新增全局/模块级可变状态是否线程安全？",
            ],
        },
        {
            "id": "null-boundary",
            "title": "空值与边界条件",
            "questions": [
                "null/None/空集合的访问是否防护？",
                "集合为空、索引越界、除零等边界是否考虑？",
                "循环终止条件是否正确（off-by-one）？",
            ],
        },
        {
            "id": "testability",
            "title": "可测试性",
            "questions": [
                "新逻辑是否可独立测试（无硬编码依赖、时间、随机）？",
                "副作用（IO、网络、DB）是否集中在可 mock 的边界？",
                "是否有测试覆盖本次变更的关键分支？",
            ],
        },
        {
            "id": "backward-compat",
            "title": "向后兼容",
            "questions": [
                "公共接口/数据结构变更是否破坏既有调用方？",
                "默认行为变更是否可能影响未显式传参的调用方？",
                "删除/重命名是否有过渡期或同步更新全部引用？",
            ],
        },
        {
            "id": "performance",
            "title": "性能",
            "questions": [
                "是否存在明显 N+1 查询或循环内重活（IO、正则编译、DB 调用）？",
                "新引入的数据结构/算法量级是否匹配预期规模？",
                "是否引入了不必要的拷贝/序列化？",
            ],
        },
        {
            "id": "code-quality",
            "title": "代码质量",
            "questions": [
                "是否有重复逻辑可抽取（本文件或同模块已有实现）？",
                "命名是否准确反映行为（无误导性名称）？",
                "是否有死代码、未使用变量、注释与代码不一致？",
            ],
        },
    ],
    "python": [
        {
            "id": "py-mutable-default",
            "title": "可变默认参数",
            "questions": ["函数参数默认值是否为可变对象（list/dict/set）——调用间共享状态？"],
        },
        {
            "id": "py-bare-except",
            "title": "裸 except",
            "questions": [
                "是否使用裸 except / except Exception 吞掉包括 KeyboardInterrupt 在内的异常？"
            ],
        },
        {
            "id": "py-resource-context",
            "title": "资源上下文管理",
            "questions": ["文件、socket、锁是否使用 with 语句管理生命周期？"],
        },
        {
            "id": "py-encoding",
            "title": "编码处理",
            "questions": ["文件读写是否显式指定 encoding（跨平台 GBK/UTF-8 差异）？"],
        },
        {
            "id": "py-import-side-effect",
            "title": "import 副作用",
            "questions": ["模块导入是否触发重副作用（网络、文件写、DB 连接）？"],
        },
    ],
}


def load_project_checklist(repo_path: Optional[str]) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """Load ``<repo>/repowiki/review_checklist.yaml`` if present.

    Returns ``None`` when the file is absent or unreadable (malformed YAML is
    logged and ignored — a broken override must not break the review).
    """
    if not repo_path:
        return None
    p = Path(repo_path) / "repowiki" / "review_checklist.yaml"
    if not p.exists():
        return None
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML unavailable, falling back to builtin checklist (override: %s)", p)
        return None
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse project checklist %s, falling back to builtin: %s", p, exc)
        return None
    if not isinstance(data, dict):
        logger.warning(
            "Project checklist %s is not a mapping (%s), falling back to builtin",
            p,
            type(data).__name__,
        )
        return None
    out: Dict[str, List[Dict[str, Any]]] = {}
    for key, entries in data.items():
        if not isinstance(entries, list):
            logger.warning("Section %r of %s is not a list, skipped", key, p)
            continue
        valid = [e for e in entries if isinstance(e, dict) and e.get("id")]
        if len(valid) != len(entries):
            logger.warning("Section %r of %s dropped entries missing 'id'", key, p)
        out[str(key)] = valid
    return out


def get_checklist(
    repo_path: Optional[str],
    changed_files: List[str],
) -> List[Dict[str, Any]]:
    """Resolve the merged checklist for a set of changed files.

    Language-agnostic items always included; per-language items added for
    each distinct language among the changed files.  Project overrides merge
    by ``id`` (same id replaces, unknown id appends).
    """
    langs: List[str] = []
    for f in changed_files:
        lang = LANG_BY_EXT.get(Path(f).suffix.lower())
        if lang and lang not in langs:
            langs.append(lang)

    merged: Dict[str, Dict[str, Any]] = {}
    for lang in ["all", *langs]:
        for entry in BUILTIN_CHECKLISTS.get(lang, []):
            merged[entry["id"]] = dict(entry, lang=lang)

    project = load_project_checklist(repo_path)
    if project:
        for lang in ["all", *langs]:
            for entry in project.get(lang, []):
                merged[entry["id"]] = dict(entry, lang=lang)

    return [merged[k] for k in merged]
