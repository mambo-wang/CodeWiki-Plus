### 2026-08-29 15:58

为 init_workspace 增加“首次初始化布局强制闸门”与“workspace.json 总是写入”两项行为（用户反馈：初始化不问布局模式、且 repowiki/.meta/ 下没有 workspace.json）。

改动要点：
1. handle_init_workspace 首次初始化（骨架不齐备 + 无持久化配置 + 未传 layout）时不写任何产物，返回 status="needs_layout_decision" + 两选项，由调用方 Agent 征询用户后带 layout 重调；clone-only 接管与有配置的重跑豁免闸门。
2. workspace.json 两种布局都写入（此前仅 centralized 写，colocated 以“无配置=默认”隐式表达，反转了设计文档 D11 的零新增文件承诺）；clone-only 接管模式为无配置的存量工作区补写（backfilled）。
3. registry schema 重新暴露 layout（enum colocated/centralized），工具描述写明“先问用户”；_prompt_init_workspace 重排步骤1分支顺序（全新目录判定提到骨架缺失之前，修复了全新目录被误匹配为“骨架有缺失”而跳过询问的歧义），并补 needs_layout_decision 处理。
4. 测试：_init 辅助默认 layout="colocated"（layout=None 模拟省略）；新增 TestLayoutDecisionGate×5；schema 断言、colocated 写配置断言、登记表≠探测信号用例改为“init 后删配置模拟存量”；同步适配 test_layout_routing / test_remove_repo_cleanup / test_workspace_analyzer_layout / test_hook_registry（“自动克隆”断言本就已与 prompt 文案脱节，改为“补克隆”）。
5. 文档：管理模型文档 §4.1/§5、README 中英文工具表与 prompt 表同步；设计文档与系列文章作为历史记录未动。

验证：全量测试 590 过 2 跳过 0 失败；ruff 通过；真机跑通闸门→带参重调→无参重跑沿用→删配置后补写四步。

注意：用户已确认两项决策——强制闸门（而非软性指引）与总是写入（含存量补写）。
