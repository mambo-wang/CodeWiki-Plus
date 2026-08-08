"""
MCP Prompt Templates for CodeWiki.

This module contains all workflow prompt templates that guide agents through
CodeWiki operations: Wiki generation, knowledge extraction, search strategies,
quality checks, incremental updates, cross-service tracing, workspace analysis,
code analysis, impact review, note ingestion, architecture review, and
team-memory fusion (conversation capture hook toggle, conversation distillation).

Usage:
    from codewiki.mcp.prompts import register
    register(server)
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_path(raw: str) -> str:
    """Resolve a path: if relative, join with cwd; always return absolute."""
    p = raw.strip()
    if not p or p in (".", "./"):
        return os.getcwd()
    if os.path.isabs(p):
        return os.path.normpath(p)
    return os.path.normpath(os.path.join(os.getcwd(), p))


def _prompt_generate_wiki(args: dict[str, str]) -> str:
    repo_path = _resolve_path(args.get("repo_path", ""))
    output_dir = args.get("output_dir", "")
    od_note = f'，output_dir="{output_dir}"' if output_dir else ""
    return f"""请为代码仓库生成完整的 Wiki 文档。按以下步骤执行：

## 步骤 1: 分析仓库
调用 analyze_repo(repo_path="{repo_path}"{od_note})
- 返回组件数量、语言统计等分析结果
- 大文件结果写入 workspace 文件，通过返回的 file_path 读取

## 步骤 2: 模块聚类
调用 get_prompt(prompt_type="cluster", repo_path="{repo_path}")
- 获取聚类规则（按目录结构、依赖关系、功能内聚性分组）
- **重要**: 直接根据你的理解对组件进行语义分组
- 根据规则将组件分为模块，构建 module_tree JSON
- 调用 save_module_tree(repo_path="{repo_path}", module_tree=...) 保存

## 步骤 3: 获取处理顺序
调用 get_processing_order(repo_path="{repo_path}")
- 返回叶优先顺序：先写叶模块，再写父模块（父模块可引用子模块文档）

## 步骤 4: 逐模块撰写文档
对每个模块（按处理顺序）：
1. 调用 get_prompt(prompt_type="user", repo_path="{repo_path}", variables={{"module_name": "<模块名>"}}) 获取撰写指引
2. 调用 read_code_components(repo_path="{repo_path}", component_ids) 读取源码
3. 调用 list_dependencies(repo_path="{repo_path}", component_ids) 获取依赖关系
4. 撰写 Markdown 文档（200-500 行叶模块，含 Mermaid 架构图）
5. 调用 write_doc_file(repo_path="{repo_path}", filename="<模块名>.md", page_type="module", content=...) 写入

## 步骤 5: 仓库总览
调用 get_prompt(prompt_type="overview_repo", repo_path="{repo_path}") 获取总览模板
撰写 overview.md（80-200 行），链接所有模块文档

## 步骤 6: 质检与关闭（强制，不可跳过）
- 调用 lint_wiki(repo_path="{repo_path}") 检查一致性
- 修复发现的问题（edit_doc_file）
- 调用 close_session(repo_path="{repo_path}") 完成（触发索引重建、AGENTS.md 注入、构建 BM25 搜索索引与 wikilink 图）
- 注意：close_session 是整条流水线的强制终态步骤。只有它执行后 query_wiki 才能检索到内容；漏掉它会导致 Wiki 不可搜索，且本流程视为未完成。

## 注意事项
- 每个叶模块至少 1 个 Mermaid 图（graph TD 或 graph LR）
- 使用 [模块名](模块名.md) 交叉引用
- 节点 ID 仅用字母和数字，标签用方括号
- 文档语言默认中文"""


def _prompt_extract_knowledge(args: dict[str, str]) -> str:
    source_path = args.get("source_path", "")
    if not source_path:
        source_path = "<source_path>"
    else:
        source_path = _resolve_path(source_path)
    # Derive a name from the file stem
    from pathlib import Path as _Path
    source_name = _Path(source_path).stem
    # output_dir defaults to cwd/repowiki (not next to the source file)
    output_dir = args.get("output_dir", "") or str(_Path(_resolve_path("")) / "repowiki")
    granularity = args.get("granularity", "").strip()
    gran_call = f', variables={{"granularity": "{granularity}"}}' if granularity else ""
    gran_default_note = (
        "" if granularity else
        "- granularity 未指定时，自动遵循 schema.yaml 的 extraction_granularity 配置\n"
    )
    return f"""请导入外部文档并从中抽取结构化知识。采用「骨架提取 → 去重检查 → 证据校验 → 页面撰写」两阶段流程，按以下步骤执行：

## 步骤 1: 导入文档
调用 ingest_source(output_dir="{output_dir}", source_ref="{source_path}")
- 文档会被复制到 {output_dir}/raw/sources/ 并注册到 source_registry.json
- 此步骤直接传入 output_dir，无需 session

## 步骤 2: 骨架提取（Pass 0 — 只识别，不撰写）
1. 通读源文档 "{source_path}"（使用 Read 工具直接读取原始文件，无需 view_repo_file），标记关键实体和抽象概念
2. 调用 get_prompt(prompt_type="extraction_scan"{gran_call}) 获取识别规则和粒度指引
{gran_default_note}3. 按模板输出 JSON 骨架：每项只含 title/type/summary/aliases/source_ref/target_page
- **本阶段禁止撰写页面正文**
- 每项必须携带 `[^src:{source_name}:<line_range>]` 行范围引用，指向源文档中实质性讨论该项的位置

## 步骤 3: 去重检查（语义去重）
对每个骨架项：
1. 调用 query_wiki(output_dir="{output_dir}", query="<title 及 aliases>") 搜索已有相似页面
2. 调用 get_prompt(prompt_type="extraction_dedup") 获取去重判定规则
3. 按规则将每项三分类：**create**（新建页面）/ **merge**（合并进已有页面）/ **drop**（丢弃）
- 核心原则：**related ≠ same**——相关不等于相同，拿不准就不合并

## 步骤 4: 证据校验
重读源文档（带行号），逐项校验存活的骨架项：
- source_ref 行范围内必须**实质性讨论**该项（独立段落、≥2 句或列表要点展开），而非顺带提及
- 一次性提及按当前 granularity 处理：focused/standard 直接丢弃；exhaustive 可保留但页面中须注明仅为提及
- 无法给出真实引用的项应丢弃——**无引用不成立**

## 步骤 5: 撰写知识页面（使用 output_dir="{output_dir}"）
1. 源文档摘要: write_doc_file(output_dir="{output_dir}", filename="{source_name}.md", page_type="source", content=...)
   - 调用 get_prompt(prompt_type="source_summary") 获取模板
2. 实体页面（action=create）: write_doc_file(output_dir="{output_dir}", filename="<实体名>.md", page_type="entity", content=...)
   - 调用 get_prompt(prompt_type="entity_page") 获取模板（含编译器写作纪律）
