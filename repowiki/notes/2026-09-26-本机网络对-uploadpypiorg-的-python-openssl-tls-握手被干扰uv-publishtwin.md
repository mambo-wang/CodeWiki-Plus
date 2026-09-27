---
type: pitfall
title: 本机网络对 upload.pypi.org 的 Python OpenSSL TLS 握手被干扰：uv publish/twine 超时，curl.exe（schannel
  栈）直传 legacy API 绕法
tags:
- pitfall
metadata:
  date: 2026-09-26
  confidence_level: weak
  task_id: 发版本
  source_session: 4a12044311f84fd3a7ddcecc96abdd33
  related_modules:
  - publish
  - release
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-7.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:40:19+00:00
stale_after: '2027-03-25'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:03Z'
---

## 现象

本机网络环境下，Python OpenSSL 与 upload.pypi.org 的 TLS 握手被干扰：`uv publish`、`twine upload` 全部超时失败，重试亦无效。

## 根因

不是 PyPI 或凭据问题，而是网络层对 Python OpenSSL TLS 握手（TCP + TLS 指纹）的干扰。同机 `curl.exe` 使用 schannel 加密栈，与 upload.pypi.org 握手正常，几乎瞬时连通。

## 绕法

1. 用 Python 提取包元数据（wheel 的 `*.dist-info/METADATA` 与 sdist 的 PKG-INFO），按 PyPI legacy API 字段映射为 `name/version/description/.../content` 与多文件 `file` 字段。
2. 用 `curl.exe -K <配置文件>` 直传 `https://upload.pypi.org/legacy/`，绕开 Python OpenSSL 栈。
3. digest 字段名是 `sha256_digest`（不是 `digests.sha256`），metadata_version 等字段也要按 legacy API 拼对。
4. 上传后直查 `https://pypi.org/pypi/<pkg>/<version>/json`（或版本端点）核对新版本已就位。
5. API token 的临时文件用完即清理，并定期轮换。

## 结论

Python 生态上传工具（uv/twine）在 TLS 被干扰的网络里不可用，curl.exe（schannel 栈）直传 legacy API 是可靠绕法；注意 legacy API 的字段名差异与上传后核对。
