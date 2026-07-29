"""MCP Resources — read-only context for agents.

This module registers resource and resource-template handlers on the MCP
server instance, providing agents with read-only access to prompt catalogs,
capability overviews, page-type documentation, and per-wiki metadata
(catalog, module tree, index status).
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ===================================================================
#  Helper functions
# ===================================================================

def _read_wiki_resource(uri_str: str) -> str:
    """Handle parameterized wiki resources like codewiki://wiki/{output_dir}/catalog."""
    from urllib.parse import unquote
    # Parse: codewiki://wiki/<encoded_output_dir>/<resource_type>
    path_part = uri_str[len("codewiki://wiki/"):]
    # The last segment is the resource type
    last_slash = path_part.rfind("/")
    if last_slash == -1:
        return json.dumps({"error": "Invalid URI format. Expected: codewiki://wiki/{output_dir}/{catalog|module-tree|index-status}"})

    output_dir_encoded = path_part[:last_slash]
    resource_type = path_part[last_slash + 1:]
    output_dir = unquote(output_dir_encoded)

    output_path = Path(output_dir)
    if not output_path.exists():
        return json.dumps({"error": f"Output directory not found: {output_dir}"})

    if resource_type == "catalog":
        return _wiki_catalog(output_path)
    elif resource_type == "module-tree":
        return _wiki_module_tree(output_path)
    elif resource_type == "index-status":
        return _wiki_index_status(output_path)
    else:
        return json.dumps({"error": f"Unknown resource type: {resource_type}. Available: catalog, module-tree, index-status"})


def _wiki_catalog(output_path: Path) -> str:
    """Build a catalog of all wiki pages."""
    pages = []
    wiki_dir = output_path / "wiki"
    search_dirs = [wiki_dir, output_path / "notes"]
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for md_file in sorted(search_dir.rglob("*.md")):
            rel = md_file.relative_to(output_path)
            # Read first heading as title
            title = md_file.stem
            try:
                for line in md_file.read_text(encoding="utf-8").splitlines()[:10]:
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
            except Exception:
                pass
            # Determine page type from directory
            parts = rel.parts
            page_type = parts[1] if len(parts) > 2 and parts[0] == "wiki" else "note"
            pages.append({"path": str(rel).replace("\\", "/"), "title": title, "type": page_type})

    return json.dumps({"output_dir": str(output_path), "page_count": len(pages), "pages": pages}, ensure_ascii=False, indent=2)


def _wiki_module_tree(output_path: Path) -> str:
    """Read the module tree from .meta/module_tree.json."""
    from codewiki.src.config import meta_resolve
    tree_path = Path(meta_resolve(output_path, "module_tree.json"))
    if not tree_path.exists():
        return json.dumps({"error": "Module tree not found. Run analyze_repo + save_module_tree first."})
    try:
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
        # Summarize
        def _summarize(t, depth=0):
            modules = []
            for name, info in t.items():
                modules.append({
                    "name": name,
                    "components": len(info.get("components", [])),
                    "children": len(info.get("children", {})) if isinstance(info.get("children"), dict) else 0,
                    "is_leaf": not bool(info.get("children")),
                })
                if isinstance(info.get("children"), dict) and info["children"]:
                    modules.extend(_summarize(info["children"], depth + 1))
            return modules
        summary = _summarize(tree)
        return json.dumps({"output_dir": str(output_path), "total_modules": len(tree), "modules": summary}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to read module tree: {e}"})


def _wiki_index_status(output_path: Path) -> str:
    """Check the search index and link graph status."""
    from codewiki.src.config import meta_resolve
    index_path = Path(meta_resolve(output_path, "search_index.db"))
    result = {"output_dir": str(output_path), "index_exists": index_path.exists()}

    if index_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(index_path))
            cur = conn.cursor()
            # Count indexed pages
            try:
                cur.execute("SELECT COUNT(*) FROM search_index")
                result["indexed_pages"] = cur.fetchone()[0]
            except Exception:
                result["indexed_pages"] = 0
            # Count tokens
            try:
                cur.execute("SELECT COUNT(*) FROM search_token_index")
                result["token_entries"] = cur.fetchone()[0]
            except Exception:
                result["token_entries"] = 0
            # Count graph edges
            try:
                cur.execute("SELECT COUNT(*) FROM wiki_links")
                result["graph_edges"] = cur.fetchone()[0]
            except Exception:
                result["graph_edges"] = 0
            conn.close()
        except Exception as e:
            result["error"] = str(e)
    else:
        result["hint"] = "Search index not built yet. Call close_session or build_search_index to create it."

    return json.dumps(result, ensure_ascii=False, indent=2)


