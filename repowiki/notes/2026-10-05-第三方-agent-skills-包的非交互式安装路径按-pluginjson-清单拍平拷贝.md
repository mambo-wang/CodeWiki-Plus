---
type: procedure
title: "第三方 agent skills 包的非交互式安装路径：按 plugin.json 清单拍平拷贝"
tags: ["procedure"]
aliases: ["skills.sh 安装", "第三方技能包安装", "mattpocock skills", "SKILL.md 扁平拷贝"]
metadata:
  date: 2026-10-05
  confidence_level: strong
  reason: "本次安装已实测校验（27 个技能全部被 Qoder 技能列表识别）"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.14.1, at: 2026-10-05T14:09:30Z }
stale_after: 2027-04-03
---

## 结论
安装 skills.sh 生态的技能包（如 mattpocock/skills）到 Qoder 时，不必用官方安装器，按上游 `.claude-plugin/plugin.json` 的 `skills` 清单把每个技能目录**拍平**拷到 `~/.agents/skills/<name>/` 即可。

## 为什么这样装
- `npx skills@latest add <owner>/<repo>` 是交互式 TUI（选技能、选 agent），非交互 shell 里跑不动。
- plugin.json 的 `skills` 数组就是上游认定的正式发布集，天然排除了 `skills/in-progress`、`skills/misc`、`skills/deprecated` 三档草稿与专用件。
- Qoder 只读一层目录（`~/.agents/skills/<name>/SKILL.md`），不认 engineering/productivity 分类层级，所以必须拍平。

## 装前必查的三点
1. **相对引用**：`grep -rn '\.\./' skills/**` —— 若技能内部无跨目录引用，拍平安全（mattpocock/skills 即如此，支持文件 `agents/openai.yaml`、`*.md` 附录、`template.sh` 都在技能目录内）。
2. **名字撞车**：与 `~/.agents/skills/` 已有目录、以及宿主内置技能名比对；撞名会静默覆盖或引发自动触发歧义。
3. **frontmatter 一致性**：`name:` 必须等于目录名，且逐个都有 `SKILL.md`。装完看系统技能列表是否刷新，作为真正被加载的证据。

## 已知副作用
- `disable-model-invocation: true` 的技能只能斜杠手动调用，不会出现在模型自动命中列表里；一次装 27 个别指望全部自动生效。
- 成套的工程流程技能（code-review / retro / research / triage）与本项目已有 codewiki 技能职能重叠，自动触发会撞车；先观察一轮再决定精简。
- 这类包多要求先跑一次仓库级 setup（配置 issue tracker、triage 标签、文档目录），会往 AGENTS.md 体系里新增一套约定，与既有知识飞轮配置并存需取舍。
- 装完是**可编辑副本**，不会后台更新；更新靠重新拉上游 + 覆盖拷贝，因此在 `~/WORK_skills/` 留一份带 commit hash 的安装记录。
