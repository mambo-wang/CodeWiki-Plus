---
type: decision
title: skill_creator 增加技能包 scripts/ 资产通道：15 项设计决策全部定案
tags:
- codewiki
- decision
metadata:
  date: 2026-10-31
  confidence_level: weak
  task_id: 产品维护
  source_session: 183913c20fab44a9996c660b1278cb6b
  related_modules:
  - skill-creator
  - wiki-lint
  - mcp-registry
  severity: high
  source_ref: conversations/conv-我在内网电脑使用codewiki的时候，发现一个小问题，就是编译的技能里只有SKILL.md没有相关脚本，看可以优化吗？.md
  scene: 技能编译器资产通道设计
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.16.6
  at: 2026-10-31 01:42:38+00:00
stale_after: '2027-10-31'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-10-31T07:01:29Z'
---

## Background

用户在内网机器使用 CodeWiki 编译的技能时发现：`skill_creator` 编译产物只有 `SKILL.md` 单文件，正文引用的脚本既不在技能包里也不随 install 带走，新机器上技能触发后找不到脚本，不可移植。导火索案例：编译 `linseer-preset-multimal-asset` 技能时正文照搬笔记里的工具名 `hf_download.py` / `zip_assets.py`，而这两个脚本在用户本机 `G:\models`，不在技能包也不在工作区。

现状代码事实（2026-10-31 核对）：
- submit 只写单文件：`_create_skill_file` / `_update_skill_file` 落 `skills/<name>/SKILL.md`，无资产通道（`skill_creator.py:567-650`）
- install 也只复制 SKILL.md：`_mode_install` 生成 `.codebuddy/skills/<name>/SKILL.md`（`skill_creator.py:686-774`）
- 写作规范只禁绝对路径和密钥，无「脚本引用必须自包含」规则（`_SKILL_WRITING_SYSTEM`，`skill_creator.py:129-172`）
- lint 敏感串检查只有 absolute_path / secret_key 两类（`skill_creator.py:86-104`）

## Decision

经三轮 grill（Q1-Q15）用户逐项拍板，设计共识如下：

| # | 决策 |
|---|---|
| Q1 | 脚本内容由 agent 显式传入 `scripts[]`（filename + content），不做工作区路径自动抓取 |
| Q2 | MVP 只做 `scripts/` 可执行脚本，不做通用 assets |
| Q3 | 漂移哈希覆盖 scripts/ 全部文件内容，脚本修订触发 drift warning（现状哈希只算 name+description+body，`skill_creator.py:667-675`） |
| Q4/Q13 | 严重级拆分：`scripts/xxx.py` 规范写法缺文件 = submit **error**；裸 `xxx.py` 缺文件 = lint **warning** |
| Q5 | **不设脚本大小/数量限制**（用户明确选 B，推翻助手推荐的 32KB/5 个上限——靠 8KB 正文上限间接约束） |
| Q6 | 脚本内容过敏感串扫描（绝对路径/密钥），命中拒收 |
| Q7 | `action=updated` 再提交时 scripts[] **全量替换**（区别于 source_refs 只增不减，`skill_creator.py:619-623`） |
| Q8 | install 复制整个 scripts/ 到生效区；retire 删除生效区整个技能目录（顺带修掉现状只删单文件 `effect_file.unlink()` 的残留缺陷，`skill_creator.py:816-826`） |
| Q9/Q12 | 引用匹配认规范写法 + 裸文件名两种，扩展名白名单 `.py .sh .ps1 .js .ts .rb .pl` |
| Q10 | 不做 `scripts_file` 文件侧通道，撞 MCP 载荷上限再说（YAGNI） |
| Q11 | filename 扁平安全字符集（拒路径分隔符/`..`/空白），不支持子目录；校验复用「先拒原始串再规范化」思路（`skill_creator.py:506-513` 教训） |
| Q14 | lint 报孤儿脚本 warning（`unreferenced_script`：scripts/ 有文件但正文未引用） |
| Q15 | install 先清空生效区 scripts/ 再复制，保持草稿区/生效区两区一致 |

## 改动面

`skill_creator.py`（submit 校验+落盘、install/retire 目录级处理、哈希扩展）、`wiki_lint.py`（两条新检查：裸名缺文件 warning、孤儿脚本 warning）、`registry.py` schema、`prompts.py` 写作规范、测试、设计文档（放 `docs/`，沿用本仓设计方案文档惯例）。

## Rationale

值得持久化：这是一次完整的设计决策落定（15 项边界全部拍板），后续写设计文档与实施计划都要以此为准；其中 Q5 是用户明确推翻推荐的选择，Q8/Q15 顺带修掉两个现状缺陷，不记下来实施时容易回退到旧口径。

关键理由摘录：Q1 显式优于布局推导（Doctrine），自动抓取要把路径归属判断（本次翻车根源）请回来；Q7 脚本是可执行内容，bug 修复后旧版必须消失；Q13 规范写法是强承诺、裸名是弱信号，严重级跟信号强度走，避免正文提一句 `setup.py` 就被 error 卡住。
