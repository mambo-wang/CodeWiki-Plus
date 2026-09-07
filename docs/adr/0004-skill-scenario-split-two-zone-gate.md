# 0004. 技能与场景分轨，两区制守确认闸门

日期：2026-09-06
状态：已接受

## 背景

为承载「自动生成 SKILL」（把已确认知识编译成 SKILL.md 行为指令资产），需要决定技能
（skill）与既有场景块（scenario）的关系，以及生成的技能文件如何在不违反「落盘必经
确认闸门」Doctrine 的前提下安全生效。核心矛盾：SKILL.md 一旦落进 IDE 技能发现目录
（`.codebuddy/skills/`）即被宿主自动加载并可触发——草稿期文件若直接落生效区，确认
闸门形同虚设。定档调研见
`repowiki/wiki/comparisons/自动生成SKILL可行性-wikiskill闭环-vs-CodeWiki编译复用.md`
与 `repowiki/wiki/queries/skill-creator设计方案.md`（权衡三）。

## 决策

1. **技能与场景分轨**：scenario 是检索知识（agent 主动 `query_wiki` 按需查阅），
   skill 是行为指令（宿主 IDE 按 description 自动触发改变 agent 行为）。两者素材同源
   （已确认笔记）、消费链路不同，不合并为一种资产。
2. **草稿区技能进索引但不进召回**：草稿区 `repowiki/skills/` 参与索引构建与
   lint_wiki 扫描（管理通道），但不进入 query_wiki 的召回排序（避免 agent 把行为
   指令当检索知识引用，混淆两种语义）。
3. **两区制**：草稿落 `repowiki/skills/`（进索引进 lint、不生效），经用户确认后
   install 到生效区 `.codebuddy/skills/`（IDE 发现即生效）。install 是用户动作，
   工具不代劳；install 后的修订漂移只提示（lint warning + prepare 提示），不自动
   覆盖生效区。

## 理由

1. **单区 + status 标记不可行**：草稿期技能若落在生效区，IDE 即时发现并可触发，
   `status: draft` 标记没有任何机制强制力——闸门必须由目录隔离（IDE 不扫描
   repowiki/skills/）来物理保证。
2. **wikiskill 同构佐证**：其隔离 profile 机制（`backends/hermes.py` symlink 重建
   active 集）同样靠宿主技能发现边界实现"所见即 active 集"，语义等价但路径更重；
   两区制用目录边界达到同一效果，无需 profile 编排。
3. **检索双通道会造成语义混淆**：若技能可被 query_wiki 召回，agent 会把 SKILL 正文
   当知识引用，与"行为指令只经 IDE 触发"的消费模型冲突；scenario 已承担检索职责。

## 后果

- 生效区与草稿区可能漂移（草稿修订后生效区仍旧版）：这是有意代价，由 lint 的
  content_hash 一致性检查暴露、由用户决定 reinstall。
- `repowiki/skills/` 是新的受管目录：schema.yaml 需增 `page_types.skill`，
  lint/路由/索引相应感知；`.codebuddy/skills/` 不进 repowiki 任何扫描。
