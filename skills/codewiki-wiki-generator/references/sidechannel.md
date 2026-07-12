# 文件侧通道详解

CodeWiki MCP 采用**文件侧通道**架构：大体量数据（组件列表、源码、依赖图、处理顺序）写入磁盘文件，MCP 只返回文件路径和精简摘要。你需要用自己的文件读取能力（Read 工具）读取 workspace 文件获取完整数据。

## Workspace 目录

```
{repo_path}/.codewiki/sessions/{session_id}/
```

## analyze_repo 直接生成的文件

调用 `analyze_repo` 后，以下文件**自动**写入 workspace：

| 文件 | 内容 | 读取时机 |
|------|------|----------|
| `summary.json` | 分析摘要：组件/叶子节点数量、语言统计、前 20 个叶子节点 ID | 阶段 1 立即读取 |
| `changes.json` | 增量变更信息（仅增量模式下生成） | 增量更新时读取 |
| `schema.json` | Schema 信息（条件生成，可能为 null） | 按需读取 |

## 按需生成的文件

以下文件需要通过对应工具调用**触发**后才会生成：

| 文件 | 触发工具 | 内容 |
|------|----------|------|
| `component_list.json` | `list_components` | 完整组件列表，每项含 `{"id", "type", "file"}` |
| `component_summary.json` | `list_components(summary: true)` | 按文件分组的组件摘要，每文件含 `{"count", "types", "classes"}` |
| `dependencies.json` | `list_dependencies` | 完整依赖图 |
| `processing_order.json` | `save_module_tree` 或 `get_processing_order` | 叶优先的文档生成顺序 |
| `sources/*.src` | `read_code_components` | 每个组件一个 `.src` 文件 |

## 重要说明

- SQLite 缓存模式下，组件数据存储在内存 SQLite 中，**不会**自动生成 `component_index.json` 或 `leaf_nodes.json`。必须调用 `list_components` 获取组件清单
- 聚类阶段优先使用 `summary: true` 模式获取轻量摘要（体积约为完整列表的 1/8）
- 生成文档时使用 `file_prefix` 按目录获取精确组件 ID
- `list_components` 无论传什么参数都写同一个 `component_list.json`，**并发调用会互相覆盖**，必须串行
