---
type: pitfall
title: 蒸馏 worker 启动前先自检 MCP 可见性，拿不到 distill_conversation 就停，不要退让直连 handler
tags:
- pitfall
aliases:
- distill-worker MCP
- MCP 未挂载
- 直连 handler
- subagent MCP 授权
- distill 残留文件
metadata:
  date: 2026-09-08
  related_modules:
  - mcp
  severity: medium
  root_cause: subagent frontmatter 的 toolsMCP 声明只是意图，不等于运行时授权生效；MCP server 未连接时声明静默失效而非报错，worker
    误判为「工具不可用就自己想办法」而非「环境故障需上报」。
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.8.0
  at: 2026-09-08 05:30:18+00:00
stale_after: '2027-03-09'
verified:
- by: human:wangbao
  at: '2026-09-10T07:47:26Z'
---

## 背景

2026-09-08 补蒸馏时，`distill-worker` subagent 的 frontmatter 声明了 `toolsMCP: codewiki`，但运行时工具集里并没有挂上 codewiki MCP，`distill_conversation` 不可调用。worker 为了「不空转」，改为直接 `import codewiki.mcp.tools.distill_conversation.handle_distill_conversation` 走 python 执行，参数与 Mode C 完全一致。

同一轮还发现上一轮 worker 留下的 `repowiki/raw/.distill-产品维护-3.json` 没被消费，一直堆在 raw 暂存区——直连执行中断时的典型残留。

## 正确做法

1. **先自检再干活**：worker 启动第一步调用一次 `distill_conversation(mode="prepare")` 探活。拿不到工具或返回错误 → **立即停下**，向主 Agent 报告「MCP 环境未就绪」，由主 Agent 决定是修配置还是改走别的通道。
2. **不要退让直连 handler**：直连会绕过 dispatch 与 schema 校验（Doctrine：不绕过 dispatch/schema 校验直连 handler），且缺少工具层的清理/回滚语义，异常中断会在 raw 暂存区留下垃圾。
3. **主 Agent 侧同理**：若主 Agent 自己也看不到 codewiki MCP 工具，先引导用户修 MCP 配置（`.mcp.json` / MCP server 开关），再跑知识飞轮操作；`confirm_note` 之类的闸门操作尤其不该走直连，因为 `verified_by` 记账格式会走样（本次直连确认的条目记为 `wangbao`，MCP 通道记为 `human:wangbao`）。
4. **收尾清理**：任何蒸馏批次结束后检查 `repowiki/raw/` 是否还有 `.distill-*.json`，有就删（Doctrine：噪声暂存宁删不留，显式 keep 才保留）。

## 根因

subagent 的 `toolsMCP` 声名为**意图声明**，不等于运行时授权生效；IDE 侧 MCP server 未连接/被禁用时，声明会静默失效而非报错。把「工具不可用」当成「换个办法也要干完」而不是「环境故障，停下来报告」，是这次的判断失误。

## 与既有笔记的边界（勿重复引用）

- `notes/2026-08-29-subagent-定义的-frontmatter-按宿主家族分发同名文件不同-schema.md`：覆盖**宿主权限模型**——claude 家族自定义子代理运行时根本不连接 MCP，解法是 spawn 内置 general-purpose 子代理。本条针对的是**另一种情况**：宿主本身支持 MCP（CodeBuddy），只是运行时 MCP 连接未就绪/被禁用，声明静默失效。前者是"换宿主策略"，后者是"先探活、未就绪就上报"。
- `notes/2026-08-25-mcp-参数长度受限时蒸馏-submit-走文件侧通道python-脚本直接调-handle-distill-conve.md`：已确立"勿用 python 脚本直连 handler 绕过"，但动因是**载荷超限**且已给出正式替代通道 `distilled_file`。本条补的是**工具完全不可见**时的处置，以及直连在闸门操作（`confirm_note`）上导致的 `verified_by` 记账走样——这是那条没覆盖的后果面。

## 适用范围

所有依赖 codewiki MCP 的 subagent（distill-worker 等）与主 Agent 的知识飞轮操作（capture / distill / ingest / confirm / query）。
