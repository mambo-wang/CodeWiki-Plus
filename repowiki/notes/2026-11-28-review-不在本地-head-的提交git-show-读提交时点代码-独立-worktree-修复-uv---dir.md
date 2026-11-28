---
type: procedure
title: "Review 不在本地 HEAD 的提交：git show 读提交时点代码 + 独立 worktree 修复 + uv --directory 跑测试"
tags: ["baseexception", "procedure", "timeouterror"]
metadata:
  date: 2026-11-28
  confidence_level: weak
  scene: "OCR 委托 review/跨提交验证"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-28T00:08:55Z }
stale_after: 2027-05-27
---

## Background
OCR 委托模式 review 提交 a5467805 时，该提交在 origin/develop 上但本地 HEAD（落后 2 个提交）不包含它，工作树还有大量既有未提交改动。直接读工作树文件会拿到旧代码导致误判（实测：grep 到的 class [TimeoutError](../../codewiki/src/be/dependency_analyzer/analysis/call_graph_analyzer.py)(Exception) 与提交里的 BaseException 不一致，暴露了工作树是旧版本）。

## 正确做法（完整流程）
1. 先验证提交是否在本地 HEAD：git merge-base --is-ancestor <commit> HEAD && echo IN_HEAD || echo NOT_IN_HEAD；不在则所有上下文读取一律用 git show <commit>:<path>，禁止直接 Read 工作树。
2. 修复落位：本地落后且工作树脏时，不快进、不切分支，从 origin/develop 新建独立 worktree：git worktree add -b fix/review-<hash> <独立路径> origin/develop，在 worktree 里改，主工作区零接触。
3. 在 worktree 跑测试：用主仓 venv + PYTHONPATH 指向 worktree：PYTHONPATH="<worktree>" uv run --directory <worktree> --project <主仓> python -m pytest tests/...。⚠️ 只加 --project 不加 --directory 会把 cwd 切到主仓，报「file or directory not found」。
4. 实证验证优于读代码推断：对可疑解析逻辑（如 tree-sitter C 宏声明误解析）写探针脚本实测解析树，不靠猜；对第三方库属性名（mermaid-py 的 svg_response/MermaidError.status_code）核对安装包源码。
5. 清理：git worktree remove --force <path>，Windows 下若 Permission denied（文件锁）先 cd 出该目录再删。

## Rationale
「review 的提交不在本地 HEAD」是委托模式常见场景（远端先行合入）；工作树旧代码与提交内容不一致会系统性误导 review 结论，本流程的每一步都是防这个坑的实证。
