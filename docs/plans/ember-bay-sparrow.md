# analyze_repo 增加跨服务调用分析（Monorepo 支持）

## Context

当前跨服务调用分析仅在 `analyze_workspace`（多仓库工作区）中执行。但像 CodingHub 这样的 monorepo 项目，虽然是单个 git 仓库，内部却包含多个子服务（如 backend、frontend、各微服务模块）。用户希望 `analyze_repo` 也能自动检测子服务边界并执行跨服务调用分析。

核心发现：`CrossServiceMatcher` 是基于标签的分区引擎，`repo_name` 只是字符串标签，不依赖 git。只要给不同子服务分配不同标签，匹配器无需修改即可工作。

## 实现方案

### 1. 新增：子服务检测器

**新文件**: `codewiki/src/be/dependency_analyzer/analysis/service_detector.py`

```python
def detect_services(repo_path: Path) -> Dict[str, Path]:
    """检测 monorepo 内的子服务边界，返回 {service_name: relative_path}"""
```

检测策略（按优先级）：
- **docker-compose.yml**: 解析 services 定义，提取 build.context 目录作为服务路径
- **多 Dockerfile**: 扫描不同子目录下的 Dockerfile，每个代表一个可部署服务
- **多构建清单**: 检测子目录中的 `go.mod`、`pom.xml`、`package.json`（含 start/main 脚本）、`pyproject.toml`、`setup.py`
- **约定目录**: `services/`、`apps/`、`microservices/` 下的直接子目录
- **Spring Boot**: `application.yml` 中的 `spring.application.name`

过滤规则：
- 排除 `node_modules`、`.venv`、`dist`、`build`、`test`、`tests`、`__pycache__` 等
- 服务路径深度限制 ≤ 3 层（避免误检）
- 至少检测到 2 个服务才触发跨服务分析

### 2. 修改：路由标签重分配

**修改文件**: `codewiki/mcp/tools/analysis.py`

在 `handle_analyze_repo` 中，路由缓存之后（约 line 149 `cache.batch_insert_routes` 之后）插入：

```python
# 子服务检测 + 跨服务分析
from ...analysis.service_detector import detect_services
services = detect_services(repo_path)
cross_service_info = {}
if len(services) >= 2:
    # 1. 按文件路径前缀将路由重新分配到子服务
    retagged_routes = _retag_routes_by_service(routes, services, repo_name)
    # 2. 更新缓存中的 repo_name
    cache.batch_insert_routes(retagged_routes, incremental=False)
    # 3. 运行 CrossServiceMatcher
    cross_service_info = _run_intra_repo_cross_service(repo_path, output_dir, services, retagged_routes)
```

路由重分配逻辑（新增辅助函数 `_retag_routes_by_service`）：
- 对每条路由的 `file_path`，找到最长匹配的子服务路径前缀
- 将 `repo_name` 替换为子服务名（如 `"CodingHub/backend"` → `"backend"`）
- 未匹配任何子服务的路由保留原 repo_name，标记为 `"_root"`

### 3. 新增：单仓库跨服务分析函数

**修改文件**: `codewiki/mcp/tools/analysis.py`（或抽取到 `workspace_analyzer.py` 复用）

```python
def _run_intra_repo_cross_service(repo_path, output_dir, services, routes) -> Dict:
    matcher = CrossServiceMatcher()
    # 按子服务分组路由
    for svc_name, svc_routes in group_by_service(routes):
        matcher.add_repo_routes(svc_name, svc_routes)
    topology = matcher.match()
    # 渲染 + 持久化（复用 TopologyVisualizer）
    # 写入 output_dir/.meta/cross_service_links.json, workspace_routes.json
    # 运行 InfraScanner（指向 repo_path）
    return {"total_routes": ..., "total_links": ..., "cross_service_md": ...}
```

### 4. 修改：analyze_repo 响应增加 cross_service 字段

在返回的 JSON 中增加：
```json
{
  "cross_service": {
    "services_detected": ["backend", "frontend", "worker"],
    "total_routes": 42,
    "total_links": 8,
    "total_unmatched": 5
  }
}
```
仅在检测到 ≥2 个子服务时出现。

### 5. 修改：query_cross_service 兼容单仓库

**修改文件**: `codewiki/mcp/tools/cross_service.py`

当前只查找 `workspace_path / "workspace-wiki" / ".meta"`。增加回退路径：
```python
meta_dir = workspace_path / "workspace-wiki" / ".meta"
if not meta_dir.exists():
    meta_dir = workspace_path / "repowiki" / ".meta"  # 单仓库回退
```

### 6. 修改：server.py 工具描述更新

- `analyze_repo` 的 description 增加跨服务检测说明
- `analyze_repo` inputSchema 增加可选参数 `detect_services`（boolean，默认 true）
- `query_cross_service` description 补充单仓库场景说明

### 7. 更新 Prompt

- `workspace-analysis` prompt 中补充 monorepo 说明
- 可选：新增 `monorepo-analysis` prompt 引导单仓库跨服务工作流

## 涉及文件

| 文件 | 操作 |
|------|------|
| `codewiki/src/be/dependency_analyzer/analysis/service_detector.py` | **新建** |
| `codewiki/mcp/tools/analysis.py` | 修改：集成子服务检测 + 跨服务分析 |
| `codewiki/mcp/tools/cross_service.py` | 修改：meta_dir 回退路径 |
| `codewiki/mcp/server.py` | 修改：工具描述 + inputSchema |
| `codewiki/src/be/dependency_analyzer/analysis/cross_service_matcher.py` | 不修改（标签机制已满足） |
| `codewiki/src/be/dependency_analyzer/analysis/topology_visualizer.py` | 不修改（直接复用） |

## 验证方式

1. 对 CodingHub 项目执行 `analyze_repo`，确认检测到子服务并输出跨服务拓扑
2. 对普通单服务项目执行 `analyze_repo`，确认无子服务时跳过（无 cross_service 字段）
3. 执行 `analyze_workspace` 确认原有多仓库流程不受影响
4. 用 `query_cross_service` 查询单仓库的跨服务结果