3. 概念页面（action=create）: write_doc_file(output_dir="{output_dir}", filename="<概念名>.md", page_type="concept", content=...)
   - 调用 get_prompt(prompt_type="concept_page") 获取模板（含编译器写作纪律）
4. action=merge 的项: 先用 view_repo_file 读取已有页面，再用 edit_doc_file 追加新事实
   - 新事实必须附 `[^src:{source_name}:<line_range>]` 引用；补充 aliases；不得覆盖或删除已有内容

## 步骤 6: 构建知识图谱并验证
- 页面间使用 [[wikilink]] 互相引用（如 [[认证服务]]、[[OAuth2]]）
- build_search_index 会自动解析 wikilink 为图谱边
- 调用 query_wiki(output_dir="{output_dir}", query="<实体/概念名>") 验证新页面可被检索
- 之后可通过 query_wiki(output_dir="{output_dir}", query, hop=1) 进行多跳关联搜索

## 写作纪律（所有页面通用）
- **编译器模式**：事实性陈述直接引用源文档原句并标注 `[^src:{source_name}:<a-b>]`，可轻排序、去重、连接，但不得为风格改写或扩写
- **禁止修辞填充**："旨在帮助…"、"该平台致力于…"、"具有重要意义"等套话不得出现，除非源文档原文如此
- **范围纪律**：页面每个陈述必须关于页面标题本身；与标题不符的材料（即使相关）应拒绝采纳
- 使用 frontmatter_extra 添加 aliases（搜索加权 3x）和 source_refs

## 注意事项
- 整个流程直接使用 output_dir，无需 analyze_repo
- write_doc_file 直接传 output_dir 参数
- ingest_source 只负责存储，不会自动生成 entity/concept 页面
- 每个页面应包含：定义、关键属性、与其他实体的关系、来源引用"""


def _prompt_search_wiki(args: dict[str, str]) -> str:
    query = args.get("query", "<query>")
    return f"""请搜索 Wiki 知识库回答: "{query}"

## 搜索策略

### 第一层：BM25 全文搜索
调用 query_wiki(query="{query}", include_notes=true)
- 返回按相关性排序的结果，含 snippet 和 context_package
- 如果结果不理想，尝试 expand_terms 添加同义词

### 第二层：图谱扩展
调用 query_wiki(query="{query}", hop=1)
- 沿 wikilink 图谱 BFS 扩展，发现相关但未直接匹配的页面
- hop=2 可进一步扩展（分数衰减 0.5x/hop）

### 第三层：深度阅读
对感兴趣的结果调用 query_wiki(query="<精确标题>", expand=true)
- 返回完整页面内容（截断至 3000 字符）
- 适合需要详细了解某个主题时

### 过滤技巧
- scope="modules" 限定搜索模块文档
- scope="entities" 限定搜索实体页面
- scope="notes" 限定搜索经验笔记
- type_filter="entity" 按页面类型过滤

## 注意事项
- 代码实现细节（函数签名、调用链）应使用 grep/代码搜索，不用 query_wiki
- query_wiki 擅长回答 why（设计决策）、lesson（踩坑经验）、architecture（架构约定）
- 搜索无结果时考虑：同义词、上位概念、相关模块名"""


def _prompt_quality_check(args: dict[str, str]) -> str:
    output_dir = args.get("output_dir", "")
    od_param = f'output_dir="{output_dir}"' if output_dir else 'repo_path=<repo_path>'
    return f"""请对 Wiki 文档执行全面质量审计。按以下步骤执行：

## 步骤 1: 运行全量检查
调用 lint_wiki({od_param}, checks=["all"])
- stale_refs: 文档引用了已不存在的代码组件
- broken_links: Markdown 链接指向不存在的页面
- undocumented: 高影响组件缺少文档
- cycles: 模块间存在循环依赖
- coverage: 文档覆盖率不足
- orphan_pages: 无入链的孤立页面
- no_outlinks: 无出链的页面（缺少交叉引用）

## 步骤 2: 按严重度处理
- error: 必须修复（断链、过时引用）
- warning: 建议修复（孤立页面、缺少别名）
- info: 可选优化（覆盖率提升）

## 步骤 3: 修复问题
- 断链: edit_doc_file 修正链接路径
- 过时引用: 重新阅读代码，更新文档内容
- 孤立页面: 在相关页面添加 [[wikilink]] 引用
- 缺少文档: write_doc_file 补充模块文档

## 步骤 4: 记录问题
对暂时无法修复的问题调用 flag_issue(issue_type, page_path, description)
- 问题追踪在 .meta/issues.json，支持后续批量处理

## 步骤 5: 验证修复
再次调用 lint_wiki 确认问题已解决"""


def _prompt_incremental_update(args: dict[str, str]) -> str:
    repo_path = _resolve_path(args.get("repo_path", ""))
    return f"""请增量更新代码仓库的 Wiki 文档。按以下步骤执行：

## 步骤 1: 检测变更
调用 analyze_repo(repo_path="{repo_path}")
- 如果 output_dir 已有 .meta/metadata.json，返回 changes 字段
- changes 包含: added_files, modified_files, deleted_files, affected_modules

## 步骤 2: 评估影响范围
- 阅读 changes.affected_modules 确定需要更新的模块
- 如果变更较小（<3 个模块），直接更新
- 如果变更较大，考虑重新聚类（save_module_tree）

## 步骤 3: 更新受影响模块
对每个 affected_module：
1. read_code_components 读取最新源码
2. view_repo_file 读取现有文档
3. edit_doc_file(str_replace) 更新变更部分
4. 或 write_doc_file 重写整个模块文档

## 步骤 4: 处理删除的文件
- 如果组件被删除，更新引用它的文档
- lint_wiki(checks=["stale_refs"]) 检查过时引用

## 步骤 5: 重建索引
调用 close_session(repo_path="{repo_path}") 触发索引重建

## 注意事项
- 增量更新只修改受影响的模块，不重写整个 Wiki
- 如果 metadata.json 不存在，会执行全量分析"""


def _prompt_cross_service_trace(args: dict[str, str]) -> str:
    workspace_path = _resolve_path(args.get("workspace_path", ""))
    root_service = args.get("root_service", "")
    filter_value = args.get("filter_value", "") or root_service or "<目标服务>"
    return f"""请对工作区 `{workspace_path}` 执行跨服务调用分析（Cross-Service Trace）。
本流程综合使用 CodeWiki 的 RouteNode 静态匹配和 codebase-memory-mcp（如可用）的语义追踪，
产出完整的跨服务调用拓扑。

## 步骤 0：前置检查
- 确认已执行 `analyze_workspace`。如未执行，先调用：
  ```
  analyze_workspace(workspace_path="{workspace_path}")
  ```
