# CodeGraph 增强

CodeGraph 提供调用图、影响范围分析和跨文件依赖追踪能力，与 CodeWiki 的组件分析互补——CodeWiki 告诉你「有哪些组件」，CodeGraph 告诉你「组件之间的调用和依赖关系」。

## 阶段 1 增强

在 `analyze_repo` 完成后，执行以下补充步骤：

1. `codegraph_status` — 检查索引健康状态，记录 file_count / node_count / edge_count / languages
2. `codegraph_files`（`outputFormat: "grouped"`）— 获取按语言分组的文件树和每文件符号数
3. `codegraph_explore`（`query: "main entry point server initialization"`, `maxFiles: 8`）— 了解项目入口和启动流程

这些信息帮助你从**结构视角**理解项目全貌。

## 阶段 2：验证聚类

在初步聚类后，用调用图数据验证和优化分组：

1. 对每个候选模块的核心符号，调用 `codegraph_callers` 和 `codegraph_callees`，发现跨模块依赖
2. 如果两个候选模块之间存在大量互相调用 → 考虑合并为一个模块
3. 如果某个符号被多个模块的符号频繁调用 → 可能属于独立的「共享基础设施」模块
4. `codegraph_explore`（`maxFiles: 6`）用候选模块名或目录名搜索，确认模块边界

**本质**：CodeWiki 的 Tree-sitter 分析告诉你「有哪些组件」，CodeGraph 的调用图告诉你「哪些组件在协作」。协作紧密的组件应该归入同一模块。

## 阶段 3：调用关系

为每个叶模块收集调用关系数据，丰富文档中的「依赖关系」章节：

1. `codegraph_callers`（`limit: 10`）— 模块内核心类/函数的上游调用者
2. `codegraph_callees`（`limit: 10`）— 模块内核心类/函数的下游依赖
3. `codegraph_impact`（`depth: 2`）— 关键组件的变更影响范围

写入文档的「依赖关系」章节：

- **上游依赖**（谁调用了这个模块）：主要调用者及其所在模块
- **下游依赖**（这个模块调用了谁）：主要被调用者及其所在模块
- **变更影响**（改了这个模块会影响谁）：对关键组件列出影响范围

## 阶段 4 增强

用阶段 1 收集的 CodeGraph 数据补充仓库总览：

- 在架构图中体现模块间的调用方向（来自调用图数据）
- 列出项目的技术栈详情（来自 CodeGraph 的语言和框架检测）

## 增量元数据

在输出目录的 `.meta/` 子目录保存两个元数据文件：

**`.meta/module_map.json`** — 模块到源文件的映射：

```json
{
  "engine": {
    "files": ["internal/engine/loop.go", "internal/engine/reporter.go"],
    "key_symbols": ["AgentEngine", "Run", "Reporter"]
  }
}
```

**`.meta/wiki_metadata.json`** — 生成基线：

```json
{
  "commit_sha": "<git rev-parse HEAD>",
  "generated_at": "<ISO-8601 时间戳>",
  "modules": ["engine", "provider", "tools"],
  "codegraph_stats": {"file_count": 19, "node_count": 204, "edge_count": 400}
}
```

这两个文件让增量更新能利用 CodeGraph 的 impact 分析实现**符号级精度**的变更追踪。

## 增量更新（增强模式）

当 CodeGraph 可用且存在 `.meta/module_map.json` + `.meta/wiki_metadata.json` 时：

1. **检测变更**：`git diff <commit_sha>..HEAD --name-only`，过滤源文件变更
2. **映射到模块**：读取 `.meta/module_map.json`，找到变更文件所属的模块（直接影响模块）
3. **扩展影响范围**：对变更文件中的关键符号调用 `codegraph_impact(depth: 2)`，找出所有受波及的模块（级联影响模块）。这比标准模式的路径匹配更精准
4. 无变更 → 报告「文档已是最新」并停止
5. 重新生成受影响模块（重跑阶段 3）
6. 更新 `overview.md`（阶段 4）
7. 写入新的 `wiki_metadata.json`（新 commit SHA + 时间戳），除非模块结构变化否则保持 `module_map.json` 不变
