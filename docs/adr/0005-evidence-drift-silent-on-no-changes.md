# 0005. 证据漂移信号仅在代码变更路径参与增量决策，no_changes 路径保持静默

日期：2026-09-06
状态：已接受

## 背景

B6（stale_evidence 回灌增量决策）把 D1 证据哈希检查的输出接入 `analyze_repo` 的
增量信号，成为与 `affected_modules`（git diff 驱动）、`stale_pages`（D2 manifest
驱动）并列的第三信号源。设计拷问中暴露一个路径决策问题：`analyze_repo` 的
`no_changes` 短路路径（代码无变更、直接复用缓存返回）是否也跑证据漂移扫描？

注意该路径并非"完全无事可做"——D2 的 `stale_pages` enrich 就挂在 no_changes 路径
上（`analysis.py` `_build_no_change_response`），因为 manifest 指纹漂移可能在代码
零变更时发生（sources 被外部编辑）。证据漂移理论上同理：代码哈希没变不会漂，但
sources 里的 `content_hash` 被手改、或上轮分析后发生过又被回滚的变更，都可能让
`verify_entry` 失败。

## 决策

**`no_changes` 路径不跑证据漂移检查，hint 保持 "Documentation is up to date"。**
漂移信号只挂 `handle_analyze_repo` 的变更路径（`_enrich_stale_evidence` 在
`_enrich_stale_pages` 之后调用）。实现上 `_enrich_stale_evidence` 内部带
`no_changes` 守卫，且在 `_build_no_change_response` 中显式不调用。

## 理由

1. **语义对称性换执行对称性是可接受的取舍**：no_changes 意味着"代码没动"，证据
   漂移在该状态下是小概率事件（sources 手改属异常操作）；为之付出每次短路都全库
   扫描的代价不成比例。
2. **出口仍然存在**：`lint_wiki(checks=["stale_evidence"])` 随时可显式触发全量
   证据校验；B6 hint 文案里明确引导这个出口。
3. **"up to date" 文案的可信度**：接受该文案在极端场景下的不精确（有漂移但代码
   没变），换取短路路径的简洁。若未来实测发现该场景高频，可重新评估。

## 后果

- 两路漂移信号（D2/D1）在 no_changes 路径行为不对称：stale_pages 参与、
  stale_evidence 静默。这是显式决策而非遗漏，代码注释已标注本 ADR。
- `_enrich_stale_evidence` 的 no_changes 守卫是防御性的（当前唯一调用点在变更
  路径），留着以防未来误挂。

## 关联

- 设计拷问记录：2026-09-06 会话（grill-with-docs），Q3 用户拍板选 (b) 静默
- D1 设计：`docs/OpenWiki-借鉴详细设计方案.md` §1
- 实现：`codewiki/mcp/tools/analysis.py::_enrich_stale_evidence`、
  `codewiki/mcp/tools/evidence.py::collect_evidence_drift`
- 测试：`tests/test_stale_evidence_signal.py::test_enrich_silent_on_no_changes_path`
