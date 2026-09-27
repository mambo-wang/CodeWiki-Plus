---
type: pitfall
title: curl 直传 PyPI 时 email.parser 的 keys() 对重复头返回 N 次导致 project_urls 重复 16 条被 400
  拒绝
tags:
- bytesparser
- pitfall
metadata:
  date: 2026-09-23
  confidence_level: weak
  severity: medium
  root_cause: email.message.Message.keys() 对重复头每个实例返回一次，get_all(key) 又取全部实例，二者嵌套导致
    N×N 重复
  reason: v5.13.1 发布实操验证：修复后 200 OK 上传成功
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.0
  at: 2026-09-23 08:45:03+00:00
stale_after: '2027-03-25'
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:25Z'
---

# curl 直传 PyPI 时 email.parser 的 keys() 对重复头返回 N 次导致 project_urls 重复 16 条被 400 拒绝

## 现象

v5.13.1 发布时用 curl.exe 直传 PyPI legacy API（绕过本机 Python OpenSSL TLS 握手干扰），wheel 上传报 400：`'project_urls' has invalid data`。\n
## 根因

从 whl 的 `*.dist-info/METADATA` 提取元数据时用了 `email.parser.BytesParser`。`Message.keys()` 对重复头（如 4 个 `Project-URL`）会把每个实例都返回一次（4 次），循环内又对每个 key 调 `get_all(key)` 取全部实例（4 条），嵌套后产生 4×4=16 条重复的 `project_urls` 字段，PyPI 服务端校验拒绝。

## 修复

遍历前对 key 去重：

```python
seen = set()
for key in msg.keys():
    lk = key.lower()
    if lk in seen or lk not in FIELD_MAP:
        continue
    seen.add(lk)
    for val in msg.get_all(key):
        fields.append((FIELD_MAP[lk], val))
```

修复后 wheel 与 sdist 均 200 OK。

## 关联

- twine 的做法可对照：`twine/repository.py:72-75` 把 `project_urls` 解析成 dict 后逐条展开为 `name, url` 元组，天然无重复。
- 上位流程见技能 windows-python-release 步骤 7（curl.exe 直传绕法）。
