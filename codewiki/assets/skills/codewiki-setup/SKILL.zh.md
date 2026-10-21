---
name: codewiki-setup
description: "一键安装或升级 CodeWiki 并把当前项目接好线：pip 安装 codewiki-plus 后执行 codewiki setup（hook 与会话采集 + .mcp.json + 技能文件）"
disable-model-invocation: true
---

# codewiki-setup

一键安装或升级 CodeWiki，并把当前项目一次性接好线（hook 与对话采集、`.mcp.json`、技能文件）。

按顺序执行以下两步；任一步失败即停止并向用户报告错误，不要继续。

## 1. 安装/升级包

```
pip install --upgrade codewiki-plus
```

`pip` 不存在时改用 `python -m pip install --upgrade codewiki-plus`。

## 2. 项目接线

在当前项目根目录执行：

```
codewiki setup
```

`codewiki` 命令不在 PATH 时（如刚安装完 PATH 未刷新）改用 `python -m codewiki setup`。

setup 会一次完成三件事：为检测到的宿主 IDE 接线 hook 与会话采集、在项目根创建或合并 `.mcp.json`（codewiki MCP server）、生成 `codewiki-*` 技能文件。

完成后可执行 `/codewiki-init-wiki` 初始化项目 wiki。

本技能是手动触发入口（disable-model-invocation: true），不占常驻上下文；由用户显式调用 /codewiki-setup 触发。
