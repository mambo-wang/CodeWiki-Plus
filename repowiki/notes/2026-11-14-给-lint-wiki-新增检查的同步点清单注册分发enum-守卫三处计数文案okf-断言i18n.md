---
type: procedure
title: "给 lint_wiki 新增检查的同步点清单：注册分发、enum 守卫、三处计数文案、okf 断言、i18n"
tags: ["procedure"]
metadata:
  date: 2026-11-14
  confidence_level: weak
  task_id: 他山之石
  source_session: "42b9be13-a446-8a36-9c69-8cd63018803e"
  related_modules: ["MCP_Tools_Quality", "MCP_Server"]
  severity: medium
  source_ref: "conversations/conv-https-mp.weixin.qq.com-s-2IUREDltOXzXECO7tWIoPA-阅读文章看看有值得借鉴的.md"
  scene: "lint_wiki 新增检查"
status: draft
author: wanderingbug
generated: { by: codewiki/5.16.7, at: 2026-11-14T01:36:17Z }
stale_after: 2027-05-13
origin: conversation

---

## 适用场景

向 `codewiki/mcp/tools/wiki_lint.py` 增加一项新检查（本次为溯源背撑检查做写前核查时摸清）。看似只改一个文件，实际有 5 处契约/文案同步点 + 守卫测试，漏改会静默漂移。

## 步骤与同步点

1. **注册**：把检查名加进 `_ALL_CHECKS` 集合（`wiki_lint.py:25-66`，会话实测 26 项）。**无装饰器注册机制**。
2. **分发**：在 `handle_lint_wiki` 内加逐项 `if "<name>" in checks` 分支（:2533-2648）。入参 `checks` 对未知名**静默过滤**、且无 `mode` 参数（:2460-2478、`codewiki/mcp/registry.py:862-920`）——名字拼错不报错，只是不跑。
3. **registry enum**：`registry.py:873-901` 的 checks enum 必须 ⊇ `_ALL_CHECKS`，由守卫测试 `tests/test_consolidation_p2.py:512-524` 强制。
4. **三处计数文案（当前均已漂移，新增时顺手闭掉）**：
   - `registry.py:821` prose 写 "Runs 25 available checks"，实际只枚举 23 项（缺 layout_violations / team_layout_gitignore / threshold_drift）；
   - `docs/capability-matrix.md:72-79` 写「25 项」按 severity 列全，缺 threshold_drift；
   - `tests/okf_regression_test.py:1085` 断言 `len(checks_run) == 16`（"16项检查全跑"），实测 checks_run=26，**该断言当前已失败**，属已知 6 失败之一（CI `continue-on-error`，`.github/workflows/ci.yml:47-48`）。
5. **消息语言**：现状 26 项检查里 23 项硬编码英文、仅 3 处走 `i18n.t`（:1215、:1368、:2719）。已定案政策见 `notes/2026-09-07-mcp-层中文返回文本-i18n-方案定案yaml-双文件全量一次性全做.md`：zh.yaml 为事实源、en.yaml 须全覆盖、**缺键无运行时回退**（输出 `[missing-i18n-key]`）、`tests/test_i18n.py` 守卫键集 → 新检查应加双语键而非硬编码英文。
6. **测试**：无统一 `test_wiki_lint.py`，按检查分散（`test_lint_fix.py`、`test_lint_layout_violations.py`、`test_consolidation_p2.py:488-510`、`test_skill_pages.py:363-460`、`test_freshness.py`、`test_low_adoption.py`、`test_threshold_drift.py`）。惯例：`tmp_path` 手搭最小 repowiki（frontmatter md + schema.yaml）→ 直调 `handle_lint_wiki` → 断言 issues 的 check/severity；`tests/conftest.py:20-33` autouse 钉 zh。

## 严重度语义（决定新检查该报什么级）

「背撑」检查的语义是 submit 已校验、lint 兜住绕过工具的手写手改（`wiki_lint.py:1663-1664`，`scenario_capacity` 同理 :1463-1465）；背撑与普通 warning 的差别**仅是 severity=error**（健康分 -10 vs -3，:2700-2706），没有独立通道。hint-only 的溯源提示应报 warning。

## 与既有知识的关系

`notes/2026-09-07-硬编码中文常量承载可派生数据必然漂移i18n-集中化时应顺带根除.md` 记的是同一类模式（可派生计数被硬编码成常量）在 prompts/catalog/tool_count 侧的实例；本条是 **lint 检查侧的具体同步点清单**，两者互补不重叠。

## Rationale

同步点分散在 4 个文件且无统一注册入口，计数文案已三处漂移；不列清单就会「加了检查但 enum 守卫红 / 文案继续骗人 / okf 断言更歪」。
