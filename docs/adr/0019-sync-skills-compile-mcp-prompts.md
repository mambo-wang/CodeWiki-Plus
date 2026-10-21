# ADR-0019: MCP prompt 编译为宿主技能文件（sync-skills）

- **状态**：已接受（2026-10-20）；supersede ADR-0017 的「命令薄壳」部分（其 2026-10-03 工具通道补丁仍有效）

## 背景

ADR-0017 把 23 个 MCP 工作流提示词编译为 `<宿主配置目录>/commands/codewiki/*.md` 命令薄壳（`codewiki sync-commands`）。宿主生态转向 skills 目录：手动触发型 skill（frontmatter `disable-model-invocation: true`）常驻上下文归零、只能 `/名称` 显式调用（CodeBuddy 系约定，见 `repowiki/notes/2026-09-11-codebuddy-skills-三级渐进披露常驻只占-100-词元数据disable-model-invocation.md`；TRAE 侧同样认该字段），语义等价于「换格式的 command」——触发仍显式，不引入模型自动路由。用户拍板：23 条工作流入口**全量从命令薄壳改为技能薄壳**，命令薄壳整体退役。

## 关键事实

- skill 布局为一层拍平 `<dir>/skills/<name>/SKILL.md`：Qoder/共享库只读一层目录，不能嵌套命名空间（`repowiki/notes/2026-10-05-第三方-agent-skills-包的非交互式安装路径按-pluginjson-清单拍平拷贝.md`）——commands 时代的 `commands/codewiki/` 子目录命名空间必须改用名称前缀表达
- IDE 自动映射只有 prompt→command 一条通道（codebuddy），**没有 prompt→skill 通道**——codebuddy 不再豁免生成
- `.codebuddy/skills/` 是 skill_creator 的生效区（ADR-0004），但 skill_creator 的容量门（`_MAX_SKILLS`）与扫描只走草稿区 `repowiki/skills/`，install 按 name 定点拷贝，同目录共存互不干扰
- `_ide_hook` 的 UserPromptSubmit 草稿匹配只探测 `repowiki/skills` 与 `<repo>/skills`（`_ide_hook.py`），物理上够不到宿主 skills 目录——生成物不写 `status` 字段不会被误匹配为草稿
- en locale 的 description 含 `": "`，frontmatter 裸写是非法 YAML，description 必须双引号包裹
- `.gitignore` 原 `.qoder/skills/` 整目录忽略：git 不进入被忽略目录，目录内 negation 无效，须改为「忽略内容、不忽略目录」（`.qoder/skills/*` + `!.qoder/skills/codewiki-*/`）

## 决策

### 1. CLI 替换：`sync-commands` 删除，`sync-skills` 上位

原地改造重写面超过 80%（docstring/模板/命名/宿主判定/CLI 名全变），改名后 `sync_commands.py` 持续撒谎；无并行共存需求。参数不变：`--lang zh|en`、`--ide`、`--dry-run`、位置参数 `repo`。外部项目此前生成的 `commands/codewiki/*.md` 不会被自动清理，需在 CHANGELOG/help 中注明「存量命令薄壳手工删除一次」。

### 2. 内容形态 = 技能薄壳（SKILL.md）

frontmatter 固定三行（对齐 `.codebuddy/skills/grill-me/SKILL.md` 先例）：

```yaml
---
name: codewiki-<kebab-name>
description: "<i18n description，双引号包裹>"
disable-model-invocation: true
---
```

正文沿用命令薄壳语义：标题 + 描述 + `get_prompt(name=..., arguments={...})` 调用块 + 开关参数映射指引段（2026-09-29 事故修复语义不动）+ 「真源在 prompts.py」声明 + 手动触发说明（`/codewiki-<name>` 触发、不占常驻上下文）。权威仍在 MCP `get_prompt`，文件只是可见入口。**不渲染 `status` 字段**（钉死约定：工作流技能不是 skill_creator 两区制产物）。**整文件语言跟随 `--lang`**：frontmatter description 与标题/描述走 i18n，正文样板与开关映射指引按 zh/en 双态渲染（en 产物不残留中文段落；实施时用户明确要求中英文都顾及，取代 ADR-0017 时代「指引段中文硬编码」的沿袭口径）。