- 记录返回的 `workspace_session_id` 和 `overview_path`
- 检查 MCP 工具列表中是否有 `trace_path`（codebase-memory-mcp），有则步骤 4 可用

## 步骤 1：读取基线拓扑
读取 `{workspace_path}/workspace-wiki/overview.md`，定位：
- Mermaid 服务流程图（识别核心枢纽服务）
- 已匹配路由表（已发现的跨服务调用）
- 未匹配路由表（潜在的盲点）

## 步骤 2：从根服务出发追踪调用链
调用 query_cross_service：
```json
{{
  "workspace_path": "{workspace_path}",
  "filter_type": "trace",
  "filter_value": "{filter_value}"
}}
```
- 返回从 `{filter_value}` 出发的所有下游调用链（深度不限）
- 每条链包含：源服务 → 客户端组件 → 协议/方法/路径 → 目标服务 → 服务端组件

## 步骤 3：多维度切片分析
针对步骤 2 的结果，从不同维度切片：
- **协议分布**：`filter_type="by_method", filter_value="POST"` 查看所有写操作链路
- **路径前缀**：`filter_type="by_path", filter_value="/api/v1/orders"` 聚焦订单域调用
- **单服务画像**：`filter_type="by_service", filter_value="<服务名>"` 看某服务的完整入向+出向

## 步骤 4：🧠 语义深度追踪（CBM 增强，可选）
对步骤 2 中的关键链路，用 codebase-memory-mcp 的 `trace_path` 做语义穿透：
```json
{{
  "project": "<CBM 项目名>",
  "function_name": "<客户端函数名>",
  "mode": "cross_service",
  "depth": 3
}}
```
- 从客户端函数入口一路追踪到服务端处理函数的内部实现
- 揭示 RouteNode 匹配不到的深层依赖：中间件调用、数据库查询、异步任务派发

## 步骤 5：架构诊断
根据收集到的调用链，输出以下诊断：
- **循环依赖**：A→B→A 的调用环（架构坏味道）
- **扇入热点**：被 ≥3 个服务调用的"上帝服务"
- **单向依赖缺失**：某服务的所有调用都是出向（可能是纯客户端/worker）
- **未匹配路由**：客户端 URL 无法与服务端路由对应（可能是外部系统调用）

## 步骤 6：归档发现
调用 ingest_note 归档到 workspace 级别知识库（workspace_session_id）：
```json
{{
  "note_type": "architecture",
  "title": "跨服务调用拓扑（{filter_value} 视角）",
  "content": "Mermaid 调用链图 + 诊断结果 + 优化建议",
  "related_modules": ["<涉及的服务名>"],
  "aliases": ["cross-service", "topology", "{filter_value}"]
}}
```

## 步骤 7：输出交付物
最终产出两份文档：
1. **拓扑报告**（Markdown）：Mermaid 图 + 调用链明细 + 架构诊断
2. **优化建议**：基于诊断的架构改进建议（拆分热点服务、消除循环依赖、
   显式化外部调用）"""


def _prompt_workspace_analysis(args: dict[str, str]) -> str:
    workspace_path = _resolve_path(args.get("workspace_path", ""))
    return f"""请分析多仓库工作区并生成跨服务文档。按以下步骤执行：

## 步骤 0：环境检测
- 检查 MCP 工具列表：
  - 是否有 `query_cross_service`？有则启用 🌐 跨服务分析
  - 是否有 `index_repository`？有则启用 🧠 codebase-memory 深度增强
  - 是否有 `codegraph_status`？有则启用 🔗 CodeGraph 调用图增强

## 步骤 1：扫描工作区（自动执行跨服务分析）
调用 analyze_workspace(workspace_path="{workspace_path}")
- 自动发现所有 git 仓库（一个 .git = 一个 repowiki）
- 为每个子仓库独立执行 analyze_repo
- 🌐 **自动执行 RouteNode 跨服务匹配**（HTTP 路由 + MQ 生产者/消费者）
- **自动扫描** docker-compose.yml / .env / application.yml 发现服务名和端口
- **自动生成** workspace-wiki/overview.md，内含 Mermaid 服务拓扑图 + 路由表
- 返回 `workspace_session_id`、`overview_path`、各仓库分析结果

## 步骤 2：审阅跨服务拓扑
读取返回的 `overview_path`（通常是 `{workspace_path}/workspace-wiki/overview.md`）：
- 查看 Mermaid 服务流程图：识别核心枢纽服务、单向依赖、循环依赖
- 查看匹配的路由表：理解服务间的 API 契约
- 查看未匹配路由：发现潜在的客户端调用盲点（例如硬编码 URL、动态路径）

## 步骤 3：深入查询跨服务调用
调用 query_cross_service(workspace_path="{workspace_path}") 进行多角度查询：
- `filter_type="all"`：全量跨服务链接
- `filter_type="by_service", filter_value="<服务名>"`：某服务的入向/出向调用
- `filter_type="by_method", filter_value="POST"`：所有写操作
- `filter_type="by_path", filter_value="/api/v1/"`：某 API 前缀下的调用
- `filter_type="trace", filter_value="<根服务>"`：从某服务出发的调用链

## 步骤 4：🧠 深度追踪（如 codebase-memory-mcp 可用）
对步骤 3 发现的关键调用链，用 CBM 的 `trace_path(mode="cross_service", depth=3)` 做
多跳语义追踪：从客户端函数一路追踪到服务端处理函数的内部调用链（包括中间件、
数据库访问、异步任务派发），揭示 RouteNode 匹配不到的深层依赖。

## 步骤 5：逐仓库生成 Wiki
对每个子仓库执行标准 Wiki 生成流程：
- 各仓库使用自己的 repo_path 执行 Wiki 生成流程
- analyze_repo → 聚类 → 逐模块撰写 → close_session
- 每个仓库的 Wiki 位于 <repo>/repowiki/
- 🔗 CodeGraph 增强模式可补充单仓内的调用图细节

## 步骤 6：归档跨服务架构决策
用 workspace_session_id 调用 ingest_note(note_type="architecture") 记录：
- 跨服务 API 契约（URL、方法、参数、返回结构）
- 消息协议约定（topic、payload schema、消费语义）
- 共享数据模型和 schema 约定
- 跨服务熔断/限流/重试策略

## 步骤 7：工作区总览（LLM 生成架构叙述）
overview.md 当前是程序化骨架（服务表 + Mermaid 拓扑 + 聚合摘要）。
用 LLM 将其升级为有架构叙事的文档：

1. 读取 `{workspace_path}/workspace-wiki/overview.md` 中的 Services 表格和
   Cross-Service Summary 部分
2. 调用 get_prompt(prompt_type="overview_workspace", variables={{
     "workspace_name": "<工作区名>",
     "services_summary": "<Services 表格内容>",
     "cross_service_data": "<Service Topology + Cross-Service Summary 内容>"
   }})
