---
name: write-doc-file-content-file-sidechannel
description: write_doc_file 建档报目标路径已被手写文件占用/路由冲突时——走 content_file 临时文件侧通道：正文写临时文件→删占位文件→write_doc_file(content_file=...) 正式建档→删临时文件
type: Skill
status: draft
generated:
  by: codewiki/5.13.1
  at: "2026-09-27T05:07:21Z"
stale_after: 2026-12-26
metadata:
  summary: write_doc_file 建档遇手写文件占位冲突时的 content_file 侧通道四步流程
  source_refs: ["notes/2026-09-27-write-doc-file-建档遇目标路径已被手写文件占用时走-content-file-临时文件侧通道.md"]
  revisions:
    - at: "2026-09-27T05:07:21Z"
      reason: created from candidate materials
      source: skill_creator
---

## 工作场景
需要用 CodeWiki 的 write_doc_file 正式建档 wiki 页面（注入 frontmatter、注册交叉链接与索引），但目标路径上已存在手写文件（如先前用 write_to_file 起草的占位稿），直接调用会触发文件路由冲突被拒绝写入。

## 适用条件
- 使用 write_doc_file 建档（page_type=module/entity/concept/query/comparison/source 等），且需要工具负责的元数据注入（frontmatter、交叉链接、索引注册）。
- 目标路径已被手写文件占用，工具报「目标路径已存在 / 路由冲突」类错误。
- 不适用于普通笔记归档（走 ingest_note，无路径冲突问题）；也不适用于编辑已有正式页面（直接 edit_doc_file）。

## 核心 SOP
依据: notes/2026-09-27-write-doc-file-建档遇目标路径已被手写文件占用时走-content-file-临时文件侧通道.md 的「content_file 侧通道建档流程」（2026-09-25 agentmemory 调研建档实际跑通）。

1. 把页面正文写入一个临时文件（如 `.codebuddy/tmp-<页面名>.md`），只写正文、不写 frontmatter——元数据由工具注入；
2. 删除目标路径上已手写的占位文件（内容已在第 1 步保全，删除无损失）；
3. 调用 `write_doc_file(content_file=<临时文件路径>, ...)` 让工具从临时文件读正文并正式建档；
4. 建档成功后删除临时文件，收尾复核新页面 frontmatter 齐全。

## 判断逻辑
- write_doc_file 报目标路径冲突 → 先确认冲突文件是手写占位（无工具注入的 frontmatter），是则走侧通道；若已是工具建的正式页面，改用 edit_doc_file 编辑，不要删了重建（会丢 revisions/edit 历史）。
- 正文很大（接近 MCP 参数限制）→ 更应走 content_file 文件侧通道，顺带规避大载荷内联传输问题。
- 手写文件内容与拟建页面无关（纯误占位）→ 可直接删，无需第 1 步保全。

## 禁忌与反模式
- 勿因冲突就放弃 write_doc_file、让手写文件充当正式页面：缺 frontmatter/索引注册，页面不进检索与 wikilink 图。
- 勿绕过 dispatch 直连 handler 写文件——路由冲突是确定性簿记在保护建档一致性。
- 勿把临时文件留在仓库工作树里忘记清理（第 4 步必做）。
- 勿在临时文件里手写 frontmatter：与工具注入的元数据冲突或产生重复段。