# ===================================================================
#  Registration
# ===================================================================

def register(server):
    """Register resource and resource-template handlers on the MCP server."""

    @server.list_resources()
    async def list_resources() -> list:
        """List available static resources."""
        from mcp.types import Resource
        return [
            Resource(
                uri="codewiki://prompts/catalog",
                name="Prompt 模板目录",
                title="CodeWiki Prompt 模板目录",
                description="所有可用的 Prompt 模板列表及其用途说明，帮助 agent 了解可用的工作流指引",
                mimeType="application/json",
            ),
            Resource(
                uri="codewiki://capabilities",
                name="服务能力概览",
                title="CodeWiki 服务能力与工具清单",
                description="完整的工具列表、参数速查、工作流说明，agent 可据此规划任务",
                mimeType="application/json",
            ),
            Resource(
                uri="codewiki://page-types",
                name="页面类型说明",
                title="Wiki 页面类型与路由规则",
                description="各 page_type 的用途、存储路径、frontmatter 规范和 wikilink 建图规则",
                mimeType="application/json",
            ),
        ]

    @server.list_resource_templates()
    async def list_resource_templates() -> list:
        """List available resource templates (parameterized URIs)."""
        from mcp.types import ResourceTemplate
        return [
            ResourceTemplate(
                uriTemplate="codewiki://wiki/{output_dir}/catalog",
                name="Wiki 页面目录",
                title="指定 Wiki 的页面目录",
                description="获取指定输出目录下所有 Wiki 页面的目录（标题、类型、路径），URI 中 output_dir 使用 URL 编码的绝对路径",
                mimeType="application/json",
            ),
            ResourceTemplate(
                uriTemplate="codewiki://wiki/{output_dir}/module-tree",
                name="模块聚类树",
                title="指定 Wiki 的模块聚类树",
                description="获取指定 Wiki 的模块聚类结构（模块名、组件数、层级关系）",
                mimeType="application/json",
            ),
            ResourceTemplate(
                uriTemplate="codewiki://wiki/{output_dir}/index-status",
                name="搜索索引状态",
                title="指定 Wiki 的搜索索引状态",
                description="获取 BM25 搜索索引和 wikilink 图谱的构建状态（页面数、token 数、边数）",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: Any) -> str:
        """Read a resource by URI."""
        uri_str = str(uri)

        if uri_str == "codewiki://prompts/catalog":
            return json.dumps({
                "prompts": [
                    {"name": "generate-wiki", "title": "生成代码 Wiki", "description": "完整的代码仓库 Wiki 生成流水线", "arguments": ["repo_path (optional, 默认当前目录)", "output_dir (optional)"]},
                    {"name": "extract-knowledge", "title": "外部文档知识抽取", "description": "导入外部文档并从中抽取实体/概念，一步完成导入+提取", "arguments": ["source_path (required, 文档绝对路径)"]},
                    {"name": "search-wiki", "title": "知识库搜索", "description": "BM25 + 图谱扩展 + 深度阅读的分层搜索策略", "arguments": ["query (required)"]},
                    {"name": "quality-check", "title": "文档质量审计", "description": "全面质量检查：过时引用、断链、覆盖率、循环依赖", "arguments": ["output_dir (optional)"]},
                    {"name": "incremental-update", "title": "增量更新 Wiki", "description": "检测代码变更并增量更新受影响的模块文档", "arguments": ["repo_path (optional, 默认当前目录)"]},
                    {"name": "workspace-analysis", "title": "多仓库工作区分析（含跨服务拓扑）", "description": "扫描多 git 仓库，生成独立 Wiki 并自动执行 RouteNode 跨服务匹配 + 拓扑图 + 基础设施扫描", "arguments": ["workspace_path (optional, 默认当前目录)"]},
                    {"name": "cross-service-trace", "title": "跨服务调用链追踪", "description": "对指定根服务做跨服务调用链分析：RouteNode 静态匹配 + CBM trace_path 语义穿透", "arguments": ["workspace_path (required)", "filter_value (optional, 追踪起点)"]},
                ],
                "usage": "通过 MCP prompts/get 协议获取完整工作流指引，或调用 get_prompt 工具获取代码生成阶段的 prompt 模板",
            }, ensure_ascii=False, indent=2)

        elif uri_str == "codewiki://capabilities":
            return json.dumps({
                "server": "CodeWiki-CN MCP Server v5.1.0",
                "tool_count": 22,
                "tool_categories": {
                    "代码分析": ["analyze_repo", "analyze_workspace", "list_components", "list_dependencies", "analyze_impact", "read_code_components", "view_repo_file"],
                    "跨服务分析": ["query_cross_service"],
                    "文档生成": ["write_doc_file", "edit_doc_file", "save_module_tree", "get_processing_order", "get_prompt", "generate_docs (legacy)"],
                    "知识库管理": ["query_wiki", "ingest_note", "ingest_source", "retract_source", "batch_ingest"],
                    "质量保障": ["lint_wiki", "flag_issue"],
                    "会话管理": ["close_session", "get_module_tree (legacy)"],
                },
                "key_patterns": {
                    "workspace_file": "大结果写入 .codewiki/workspace/ 目录，通过 file_path 读取",
                    "session_lifecycle": "analyze_repo 创建 → 工具调用 → close_session 清理（2h TTL）",
                    "page_type_routing": "module→wiki/modules/, entity→wiki/entities/, concept→wiki/concepts/, source→wiki/sources/",
                    "search_layers": "BM25 全文 → hop 图谱扩展 → expand 深度阅读",
                    "cross_service": "analyze_workspace（多仓库）或 analyze_repo（monorepo 单仓库）自动生成拓扑 → query_cross_service 多维切片 → (可选) CBM trace_path 语义追踪",
                },
            }, ensure_ascii=False, indent=2)

        elif uri_str == "codewiki://page-types":
            return json.dumps({
                "page_types": {
                    "module": {"path": "wiki/modules/", "description": "代码模块文档（由 analyze_repo 流水线生成）", "typical_sections": ["概述", "架构图", "核心组件", "依赖关系", "使用示例"]},
                    "entity": {"path": "wiki/entities/", "description": "实体页面（人物/系统/服务/组件/API）", "typical_sections": ["定义", "关键属性", "关系", "来源引用"]},
                    "concept": {"path": "wiki/concepts/", "description": "概念页面（模式/算法/协议/架构决策）", "typical_sections": ["定义", "原理", "应用场景", "相关概念"]},
                    "source": {"path": "wiki/sources/", "description": "外部源文档摘要页", "typical_sections": ["来源信息", "核心内容", "抽取的实体/概念", "引用"]},
                    "comparison": {"path": "wiki/comparisons/", "description": "对比分析页面", "typical_sections": ["对比维度", "各方案优劣", "结论"]},
                    "query": {"path": "wiki/queries/", "description": "查询结果归档页面", "typical_sections": ["问题", "答案", "参考来源"]},
                },
                "wikilink_rules": {
                    "syntax": "[[页面名]] 或 [显示文本](相对路径.md)",
                    "graph_build": "build_search_index 自动解析所有 wikilink 为 wiki_links 表中的有向边",
                    "multi_hop": "query_wiki(hop=N) 沿图谱边 BFS 扩展，每跳分数衰减 0.5x",
                    "aliases": "frontmatter_extra.aliases 中的别名也参与 wikilink 解析",
                },
            }, ensure_ascii=False, indent=2)

        # Resource templates: codewiki://wiki/{output_dir}/...
        elif uri_str.startswith("codewiki://wiki/"):
            return _read_wiki_resource(uri_str)

        return json.dumps({"error": f"Unknown resource: {uri_str}"})