3. 根据返回的模板撰写完整 overview（80-150 行），重点包含：
   - 2-3 段架构叙述（系统目的、服务协作方式、数据流、架构模式）
   - Mermaid 服务拓扑图（可用 subgraph 分组）
   - 聚合跨服务摘要（每对服务一行：调用数 + 代表性端点 + 交互性质）
   - 服务目录表（链接各仓库 wiki）
4. 用 write_doc_file 写入 `{workspace_path}/workspace-wiki/overview.md`
   （替换骨架中的 AGENT_ENRICH 注释占位符）

## 注意事项
- 每个子仓库独立管理自己的 Wiki
- workspace 级别只存放跨服务关注点
- 使用 query_wiki 在 workspace 级别搜索跨服务知识
- 未匹配的客户端调用（在 overview.md 路由表中标记）需人工确认：可能是外部系统调用、
  硬编码 URL、或客户端使用了 RouteNode 匹配不到的协议（如 gRPC）"""


def _prompt_code_analysis(args: dict[str, str]) -> str:
    repo_path = _resolve_path(args.get("repo_path", ""))
    return f"""请对代码仓库执行纯结构分析（不生成 Wiki 文档）。按以下步骤执行：

## 步骤 1: 分析仓库
调用 analyze_repo(repo_path="{repo_path}")
- 构建函数级调用图（Tree-sitter AST 解析，无 LLM）
- 返回组件数量、语言统计等分析结果
- 结果缓存在 SQLite 中，支持增量更新

所有查询工具直接传 repo_path：
```
analyze_impact(repo_path="{repo_path}", file_paths=['src/utils.py'], direction='depended_by')
list_dependencies(repo_path="{repo_path}", module_level=true)
list_components(repo_path="{repo_path}", component_type='function')
```

## 步骤 2: 浏览组件
调用 list_components(repo_path="{repo_path}", filter_type='all') 浏览所有组件
- filter_type='by_file', filter_value='src/auth/' 按路径筛选
- filter_type='by_type', filter_value='class' 按类型筛选
- 大文件结果通过 workspace file_path 读取完整组件索引

## 步骤 3: 查询依赖关系
```
# 直接（1跳）依赖
list_dependencies(repo_path="{repo_path}", component_ids=['src/auth.py::AuthService'], direction='both')

# 模块级依赖图
list_dependencies(repo_path="{repo_path}", module_level=true)
```

## 步骤 4: 传递性影响分析
```
# 谁依赖我（传递性）
analyze_impact(repo_path="{repo_path}", component_ids=['src/utils.py::parse_config'],
               direction='depended_by')

# 按文件路径（自动解析为组件）
analyze_impact(repo_path="{repo_path}", file_paths=['src/utils.py'],
               direction='depended_by')

# 完整调用链路
analyze_impact(repo_path="{repo_path}", component_ids=['src/utils.py::parse_config'],
               direction='depended_by', include_paths=true)
```

## 步骤 5: 阅读源码
```
read_code_components(repo_path="{repo_path}", component_ids=['src/auth.py::AuthService'])
```

## 关键点
- 所有分析本地运行（Tree-sitter），无需 LLM/API Key
- 结果持久化到 SQLite，重新分析时可增量复用缓存
- 查询工具直接传 repo_path，无需 session
- 后续想生成 Wiki 时，直接执行 generate-wiki 工作流即可
- 使用 get_prompt(prompt_type="code_analysis") 获取更详细的工具用法说明"""


def _prompt_impact_review(args: dict[str, str]) -> str:
    repo_path = _resolve_path(args.get("repo_path", ""))
    target = args.get("target", "<target>")
    # Determine if target looks like a component_id (has ::) or a file path
    is_component = "::" in target
    if is_component:
        impact_call = f"analyze_impact(repo_path='{repo_path}', component_ids=['{target}'], direction='depended_by', include_paths=true)"
        reverse_call = f"analyze_impact(repo_path='{repo_path}', component_ids=['{target}'], direction='depends_on')"
    else:
        impact_call = f"analyze_impact(repo_path='{repo_path}', file_paths=['{target}'], direction='depended_by', include_paths=true)"
        reverse_call = f"analyze_impact(repo_path='{repo_path}', file_paths=['{target}'], direction='depends_on')"
    return f"""请评估修改 `{target}` 的影响范围。按以下步骤执行：

## 步骤 1: 正向影响分析（谁依赖我）
调用 {impact_call}
- 如果此仓库之前分析过，会直接从 SQLite 缓存加载，无需先跑 analyze_repo
- 返回所有传递性受影响的组件
- depth 0 = 目标组件本身，depth 1 = 直接调用者，depth 2+ = 间接调用者
- include_paths=true 会返回从目标到每个受影响组件的最短调用链

## 步骤 2: 反向依赖分析（我依赖谁）
调用 {reverse_call}
- 返回目标组件传递性依赖的所有组件
- 帮助理解修改可能破坏的上游依赖

## 步骤 3: 风险评估
根据分析结果评估：
- **爆炸半径**：<10 个受影响组件 = 低风险，10-50 = 中等，50+ = 高风险
- **模块扩散**：受影响组件分布在 1-2 个模块还是 5+ 个？跨模块影响需要更多集成测试
- **深度分布**：大部分受影响在 depth 1-2？深度 5+ 意味着紧耦合
- **高风险组件**：是否有 high_risk_components（5+ 直接依赖者）在受影响集合中？
- **入口点**：受影响组件是否有 API 端点、CLI 命令、事件处理器？这些是面向用户的

## 步骤 4: 制定变更计划
- **低风险**：直接修改，跑现有测试
- **中等风险**：审查受影响模块的测试，为 depth-1 调用者添加回归测试
- **高风险**：拆分为小步骤；用 read_code_components 审查每个 depth-1 调用者；考虑特性开关

## 后续查询
```
# 钻入某个受影响的组件
analyze_impact(repo_path='{repo_path}', component_ids=['<affected_id>'], direction='depends_on')

# 查看模块级依赖
list_dependencies(repo_path='{repo_path}', module_level=true)

# 阅读高风险组件源码
read_code_components(repo_path="{repo_path}", component_ids=['<high_risk_id>'])
```

使用 get_prompt(prompt_type="impact_review") 获取更详细的解读指南。"""


def _prompt_ingest_note(args: dict[str, str]) -> str:
    output_dir = args.get("output_dir", "")
    note_type = args.get("note_type", "general")
    dir_hint = f'output_dir="{output_dir}"' if output_dir else 'output_dir="<repo>/repowiki"'
    return f"""请将知识经验归档到 Wiki 知识库。按以下步骤执行：

