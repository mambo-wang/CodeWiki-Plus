---
type: decision
title: codewiki-plus 无感知自动升级：混合 rename-aside + wait-for-exit 策略定案
tags:
- decision
metadata:
  date: 2026-09-24
  confidence_level: weak
  reason: 用户在 grill-me 会话中逐轮确认 Q1–Q14 全部按推荐锁定，并明确确认实现
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.0
  at: 2026-09-24 13:06:23+00:00
stale_after: '2027-09-24'
verified:
- by: human:wangbao
  at: '2026-09-24T13:19:44Z'
---

# codewiki-plus 无感知自动升级设计定案（2026-09-24，grill-me 拷问式设计 Q1–Q14）

## 决策

| # | 决策点 | 定案 |
|---|---|---|
| Q1 | 默认开启？ | 默认开启 + `CODEWIKI_NO_AUTOUPDATE` 退出开关 + config.json `autoupdate:false` + version 输出留痕 |
| Q2 | 安装形态 | 仅纯 pip/uv venv 自动升；pipx/uv tool/conda/源码安装跳过并提示手动命令 |
| Q3 | 版本闸门 | patch+minor 自动升，major 只提示（semver） |
| Q4 | 失败容忍 | 信任 pip 原子性 + 启动时健康自检（元数据版本≠import 版本→重装自愈），不做备份回滚 |
| Q6 | 升级策略 | 混合：纯 Python 改动 rename-aside 零等待；tree-sitter 系原生依赖版本变动（比较 PyPI requires_dist）退回 wait-for-exit |
| Q7 | 状态文件 | `~/.codewiki/autoupdate.json`（last_check/last_version/last_result/pending_target） |
| Q8 | 并发互斥 | `~/.codewiki/.autoupdate.lock`，O_CREAT\|O_EXCL 原子创建，10 分钟超时抢占 |
| Q9 | 显式命令 | `codewiki upgrade`（前台）+ `--check`（只查不装）；不做 --rollback |
| Q10 | 自检时机 | 仅 last_result=upgraded 后的首次启动 |
| Q11 | 挂载点 | 只挂 CLI main() + MCP server main()；hook 不挂（fail-open 纯采集定位，收益与 server 重叠） |
| Q12 | 检查方式 | 全异步：主进程只读本地状态文件（微秒级），PyPI 查询+升级全在 detached 子进程，零阻塞 stdio 握手 |
| Q13 | 测试 | 单元（mock PyPI/pip）+ 集成（file:/// 本地 index 装真 wheel、子进程持锁模拟运行中 server），CI 三平台 |
| Q14 | 发布 | 直接随下个 minor 版本全量开启，不灰度 |

## 为什么「等父进程退出」不是缺陷

运行中进程本就无法热加载新代码；立即升级反而造成懒加载版本混跑（已 import 旧模块 + 未 import 新模块）。wait-for-exit 是正确性要求，不只是 Windows 文件锁妥协。配合 rename-aside（大多数版本零等待）+ CLI/hook 短命进程触发点，实际升级延迟被压缩到一个会话周期以内。

## 实现

- `codewiki/utils/self_update.py`：核心模块
- `codewiki/cli/commands/upgrade.py`：`codewiki upgrade [--check]`
- 挂载：`codewiki/cli/main.py:main()`、`codewiki/mcp/server.py:main()`
- `tests/test_self_update.py`：26 单元测试

锁语义实测依据见同日笔记「Windows 加载中的 .pyd 可重命名不可写不可删」。
