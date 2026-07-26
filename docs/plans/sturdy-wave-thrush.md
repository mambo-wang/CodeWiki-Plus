## Context

CodeWiki-CN 的 `analyze_repo` MCP 工具在 40000+ 组件的大仓库上超时。根因是多层的：MCP 事件循环被阻塞、AST 解析串行执行、ast_parser 存在 O(n×r) 线性扫描、Windows 平台单文件超时失效、文件树遍历冗余、排除模式匹配过重。需要实施 Phase 1（快速止血）和 Phase 2（核心提速）共 8 项优化。

## 修改文件清单

| 文件 | 改动项 |
|------|--------|
| `codewiki/src/be/dependency_analyzer/ast_parser.py` | #3 name 索引替代线性扫描 |
| `codewiki/src/be/dependency_analyzer/analysis/call_graph_analyzer.py` | #4 跳过可视化 + #5 并行 AST + #6 Windows 超时 |
| `codewiki/src/be/dependency_analyzer/analysis/repo_analyzer.py` | #7 排除模式预编译 + #8 单次遍历建树 |
| `codewiki/src/be/dependency_analyzer/analysis/analysis_service.py` | 透传 skip_visualization / max_workers |
| `codewiki/mcp/tools/analysis.py` | 拆分 handle_analyze_repo 为计算+后处理 |
| `codewiki/mcp/server.py` | #1 ProcessPoolExecutor 执行分析 |

## 实施顺序

### Step 1: ast_parser.py — name 索引 (独立、安全)

在 `_build_components_from_analysis()` 的组件注册循环后，构建 `name_to_ids: Dict[str, List[str]]` 索引。替换 lines 119-123 的线性扫描为 O(1) 查找。当 name 存在多个匹配时跳过（避免歧义依赖，比原代码取第一个匹配更正确）。

### Step 2: call_graph_analyzer.py — 跳过可视化 (独立)

`analyze_code_files()` 签名加 `skip_visualization: bool = False`。当 True 时跳过 `_generate_visualization_data()`，返回 `"visualization": None`。

### Step 3: repo_analyzer.py — 单次遍历 + 排除模式优化 (独立)

- `__init__` 中预分类排除模式：`_exclude_exact_names: set`（精确名称）、`_exclude_dir_prefixes: set`（目录前缀）、`_exclude_globs: list`（通配符）。
- `_should_exclude_path` 先查 set（O(1)），再跑 glob（仅剩余约 30 条）。
- `_build_file_tree` 中同步累加 `_file_count` 和 `_total_size_bytes`，去掉 `sorted()`。
- `analyze_repository_structure` 直接读累加器，不再调 `_count_files` / `_calculate_size`。

### Step 4: analysis_service.py — 透传参数

`_analyze_call_graph()` 加 `skip_visualization=False` 和 `max_workers=0` 参数，传递给 `call_graph_analyzer.analyze_code_files()`。

### Step 5: call_graph_analyzer.py — 并行 AST 解析 + Windows 超时

核心改动，最大收益项：

- 新增模块级函数 `_analyze_single_file_worker(repo_dir, file_info) -> dict`：在独立进程中分析单个文件，返回可 pickle 的 dict（Node.model_dump() 列表 + CallRelationship.model_dump() 列表）。内部按 language 分发到对应 analyzer（import 路径和方法名见现有 `_analyze_<lang>_file` 方法）。
- `analyze_code_files()` 加 `max_workers: int = 0` 参数（0 = auto = min(cpu_count, 8)）。
- 新增 `_analyze_parallel()` 方法：用 `ProcessPoolExecutor(max_workers=N)` 提交所有文件，`future.result(timeout=30)` 实现跨平台单文件超时。合并结果时重建 Node/CallRelationship 对象。
- 保留原串行路径作为 fallback（max_workers=1 或文件数 <=1）。

### Step 6: analysis.py — 拆分 handle_analyze_repo

- 新增 `_run_analysis(repo_path, output_dir, include_list, exclude_list) -> dict`：执行 DependencyGraphBuilder，返回 `{"components_data": {...}, "leaf_nodes": [...]}`。components_data 中的 Node 序列化为 model_dump() dict，depends_on 转为 list。
- 新增 `_reconstruct_components(components_data) -> Dict[str, Node]`：反序列化回 Node 对象。
- 新增 `handle_analyze_repo_post(arguments, analysis_result, store) -> str`：接收分析结果，重建 Node，创建 session，写 workspace 文件，返回 JSON。
- 保留原 `handle_analyze_repo` 供兼容（内部调用上述三个函数）。

### Step 7: server.py — ProcessPoolExecutor

- 新增模块级 `_analysis_executor: ProcessPoolExecutor`（max_workers=1，懒初始化）。
- 新增模块级 `_run_analysis_in_process()` 函数（pickle 安全的顶层函数，调用 `_run_analysis`）。
- `call_tool` 中 `analyze_repo` 分支改为：`await loop.run_in_executor(executor, _run_analysis_in_process, ...)` 拿到结果后调 `handle_analyze_repo_post` 完成 session/workspace 操作。

## 验证方式

1. 在 CodeWiki-CN 自身仓库运行 `python -m codewiki mcp`，调用 `analyze_repo`，对比改动前后的 `component_index.json` 和 `leaf_nodes.json`（应一致或仅有 name 歧义修复导致的微小差异）。
2. 检查 `summary.total_files` 和 `summary.total_size_kb` 与改动前一致。
3. 确认 MCP server 在 `analyze_repo` 执行期间能响应其他工具调用（如 `get_prompt`）。
4. Windows 上确认复杂文件不会导致分析卡死（30 秒超时生效）。
5. 运行 `tests/smoke_test_mcp.py`（如存在）。