## 何时使用
在以下场景完成后立即归档：
- **设计决策**：为什么选择方案 A 而不是方案 B
- **踩坑记录**：开发中遇到的陷阱和根因
- **架构 rationale**：系统设计的核心理由
- **Bug 修复**：如何定位并修复了疑难 Bug
- **已知问题**：当前存在的限制或缺陷
- **临时方案**：绕过问题的 workaround

## 笔记类型选择
| 类型 | 用途 | 适用场景 |
|------|------|----------|
| decision | 记录技术/架构选型理由 | 选择了 JWT 而非 Session 认证 |
| lesson | 开发中获得的经验教训 | 老项目方法名与实际行为不一致 |
| architecture | 系统设计 rationale | 为什么采用事件驱动而非同步调用 |
| bug_fix | Bug 修复过程和方法 | 定位了竞态条件导致的偶发失败 |
| pitfall | 带根因的踩坑记录 | 字符串转义导致运行时语法错误 |
| known_issue | 已知的待修复问题 | API 在高并发下偶发超时 |
| workaround | 临时绕过方案 | 通过重试机制缓解第三方服务不稳定 |
| general | 自由格式知识 | 不属于上述类型的其他知识 |

## 步骤 1: 组织笔记内容

好的笔记应包含：
- **背景**：什么场景下产生了这个知识
- **核心内容**：决策/教训/方案本身
- **原因分析**：为什么是这样（重点写 WHY 而非 WHAT）
- **影响范围**：涉及哪些模块/组件

控制在 200-500 字，简洁有力。

## 步骤 2: 调用 ingest_note 归档

```json
{{
  "output_dir": "{output_dir or '<repo>/repowiki'}",
  "note_type": "{note_type}",
  "title": "<简洁描述核心知识的标题>",
  "content": "## 背景\\n...\\n## 核心内容\\n...\\n## 原因\\n...",
  "related_modules": ["<相关模块名>"],
  "aliases": ["<同义词/关键词，提升搜索命中率，3x 权重>"]
}}
```

### 参数说明
- **output_dir**（必填）：Wiki 输出目录路径
- **note_type**：笔记类型，默认 general
- **title**（必填）：简洁的标题，概括核心知识
- **content**（必填）：Markdown 格式的笔记正文
- **related_modules**：相关模块名列表，省略时自动从内容匹配
- **related_components**：相关组件 ID 列表
- **aliases**：同义词/别名列表，大幅提升 query_wiki 搜索命中率（3x 权重）
- **severity**：严重程度 critical/high/medium/low（仅 pitfall/known_issue）
- **root_cause**：根因描述（仅 pitfall/bug_fix）
- **source_ref**：外部来源引用（如 'RFC-793'、'api-docs-v2'）

## 步骤 3: 验证归档结果

调用 query_wiki 确认笔记可被检索：
```
query_wiki(output_dir="{output_dir or '<repo>/repowiki'}", query="<笔记标题关键词>")
```

## 高质量笔记示例

```json
{{
  "output_dir": "{output_dir or '<repo>/repowiki'}",
  "note_type": "lesson",
  "title": "OrderService.process() 只做参数校验不做业务处理",
  "content": "## 背景\\n\\nAgent 误以为 OrderService.process() 包含完整业务逻辑，基于方法名做了错误的设计假设。\\n\\n## 正确做法\\n\\nprocess() 仅做入参校验和格式化，实际业务处理在 OrderService.execute() 中。老项目方法名与实际行为不一致是常见情况，应优先阅读实现而非信任方法名。\\n\\n## 根因\\n\\n十几年老项目，方法经过多次重构但名称未更新。",
  "related_modules": ["order"],
  "aliases": ["process方法", "execute方法", "方法名不一致"]
}}
```

## 注意事项
- 不是每次操作都需要归档，只记录有复用价值的知识
- 如果未来的 Agent 或新同事遇到同样场景时有用，就值得记录
- 个人偏好、临时调整等不需要记录
- 笔记存储在 `notes/` 目录，可通过 query_wiki 全文检索"""


def _prompt_architecture_review(args: dict[str, str]) -> str:
    repo_path = _resolve_path(args.get("repo_path", ""))
    return f"""请通过依赖图分析代码库的高层架构。按以下步骤执行：

## 步骤 1: 分析仓库
调用 analyze_repo(repo_path="{repo_path}")
- 记录 total_components、languages、leaf_nodes_preview
- leaf_nodes 是入口点（无依赖者的顶层消费者）

## 步骤 2: 识别架构层次
```
# 高影响组件（被多人依赖）= 基础设施/核心层
list_dependencies(repo_path='{repo_path}', direction='depended_by')
# → 查看 high_impact_components

# 叶节点 = 应用/API 层（消费他人，无人消费）
# 已在 analyze_repo 返回的 leaf_nodes 中
```
- 高 depended_by_count 的组件 = 核心/基础设施层
- leaf_nodes = 应用边界（API、CLI、Handler）

## 步骤 3: 映射模块边界
```
list_dependencies(repo_path="{repo_path}", module_level=true)
```
关注：
- **枢纽模块**：高 depends_on + 高 depended_by（编排者）
- **叶模块**：仅 depends_on（应用层）
- **核心模块**：仅 depended_by（共享库）
- **循环依赖**：相互依赖的模块（耦合臭味）

## 步骤 4: 追踪关键路径
```
# 选一个入口点，追踪它依赖什么
analyze_impact(repo_path="{repo_path}", component_ids=['<leaf_node>'],
               direction='depends_on', include_paths=true)

# 选一个核心组件，看谁使用它
analyze_impact(repo_path="{repo_path}", component_ids=['<core_component>'],
               direction='depended_by', include_paths=true)
```

## 步骤 5: 识别热点和风险
- depended_by_count >= 10：变更抗性热点
- 循环依赖模块：重构候选
- 深依赖链（depth 5+）：紧耦合指标

## 输出模板
总结发现：
1. **层次图**：核心 → 服务 → 应用（Mermaid graph TD）
2. **模块地图**：枢纽/叶/核心分类 + 依赖箭头
3. **热点**：Top 5 最被依赖组件及其风险等级
4. **入口点**：按类型分组的叶节点（API、CLI、事件处理器）
5. **耦合关注点**：循环依赖、深链、上帝模块

使用 get_prompt(prompt_type="architecture_review") 获取更详细的分析指南。"""


def _prompt_init_wiki(args: dict[str, str]) -> str:
    repo_path = _resolve_path(args.get("repo_path", ""))
    output_dir = args.get("output_dir", "")
    od_note = f'，output_dir="{output_dir}"' if output_dir else ""
    # T6: 可选启用 IDE hook（team-memory fusion 自动采集对话）
    enable_hook = args.get("enable_hook", "").strip().lower()
    if enable_hook in ("1", "true", "yes", "on"):
        hook_block = f"""## 步骤 2: 启用 IDE 对话自动采集 Hook（可选）
