---
type: architecture
title: doctrine 不会自动注入 Agent 上下文：唯一通道是 query_wiki(mode='overview')
tags:
- architecture
metadata:
  date: 2026-08-25
  source_ref: conversations/conv-user_command-commands-codewiki-蒸馏对话提取记忆和经验-把已采集的对话（repowiki.md
  source_conversations: ['conversations/conv-user_command-commands-codewiki-蒸馏对话提取记忆和经验-把已采集的对话（repowiki-9477de.md']
status: stable
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 16:30:59+00:00
stale_after: '2027-08-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-08-24T16:32:22Z'

---

## 背景

AGENTS.md 中加入「项目定向（必做）：query_wiki(mode='overview') 拉取 Team Doctrine 全文」后，实际会话中 Agent 并未触发查询——本会话开局被任务关联硬指令占用了第一个动作，query_wiki 被跳过。AGENTS.md 指令在上下文中与任务提示竞争时经常落败，是软约束。

## 机制事实

doctrine 的注入通道只有 query_wiki(mode='overview')：knowledge_loop.py 中 _query_mode_overview 读取 wiki/doctrine.md、剥离 frontmatter、截断 1300 字符，放入返回结果的 doctrine 字段。没有其他自动注入路径：SessionStart hook 原本只注入任务关联引导；AGENTS.md 不引用 doctrine；检索层（cache.py _DOCTRINE_AUTHORITY +0.20）只有加权，仍依赖主动 query_wiki。

## 决策

让 SessionStart hook（codewiki/hooks/task_session_start.py 源，及 .codebuddy/hooks/、.qoder/hooks/ 三份副本同步）新增 _load_doctrine：读 repowiki/wiki/doctrine.md，跳过 OKF frontmatter 只注入正文；文件缺失 / 超 20KB / 读取失败时优雅降级为空，绝不破坏任务绑定引导。_build_message 末尾追加「【项目定向】已注入 Team Doctrine……」段。新增 2 个测试用例（存在时注入+frontmatter 剥离、缺失时无此段）。

## 验证

pytest tests/test_task_session_start.py 6 passed；真实仓库模拟运行注入 2320 字节 doctrine 正文，frontmatter 干净剥离。
