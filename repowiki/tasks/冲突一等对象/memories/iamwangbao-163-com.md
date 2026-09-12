### 2026-09-12 09:58

### 2026-09-12（ADR-0007 实施完成）

冲突一等对象已实现并通过独立两轴评审（Standards/Spec 并行子代理）+ 评审修复。变更清单：

1. 新文件 codewiki/mcp/tools/conflict_case.py（flag_conflict + adjudicate_conflict，案卷写 conflicts/，裁决复用 note_writer._apply_status_to_file 原语，重复声明幂等门禁）
2. codewiki/src/config.py：CONFLICTS_DIR 常量（repowiki 根级目录，与 skills/ 同族布局）
3. note_query.py：BM25 主路径 + by_file 时间线命中 claimant 标注 open_conflict（fail-open），context_package 加警示行
4. wiki_lint.py：新 check open_conflicts（超期 14 天 warning，schema.yaml lint.open_conflict_max_age_days 可调；案卷 claimant 悬空检查）+ _NON_AUDIT_DIR_NAMES（stale_refs/broken_links/no_outlinks/orphan_pages/unsupported_claims 全树扫描排除 conflicts/）+ okf_conformance 系统层豁免
5. registry.py：两工具注册（mode=thread）+ _PUSH_ON_WRITE + lint 描述 25 checks 与枚举同步（顺带修掉「22 vs 24」历史漂移）
6. tests/test_conflict_case.py 13 用例
7. docs/capability-matrix.md 冲突案卷行 beta 落地

测试：新 13 绿 + 全量 946 passed/2 skipped（评审修复前）；修复后全量复跑中。本仓真实数据 E2E 全链路验证过（flag→双 claimant 标注→lint 无 issue→reject→标注消失→现场清理还原）。

评审抓出并已修：①adjudicate 重写闭合栅栏后缺换行致正文被 frontmatter 吞（真 bug，测试曾侥幸通过，已加回归锁）；②裁决后正文头部仍写「open（未裁决）」误导人读（已同步替换）；③capability-matrix「24 项/待修」注记过时（已更新 25）；④orphan_pages/unsupported_claims 的 wiki/ 缺失回退分支会卷入 conflicts/（已排除）；⑤by_file 测试条件断言可能空转（已改硬断言）。

未修的评审发现（有意保留）：mode=check 不带标注（轻量预检刻意无负载）；adjudicate 非原子（弃权者先 deprecated、案卷写失败留中间态——ADR-0007 明确不做 CAS，git 兜底）；模块内 claimant 归一化重复（跨模块收敛留待下次重构）。提交待用户指示。