为支持 team-memory fusion（对话→Wiki 经验沉淀），可启用 IDE hook，使对话结束时自动把原始对话捕获到 repowiki/raw/（仅采集、不蒸馏；蒸馏由后台 distill_conversation 完成）。

启用方式（二选一）：
- **环境变量**（推荐，供 IDE 调用方设置）：
  ```powershell
  $env:CODEWIKI_TEAM_MEMORY_HOOK = "1"
  python -m codewiki.mcp._ide_hook --repo-path="{repo_path or '<repo>'}"
  ```
- **命令行 --enable**（单次调用强制开启）：
  ```powershell
  python -m codewiki.mcp._ide_hook --enable --repo-path="{repo_path or '<repo>'}"
  ```
对话内容可通过 `--conversation <json文件>` 传入（turns 列表或 {{"turns":[...]}}），或从 stdin 管道读取 JSON 事件。
**默认关闭**：未设置环境变量且未传 --enable 时，hook 仅打印 disabled 并以退出码 0 安全返回，不会采集任何对话。
> 注意：hook 只负责 capture_conversation（落 raw），真正的蒸馏需另行运行 distill_conversation（异步、LLM 重活）。"""
        step_shift = 1
    else:
        hook_block = ""
        step_shift = 0
    return f"""请为项目初始化 Wiki 工作区。按以下步骤执行：

## 步骤 1: 初始化
调用 init_wiki(repo_path="{repo_path}"{od_note})
- 自动创建目录结构：wiki/modules, wiki/entities, wiki/concepts, wiki/sources, wiki/comparisons, wiki/queries, notes/
- 拷贝带注释的 schema.yaml 模板到输出目录（保留所有注释，方便阅读和自定义）
- 在仓库根目录写入/更新 AGENTS.md（含使用建议、自我反思协议、知识沉淀规则）
{hook_block}
## 步骤 {2 + step_shift}: 自定义 schema.yaml
读取 `{output_dir or repo_path + '/repowiki'}/schema.yaml`，根据项目特点修改：
- **purpose**（重要）：用一两句话描述项目定位，会注入到所有文档生成 prompt 中
- **doc_types**：选择适合项目的文档风格（api/architecture/design/business 等）
- **conventions**：调整命名规范、最小行数、是否需要 Mermaid 图等
- **page_types**：按需增删页面类型

## 步骤 {3 + step_shift}: 验证 AGENTS.md
读取仓库根目录的 AGENTS.md，确认包含：
- CodeWiki LLM Wiki 章节（入口文件链接、使用建议）
- 纠正识别与经验沉淀（自我反思协议）
- 主动知识沉淀（触发信号、四问过滤、路由表）

## 后续工作流
初始化完成后，可以：
- **生成 Wiki**：使用 generate-wiki prompt 执行完整的文档生成流水线
- **知识管理**：直接使用 ingest_note / query_wiki 进行知识归档和检索
- **代码分析**：使用 code-analysis prompt 仅做结构分析不生成文档

## 注意事项
- init_wiki 是幂等的：重复执行不会破坏已有内容
- AGENTS.md 使用 HTML 注释标记隔离 CodeWiki 段落，用户自有内容不受影响
- schema.yaml 只在首次拷贝；后续 analyze_repo 会增量合并（保留用户自定义值）"""


def _prompt_team_memory_hook(args: dict[str, str]) -> str:
    repo_path = _resolve_path(args.get("repo_path", ""))
    action = (args.get("action") or "").strip().lower()
    if action == "enable":
        action_hint = "用户请求：**启用**采集 Hook。执行步骤 1 确认现状后直接进入步骤 2A。"
    elif action == "disable":
        action_hint = "用户请求：**关闭**采集 Hook。执行步骤 1 确认现状后直接进入步骤 2B。"
    else:
        action_hint = ("用户未指定动作：先执行步骤 1 检查当前状态并向用户报告，"
                       "再按其意愿选择步骤 2A（启用）或步骤 2B（关闭）。")
    return f"""管理 team-memory fusion 的对话自动采集 Hook（CodeBuddy hooks）。

{action_hint}

采集 Hook 只负责把对话捕获到 `repowiki/raw/`（仅采集、不蒸馏）；蒸馏是独立的显式步骤，见 distill-conversations prompt。

## 步骤 1: 检查当前状态
读取 `{repo_path}/.codebuddy/settings.json`：
- **已启用**：存在 hooks.SessionEnd、hooks.PreCompact、hooks.Stop 三个条目，且均执行 `python "{repo_path}/.codebuddy/hooks/capture_session_end.py"`（注意：CodeBuddy hooks 不展开环境变量，命令中必须写脚本的绝对路径，不能用 `$CODEBUDDY_PROJECT_DIR`）
- **未启用**：文件不存在，或没有上述条目

## 步骤 2A: 启用
1. 确认 `{repo_path}/.codebuddy/hooks/capture_session_end.py` 存在（随 CodeWiki 源码提供；若缺失，从 CodeWiki 源码仓库复制，不要凭记忆重写）
2. 创建或合并 `{repo_path}/.codebuddy/settings.json`，加入以下三个 hook 注册（保留文件中已有的无关配置）：

```json
{{
  "hooks": {{
    "SessionEnd": [
      {{ "matcher": "other", "hooks": [ {{ "type": "command", "command": "python \\"{repo_path}/.codebuddy/hooks/capture_session_end.py\\"", "timeout": 30 }} ] }}
    ],
    "PreCompact": [
      {{ "matcher": "*", "hooks": [ {{ "type": "command", "command": "python \\"{repo_path}/.codebuddy/hooks/capture_session_end.py\\"", "timeout": 30 }} ] }}
    ],
    "Stop": [
      {{ "hooks": [ {{ "type": "command", "command": "python \\"{repo_path}/.codebuddy/hooks/capture_session_end.py\\"", "timeout": 30 }} ] }}
    ]
  }}
}}
```

3. 前置条件：hook 启动的 python 进程必须能 import `codewiki` 包。满足任一即可：codewiki 已通过 pip 安装；hook 位于 CodeWiki 源码 checkout 内；或设置了 `CODEWIKI_HOME` 环境变量指向 checkout。都不满足时 wrapper 会跳过采集并输出带操作指引的 systemMessage（绝不阻塞 IDE）
4. 用模拟事件验证（先准备一个小的 transcript 文件，如 `[{{"role":"user","content":"测试"}}]` 存为 d:/tmp/conv.json；期望 stdout 的 systemMessage 中包含 `"status": "captured"`）：

```powershell
'{{"session_id":"verify-1","transcript_path":"d:/tmp/conv.json","cwd":"{repo_path}","hook_event_name":"SessionEnd","reason":"other"}}' | python "{repo_path}/.codebuddy/hooks/capture_session_end.py"
```

5. 验证完成后删除测试产物：`{repo_path}/repowiki/raw/` 下 verify-1 会话生成的 conv-*.md 文件

