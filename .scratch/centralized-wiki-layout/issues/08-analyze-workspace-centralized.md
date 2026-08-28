# 08: analyze_workspace 集中模式 + generate_repo_wikis 选项

**What to build:** 工作区级跨服务拓扑分析在集中模式下正常工作——按布局从正确位置读取各仓知识（不再硬编码仓内知识库路径），产出工作区总览与跨仓元数据。新增显式选项"是否顺带逐仓生成代码 wiki"：默认关闭；开启时逐仓触发代码分析填充 modules 分区；colocated 下忽略该选项。

**Blocked by:** 04

**Status:** resolved — implemented in 9848eac (2026-08-29)

- [ ] 集中模式下拓扑产物（总览 + 跨仓元数据）正确；子仓硬编码路径已移除
- [ ] 生成选项默认 false；显式开启后各仓 modules 分区被正确填充
- [ ] 拓扑分析与生成选项在集中模式下可独立工作（只跑拓扑不生成、生成后拓扑读取新产物）
- [ ] colocated 行为不变，选项被忽略