### 3. 命名 = 恒 `codewiki-` 前缀，推翻 ADR-0017 决策 4

ADR-0017 决策 4（zh 用标题 slug、en 用 prompt name）在 skill 布局下不成立：skill name 必须是 ASCII slug，且一层拍平后目录名即技能名——zh/en 双写会产出两套目录、CJK 目录名跨宿主兼容性未验证。目录名恒为 `codewiki-<kebab-name>`，`codewiki-` 前缀是拍平一层的命名空间等价物（避免与 skill_creator 产出及用户其他技能撞名）；`--lang` 决定整文件语言（见决策 2）。

### 4. 宿主判定：codebuddy 不再豁免

显式 `--ide`（qwenwork 无配置目录仍报错）> 枚举仓库根 IDE 配置目录（**含 codebuddy**）> 兜底 `.trae/skills/` 作仓库级技能登记处。

### 5. 覆盖策略 = 全量覆盖 + prune

每次执行全量重写目标 SKILL.md（快照口径同 ADR-0017 决策 7），并删除目标目录下不在本次渲染集合内的 `codewiki-*/` 目录（prune 只碰 `codewiki-` 前缀，绝不动用户其他技能；`--dry-run` 仅预览）——registry 未来瘦身时不留孤儿。

### 6. 产物入库口径不变

生成快照随仓库共享（同 ADR-0017 后的入库现状）；`.gitignore` 按「关键事实」第 6 条改法为 `.qoder/skills/codewiki-*/` 开例外。

### 7. 手动触发 = `disable-model-invocation: true` 固定渲染

23 条工作流全部是用户显式调用的入口，不开放模型自动路由（对齐 Team Doctrine「触发永远显式」）；不认该字段的宿主忽略未知 frontmatter 键，无害。

## 后果

- **正面**：工作流入口接入宿主 skills 体系；手动触发型常驻上下文归零（命令薄壳时代的命令文件本身不占常驻，但 skill 形态与宿主生态演进同向）；命名空间经 `codewiki-` 前缀与 skill_creator 产物及用户技能隔离；codebuddy 与其他宿主口径统一（一表驱动，无特例）。
- **负面**：trae/qoder 仓级 skills 目录的宿主识别**未经真机验证**（`.trae/skills/` 有入库先例但未验证 TRAE 原生识别仓级手动触发 skill；`.qoder/skills/` 此前由 IDE 插件自管理）——冒烟时真机确认后回写本 ADR 备注。**不延伸 hooks.yaml 的 `verified` 字段**：该字段语义是 hook 接线（事件名/wiring），与 skills 目录识别是两个维度，延伸会污染既有口径。
- **风险**：`disable-model-invocation` 是 CodeBuddy 系约定，其他宿主若实现不同（如完全不认该字段而自动路由），23 条全量进技能列表有误触发面——缓解：description 写作保持「条件 + 行动」精确口径，真机验证时重点观察。
- **迁移成本**：外部项目存量 `commands/codewiki/*.md` 需手工删除一次；本仓 46 个已入库命令文件随本决策实施一并 `git rm`。

## 开放点

- 若未来出现扫描宿主 skills 目录的工具，`status` 缺省被当 draft 的语义需重估（届时可渲染 `status: stable`，但会偏离三行 frontmatter 约定，需重新决策）。

## 实现顺序

1. ADR-0019 + ADR-0017 状态行
2. `sync_skills.py` 新建 + `main.py` 注册 + `sync_commands.py` 删除 + mypy 基线死条目清理
3. `test_sync_skills.py` 重写 + 措辞断言两文件更新
4. `prompts.py` 两处文案（提取 `_SYNC_SKILLS_STEP` 常量消双副本）+ i18n 四处
5. `.gitignore` + 删 46 个存量命令文件 + 跑 sync-skills 生成新产物入库
6. CONTEXT.md 术语与索引
7. 全量验证（聚焦 pytest / okf 契约 / dry-run 冒烟 / ruff / mypy / 全量 pytest）
