# 集中式 Wiki 布局（layout=centralized）— 实现测试报告

日期：2026-08-29
分支：develop（业务仓 codewiki-plus）
范围：工单 01–10 全部实现（`.scratch/centralized-wiki-layout/issues/`）
规格：`.scratch/centralized-wiki-layout/spec.md`；设计文档：`docs/多仓Harness工作区-集中式Wiki布局设计方案.md`

## 1. 结论

**全部通过。** 全量测试 565 通过 / 2 跳过 / 0 失败；ruff lint + format 全树通过；功能基线（v5.5.0）零回归——所有默认路径（`colocated`/单库）行为逐字节不变，新行为全部由显式 `layout="centralized"` 或集中式语料库内的参数触发。

| 指标 | 基线（29b9f3e，v5.5.0） | 实现后（0b8078e） |
|------|------------------------|-------------------|
| 收集用例 | 470 | 567 |
| 通过 | 468 | 565 |
| 跳过（平台相关，与本特性无关） | 2 | 2 |
| 失败 | 0 | 0 |
| 净增测试 | — | **+95** |

环境：Windows Server 2019 / Python 3.12.13（项目 .venv）/ pytest 9.1.1 / ruff 0.16.3。

## 2. 工单实现与测试覆盖

| 工单 | 提交 | 交付 | 新增测试 |
|------|------|------|----------|
| 01 跨平台文件锁泛化 | `aba7a61` | `src/locks.py` `file_lock`（线程层+OS 层双保险；句柄即锁柄；加锁失败降级仍写） | `test_locks.py` ×5：线程/多进程并发读写不交错、计数器读改写、缺文件创建、追加兼容 |
| 02 布局奠基 | `aba7a61` | `workspace_layout` 解析模块（四护栏：只认 workspace.json、成员校验、三态回退、进程缓存）；`init_workspace(layout)`；AGENTS.md 布局变体 | `test_workspace_layout.py` ×18：单库零影响、防劫持、登记表≠探测信号、三态回退、缓存、配置幂等/冲突/自定义 output_dir 拒绝、约定块变体 |
| 03 建仓集中行为 | `0ee5410` | 分区骨架、无仓内 repowiki、移除业务仓 CodeWiki 死引用块、repo-map 集中变体 | ×4：骨架+块移除+其余内容保留、colocated 不变、目录缺失跳过、幂等 |
| 04 页型路由+来源标 | `e1cceb0` | `routing_for_write`/`default_output_dir`；module→分区、共享池打标；后写覆盖+锁内来源累积；analyze_repo 布局感知 | `test_layout_routing.py` ×21：路由接缝、来源累积（含并发 12 线程不丢来源）、分区、write/ingest 集成、colocated 回归 |
| 05 一跳检索+repo= 过滤 | `b90b1a4` | `repo=` 三态并集（分区∪带标∪全局）；3 倍预算补偿；非集中语料库完全惰性 | `test_query_repo_filter.py` ×8：三态命中、负例排除、幽灵仓只剩全局、分区语料库、单库完全无效、一跳默认 |
| 06 三种作用域 | `a39d553` | `parse_scope_arg`；scope=缺省/`"global"`/列表；显式重定范围精确替换 | `test_scope_writes.py` ×19：解析、全局清除、精确设置、覆盖重定范围、端到端 repo= 命中 |
| 07 运行时数据 | `94b9f28` | capture/distill/close_session/source_ingest/task_manager 落工作区根；格式逐字节不变（ADR-0001/0002） | `test_runtime_layout.py` ×6：解析、采集落点、任务记忆全流程+时间戳头格式断言、双布局对照 |
| 08 analyze_workspace | `9848eac` | 逐仓目标布局感知；`generate_repo_wikis`（默认 false）；拓扑与生成解耦 | `test_workspace_analyzer_layout.py` ×4：拓扑单跑、生成填充、生成后重跑、colocated 开关忽略 |
| 09 lint 布局纪律 | `6406f20` | `layout_violations`：知识回流 warning、缺来源标 info（孤儿浮出）；非集中完全惰性 | `test_lint_layout_violations.py` ×5：合规零报、回流告警、孤儿提示、多仓标通过、非集中惰性 |
| 10 移除清理 | `0b8078e` | 删分区；共享池来源逐页锁内清理（多来源移除其一、唯一来源解除标注成孤儿）；知识不自动删 | `test_remove_repo_cleanup.py` ×5：全量清理、孤儿被 lint 浮出、移除后检索态、colocated 对照、未登记安全错误 |

