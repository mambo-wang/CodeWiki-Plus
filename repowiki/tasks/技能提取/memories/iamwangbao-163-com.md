### 2026-09-10 16:34

技能提取改造已落地并推送：commit eb7afc4（45 files，feat(skill): 打通流程型知识从采集到技能编译的完整通路）。改动含：采集层成功结果保留+三层名单（Tier2 只读排除名单 / Tier1b 编辑工具整块丢弃 / 单行120字符 / CODEWIKI_RAW_TOOL_DETAIL 开关）、note_types 新增 procedure 类型、skill_creator 候选 mtime 倒序+truncated+主干优先规则、skill_match 笔记打分（procedure 强信号、优先于场景）、registry 补 install/retire 契约。

### 2026-09-10 16:34

2 条知识笔记已确认 stable：决策『技能编译素材以笔记为主、场景为辅』+ pitfall『知识管线三类静默降级（黑名单vs白名单 / 候选排序截断 / install 契约不同步）』，均带交叉引用指向 2026-09-07 设计裁决进展笔记的 Q14/Q15。

### 2026-09-10 16:34

待办：windows-python-release 技能仍未 install —— 需重启 MCP server 使 registry 新 enum 生效，再 skill_creator(mode=install, name=windows-python-release)；replace_in_file 已加 Tier1b 整块丢弃（含 edit_file/apply_patch/str_replace 等同义变体）。

### 2026-09-10 16:34

技能提取改造已落地并推送：commit eb7afc4（45 files，feat(skill): 打通流程型知识从采集到技能编译的完整通路）。改动含：采集层成功结果保留+三层名单（Tier2 只读排除名单 / Tier1b 编辑工具整块丢弃 / 单行120字符 / CODEWIKI_RAW_TOOL_DETAIL 开关）、note_types 新增 procedure 类型、skill_creator 候选 mtime 倒序+truncated+主干优先规则、skill_match 笔记打分（procedure 强信号、优先于场景）、registry 补 install/retire 契约。

### 2026-09-10 16:34

2 条知识笔记已确认 stable：决策『技能编译素材以笔记为主、场景为辅』+ pitfall『知识管线三类静默降级（黑名单vs白名单 / 候选排序截断 / install 契约不同步）』，均带交叉引用指向 2026-09-07 设计裁决进展笔记的 Q14/Q15。

### 2026-09-10 16:34

待办：windows-python-release 技能仍未 install —— 需重启 MCP server 使 registry 新 enum 生效，再 skill_creator(mode=install, name=windows-python-release)；replace_in_file 已加 Tier1b 整块丢弃（含 edit_file/apply_patch/str_replace 等同义变体）。

### 2026-09-11 09:07

2026-09-11 核对结论：skill 自动编译能力不存在、也没有环境变量开关；全仓只有三条 hint 通道——_ide_hook UserPromptSubmit（draft 技能 containment≥0.5 且 prompt≥8 token）、note_consolidation L2 场景块（命令≥3 且 ≥2 条笔记背书）、distill_conversation 蒸馏产出撞草稿。阈值是代码常量，调参改 skill_match.py。

### 2026-09-11 09:07

待办未变：`windows-python-release` 技能尚未 install——需重启 MCP server 让 registry 新 enum 生效后执行 `skill_creator(mode="install", name=windows-python-release)`。
