---
title: IDE-Hook采集链路方法
type: Scenario
description: Hook 采集链路 SOP、仅接线支持边界、distill-worker 随包发布与自动部署、多 IDE 家族归并
generated:
  by: codewiki/5.3.0
  at: 2026-08-18 01:50:06+00:00
stale_after: 2026-11-16
aliases:
- IDE-Hook采集链路方法
status: stable
metadata:
  summary: hook 仅接线支持 CodeBuddy（底层已兼容 Claude Code）；distill-worker.md 随包发布自动拷贝；多 IDE
    家族归并接线
  heat: 3
  source_notes:
  - notes/2026-08-23-hook-采集机制仅正式接线-codebuddyreadme-措辞用仅接线支持.md
  - notes/2026-08-23-distill-worker-subagent-定义随包发布hook-启用时自动拷贝到项目-codebuddyagent.md
---
## 工作场景
CodeBuddy 等 IDE hook 采集链路（capture_session_end.py → _ide_hook.py → capture_conversation）的方法体系。适用于开发或排查 IDE 对话采集、transcript 解析、hook 注入引导类工作、subagent 部署。

## 适用条件
开发/修改 hook 脚本、排查「会话结束未归档对话」、设计 IDE 侧采集与 agent 引导注入、部署蒸馏 subagent。

## 核心 SOP
1. 读 IDE transcript 先识别存储格式：index.json 的 messages 只有 id/role 元数据且存在 messages/ 兄弟目录时，逐个读 messages/<id>.json——IDE 历史是「索引+分片」结构。
2. hook 执行模型保持「同步采集 + 异步蒸馏」：hook 只做落 raw 轻活（subprocess.run timeout=60）；LLM 重活蒸馏永远显式后台触发。
3. 改 hook 脚本先改源副本（codewiki/hooks/）再同步项目副本（.codebuddy/hooks/）。
4. hook 注入引导要可靠：additionalContext 里写硬性执行顺序 + 直接注入任务标题/task_id——软措辞不可靠。
5. 多 IDE 支持按家族归并：hooks.yaml 三家族 + 事件名映射表 + 安装探测；接线由 IDE 注册表驱动（IDE_SPECS 字典 + codewiki install-hooks 自动检测）。
6. 配置合并用 copy.deepcopy 而非 dict(existing)；hooks.get(event, []) 取值后必须写回。
7. **hook 采集机制仅正式接线 CodeBuddy**：README 措辞用「仅接线支持」而非「仅支持」——底层采集脚本已对 Claude Code 留了兼容设计（载荷解析事件无关、仓库路径优先级含 CLAUDE_PROJECT_DIR），缺的只是注册文件。扩展其他 IDE 只需生成对应 settings.json 注册同一批 wrapper 脚本。
8. **distill-worker.md 权威版本存 codewiki/agents/distill-worker.md**（随包发布），hook 启用时自动拷贝到目标项目 .codebuddy/agents/（_prompt_init_wiki 与 _prompt_team_memory_hook 两处）；pyproject.toml package-data 须声明 "agents/*.md"。

## 判断逻辑
- transcript 噪声过滤只保留 user/assistant 角色。
- envelope 角色选 user：system 角色会被静默丢弃。
- 幂等去重按 command 字符串精确匹配在 Windows 下失效——去重前先规范化路径分隔符。
- 「仅接线支持」准确描述了现状：底层通用化，缺口只在注册文件。

## 禁忌与反模式
- 块剥离正则不要用 ^[ \t]* 行首锚点。
- SessionEnd envelope 不要用 system 角色。
- 不要把 distill-worker.md 手工复制到各项目（会版本漂移）——走随包发布自动拷贝。

## 关键事实依据
- transcript_path 指向 index.json（仅元数据），真实内容在 messages/<id>.json。
- 家族归并洞察：31 个智能体可收敛为 3 家族 schema。
- distill-worker 安装方式与 hooks/*.py 完全对称。