## 3. 关键验收标准核对

- **modules 进分区、其余进共享池带标**：`test_layout_routing.py::TestWriteDocFileCentralized`、`TestIngestNoteCentralized` ✓
- **来源只增不减、并发不丢**：`test_provenance_accumulates_across_repos`、`TestConcurrentSharedPool`（12 线程）✓
- **三作用域（单仓/多仓/全局）可写可查**：`test_scope_writes.py::TestScopedKnowledgeQueryable` ✓
- **集中一跳 / `repo=` 三态并集 / 非集中惰性**：`test_query_repo_filter.py` 全组 ✓
- **运行时数据工作区根、格式不变**：`test_runtime_layout.py`（含 `### ` 时间戳头断言）✓
- **拓扑总执行、生成可选、colocated 忽略**：`test_workspace_analyzer_layout.py` ✓
- **布局纪律 lint、孤儿交人工**：`test_lint_layout_violations.py` + `test_remove_repo_cleanup.py::test_orphan_surfaced_by_lint` ✓
- **移除不留孤儿、知识不自动删**：`test_remove_repo_cleanup.py::test_full_cleanup` ✓
- **单库/colocated 零影响**：每张工单均有对照用例；护栏专项 `test_registration_table_alone_is_not_a_workspace`、`test_unregistered_dir_not_hijacked`、`test_repo_filter_inert_outside_centralized_corpus` 等 ✓

## 4. 质量门

- `ruff check codewiki/ tests/`：通过（0 违规）
- `ruff format`：全部已格式化
- 全量 pytest：565/565 通过（2 个跳过为既有平台相关跳过，与本特性无关）

## 5. 已知限制（设计决策，见设计文档 §13/§15）

1. **v1 无布局迁移工具**：colocated↔centralized 切换为手工步骤（设计文档 §13）；`init_workspace` 拒绝就地换布局。
2. **集中式下 `project.json` last-wins**：多仓共用工作区 `.meta` 时，session-free 缓存定位只指向最后分析的仓；会话内流程不受影响。
3. **`repo=` 过滤仅作用于关键词检索**：overview/directory/detail 等渐进阅读模式 v1 不接入。
4. **缺来源标检查为 info 级提示**：无标＝全局本身合法，检查的真实职责是让移除产生的孤儿浮出交人工裁决。
5. **锁的加锁失败语义**：保持旧版"降级仍写"（纯 prefactor 保真），极端文件系统上退化为线程层。

## 6. 提交清单（develop）

```
0b8078e feat: remove_workspace_repo 集中式知识清理（工单 10）
6406f20 feat: lint_wiki 布局纪律检查（工单 09）
9848eac feat: analyze_workspace 集中模式与 generate_repo_wikis（工单 08）
94b9f28 feat: 运行时数据集中模式落工作区根共享区（工单 07）
a39d553 feat: 手工沉淀的三种作用域标注（工单 06）
b90b1a4 feat: query_wiki 一跳检索与 repo= 范围过滤（工单 05）
e1cceb0 feat: 布局感知页型路由与共享池来源标（工单 04）
0ee5410 feat: add_workspace_repo 集中模式行为（工单 03）
aba7a61 feat: 集中式布局奠基——布局配置、工作区解析与跨平台文件锁（工单 01/02）
cce5c5b docs: 集中式 Wiki 布局设计文档 + spec + 工单 01-10
```

累计变更（相对基线）：27 文件，+2889 / −137 行。