## 步骤 2B: 关闭
1. 从 `{repo_path}/.codebuddy/settings.json` 移除 SessionEnd、PreCompact、Stop 三个条目（其他 hook 保持不变；`"hooks": {{}}` 留空也可以）
2. 已采集的 raw 文件保留在 `repowiki/raw/`，之后仍可蒸馏；关闭采集不会删除它们

## 注意事项
- Hook 是 CodeBuddy 专属机制。其他运行时（Trae、CLI agent 等）请改用 `capture_conversation` MCP 工具手动采集
- Stop 事件每轮都会触发；会话级 supersede 去重保证每个会话在 raw/ 中始终只保留最新一份完整 transcript，不会膨胀
- Hook 永不蒸馏、永不写 wiki 页面、永不使 IDE 失败（异常仅输出到 stderr，退出码保持 0）"""


def _prompt_distill_conversations(args: dict[str, str]) -> str:
    repo_path = _resolve_path(args.get("repo_path", ""))
    return f"""把已采集的对话（repowiki/raw/）蒸馏为 Wiki 经验笔记。当用户说"从最近的对话中提取经验""distill my conversations"等时使用本流程。

**分工**：你（宿主 Agent）就是本流程的 LLM——你负责思考与知识提取；CodeWiki MCP 负责确定性工作（解析、去重、入库、评审流水线）。全程本地闭环，数据不出机器。

## 步骤 1: 收集待蒸馏的捕获
调用 distill_conversation(mode="prepare", repo_path="{repo_path}")
- 返回 `status="noop"` → 还没有任何捕获。给用户两个选择：启用自动采集（见 team-memory-hook prompt），或用 `capture_conversation` 立即采集当前对话。到此为止
- 返回 `status="prepared"` → 你得到 `system_prompt` 和 `captures[]`（每项含 `conversation_id` 与 `transcript`）

## 步骤 2: 提取知识（你就是 LLM）
对每条 capture，将 `system_prompt` 应用于其 transcript，产出一个 JSON 对象：

```json
{{
  "notes": [
    {{
      "title": "简短的陈述句标题",
      "note_type": "decision | lesson | pitfall | architecture | workaround",
      "related_modules": ["module_slug"],
      "tags": ["可选", "关键词"],
      "content": "## 背景 ... ## 正确做法/决策 ... ## 根因 ..."
    }}
  ]
}}
```

质量门槛：只提取**持久有效**、未来的 Agent 或队友能直接受益的知识（带 rationale 的决策、被纠正的假设、踩坑点、不明显的架构事实、含恢复条件的临时方案）。跳过闲聊、问候和临时任务状态。没有合格内容就返回 `{{"notes": []}}`——绝不凑数。

## 步骤 3: 提交确定性处理
调用 distill_conversation(mode="submit", repo_path="{repo_path}", distilled={{"<conversation_id>": <步骤2产出的JSON>, ...}})

工具会与已有笔记去重、经 ingest_note 写入草稿（status=draft）、标记/删除已处理的 raw 文件并重建检索索引。结果按 capture 报告：新建笔记数 / 去重抑制数 / 合并数。

## 步骤 4: 与用户评审（必须）
逐条展示产出的草稿（标题 + 一句话摘要），询问用户保留哪些。对接受的调用 `confirm_note`，对拒绝的调用 `reject_note`。**绝不静默确认**——草稿评审是知识飞轮的质量闸门。

## 备选：后台 worker（Mode B）
仅当 MCP server 进程配置了 MAIN_MODEL / LLM_BASE_URL / LLM_API_KEY 环境变量时，可改用 distill_conversation(run_in_background=true)，轮询 `repowiki/distill-jobs.json` 直到 status=completed，再执行步骤 4。IDE Agent 优先使用上面的 prepare/submit 流程。"""


# ===================================================================
#  Registration
# ===================================================================

def register(server):
    """Register prompt handlers on the given MCP Server instance."""
    from mcp.types import Prompt, PromptArgument

    @server.list_prompts()
    async def list_prompts() -> list:
        """List available workflow prompt templates."""
        return [
            Prompt(
                name="generate-wiki",
                title="生成代码 Wiki",
                description="完整的代码仓库 Wiki 生成流水线：分析→聚类→逐模块撰写→总览→质检→关闭会话",
                arguments=[
                    PromptArgument(
                        name="repo_path",
                        description="要分析的代码仓库路径（相对路径基于当前工作目录，默认当前目录）",
                        required=False,
                    ),
                    PromptArgument(
                        name="output_dir",
                        description="Wiki 输出目录（默认: <repo>/repowiki）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="extract-knowledge",
                title="外部文档知识抽取",
                description="导入外部文档并从中抽取实体和概念，生成结构化知识页面并构建 wikilink 图谱。两阶段流程：骨架提取→去重检查→证据校验→页面撰写。",
                arguments=[
                    PromptArgument(
                        name="source_path",
                        description="要导入并提取知识的外部文档的绝对路径（支持 PDF/MD/DOCX/HTML）",
                        required=False,
                    ),
                    PromptArgument(
                        name="output_dir",
                        description="Wiki 输出目录（默认: <cwd>/repowiki）",
                        required=False,
                    ),
                    PromptArgument(
                        name="granularity",
                        description="提取粒度：focused（3-7 核心项）| standard（适中覆盖）| exhaustive（应提尽提）。缺省遵循 schema.yaml 的 extraction_granularity",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="search-wiki",
                title="知识库搜索",
                description="高效搜索 Wiki 知识库的策略指引：BM25 搜索、图谱扩展、深度阅读",
                arguments=[
                    PromptArgument(
                        name="query",
                        description="搜索关键词或自然语言问题",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="quality-check",
                title="文档质量审计",
                description="对已生成的 Wiki 执行全面质量检查：过时引用、断链、覆盖率、循环依赖",
                arguments=[
                    PromptArgument(
                        name="output_dir",
                        description="Wiki 输出目录",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="incremental-update",
                title="增量更新 Wiki",
                description="检测代码变更并增量更新受影响的 Wiki 模块文档",
                arguments=[
                    PromptArgument(
                        name="repo_path",
                        description="代码仓库路径（相对路径基于当前工作目录，默认当前目录）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="workspace-analysis",
                title="多仓库工作区分析（含跨服务拓扑）",
                description=(
                    "扫描父目录下的多个 git 仓库，为每个生成独立 Wiki 并自动执行跨服务分析："
                    "RouteNode 匹配（HTTP+MQ，覆盖 Py/Java/JS/TS/Go）、Mermaid 服务拓扑图、"
                    "基础设施扫描（docker-compose/.env/application.yml）。可搭配 codebase-memory-mcp "
                    "做语义级深度追踪。"
                ),
                arguments=[
                    PromptArgument(
                        name="workspace_path",
                        description="包含多个 git 仓库的父目录路径（相对路径基于当前工作目录，默认当前目录）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="cross-service-trace",
                title="跨服务调用链追踪",
                description=(
                    "对指定根服务执行跨服务调用链分析：先走 CodeWiki RouteNode 静态匹配（HTTP 路由 + "
                    "MQ 生产者/消费者），再用 codebase-memory-mcp trace_path(mode='cross_service') "
                    "做多跳语义追踪，产出调用链图 + 架构诊断（循环依赖/扇入热点/未匹配路由）。"
                ),
                arguments=[
                    PromptArgument(
                        name="workspace_path",
                        description="包含多个 git 仓库的工作区根目录（相对路径基于当前工作目录，默认当前目录；须已执行过 analyze_workspace）",
                        required=False,
                    ),
                    PromptArgument(
                        name="filter_value",
                        description="追踪起点：服务名 / HTTP 方法 / URL 子串 / 路径前缀（可在对话中补充）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="code-analysis",
                title="代码结构分析（不生成 Wiki）",
                description=(
                    "仅解析代码结构、构建函数级调用图、查询依赖和评估修改影响范围，"
                    "不生成任何 Wiki 文档。分析结果缓存在 SQLite 中，后续可随时继续生成 Wiki。"
                ),
                arguments=[
                    PromptArgument(
                        name="repo_path",
                        description="要分析的代码仓库路径（相对路径基于当前工作目录，默认当前目录）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="impact-review",
                title="修改影响范围评估",
                description=(
                    "对指定组件或文件执行传递性影响分析（BFS 遍历），评估修改的爆炸半径："
                    "谁依赖我（depended_by）或我依赖谁（depends_on），输出模块级聚合、"
                    "高风险组件识别和完整调用链路。"
                ),
                arguments=[
                    PromptArgument(
                        name="repo_path",
                        description="代码仓库路径（须已执行过 analyze_repo 或 code-analysis）",
                        required=False,
                    ),
                    PromptArgument(
                        name="target",
                        description="分析目标：组件 ID（如 src/auth.py::AuthService）或文件路径（留空可在对话框中填写）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="architecture-review",
                title="架构审查与热点分析",
                description=(
                    "通过依赖图分析理解代码库的高层架构：识别核心层/服务层/应用层、"
                    "发现依赖热点和耦合风险、定位入口点和模块边界。"
                ),
                arguments=[
                    PromptArgument(
                        name="repo_path",
                        description="代码仓库路径（相对路径基于当前工作目录，默认当前目录）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="ingest-note",
                title="经验知识归档",
                description=(
                    "将设计决策、经验教训、架构 rationale、踩坑记录等知识归档到 Wiki 知识库。"
                    "支持 8 种笔记类型，自动 BM25 索引，可通过 query_wiki 检索。"
                ),
                arguments=[
                    PromptArgument(
                        name="output_dir",
                        description="Wiki 输出目录（默认: <repo>/repowiki）",
                        required=False,
                    ),
                    PromptArgument(
                        name="note_type",
                        description="笔记类型：decision | lesson | architecture | bug_fix | pitfall | known_issue | workaround | general（默认 general）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="init-wiki",
                title="初始化 Wiki 工作区",
                description=(
                    "零配置初始化：创建目录结构、拷贝带注释的 schema.yaml 模板、"
                    "写入 AGENTS.md（含使用建议和自我反思协议）。"
                    "在开始任何 Wiki 生成或知识管理之前执行一次。"
                ),
                arguments=[
                    PromptArgument(
                        name="repo_path",
                        description="仓库根目录路径（相对路径基于当前工作目录，默认当前目录）",
                        required=False,
                    ),
                    PromptArgument(
                        name="output_dir",
                        description="Wiki 输出目录（默认: <repo>/repowiki）",
                        required=False,
                    ),
                    PromptArgument(
                        name="enable_hook",
                        description="是否启用 IDE 对话自动采集 Hook（team-memory fusion）：true/1 会在初始化指引中追加 hook 启用说明；留空或 false 则跳过。Hook 默认关闭，仅采集对话不蒸馏。",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="team-memory-hook",
                title="启用/关闭对话自动采集 Hook",
                description=(
                    "管理 team-memory fusion 的 CodeBuddy 对话采集 Hook：检查现状、"
                    "启用（注册 SessionEnd/PreCompact/Stop 三个事件）或关闭。"
                    "Hook 只采集对话到 repowiki/raw/，不蒸馏。"
                ),
                arguments=[
                    PromptArgument(
                        name="action",
                        description="要执行的动作：enable（启用）| disable（关闭）；留空则先检查现状再按用户意愿选择",
                        required=False,
                    ),
                    PromptArgument(
                        name="repo_path",
                        description="仓库根目录路径（相对路径基于当前工作目录，默认当前目录）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="distill-conversations",
                title="蒸馏对话提取经验",
                description=(
                    "把 repowiki/raw/ 中已采集的对话蒸馏为经验笔记：宿主 Agent 充当 LLM，"
                    "distill_conversation(mode=prepare) 取 transcript → Agent 提取知识 → "
                    "mode=submit 交回做去重/草稿入库/评审。全程本地闭环，蒸馏产出须 confirm_note 确认。"
                ),
                arguments=[
                    PromptArgument(
                        name="repo_path",
                        description="仓库根目录路径（相对路径基于当前工作目录，默认当前目录）",
                        required=False,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, str] | None) -> Any:
        """Return a workflow prompt template with step-by-step agent instructions."""
        from mcp.types import GetPromptResult, PromptMessage, TextContent as PromptTextContent
        args = arguments or {}

        prompts_map = {
            "generate-wiki": _prompt_generate_wiki,
            "extract-knowledge": _prompt_extract_knowledge,
            "search-wiki": _prompt_search_wiki,
            "quality-check": _prompt_quality_check,
            "incremental-update": _prompt_incremental_update,
            "workspace-analysis": _prompt_workspace_analysis,
            "cross-service-trace": _prompt_cross_service_trace,
            "code-analysis": _prompt_code_analysis,
            "impact-review": _prompt_impact_review,
            "architecture-review": _prompt_architecture_review,
            "ingest-note": _prompt_ingest_note,
            "init-wiki": _prompt_init_wiki,
            "team-memory-hook": _prompt_team_memory_hook,
            "distill-conversations": _prompt_distill_conversations,
        }

        handler = prompts_map.get(name)
        if not handler:
            return GetPromptResult(
                description=f"Unknown prompt: {name}",
                messages=[PromptMessage(
                    role="user",
                    content=PromptTextContent(type="text", text=f"未知的 Prompt 模板: {name}。可用模板: {', '.join(prompts_map.keys())}"),
                )],
            )

        text = handler(args)
        return GetPromptResult(
            description=f"CodeWiki 工作流指引: {name}",
            messages=[PromptMessage(
                role="user",
                content=PromptTextContent(type="text", text=text),
            )],
        )
