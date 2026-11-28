---
type: procedure
title: "微信公众号文章取材：WebFetch 遇环境异常验证页改 curl 带 UA，判据看 og:title 与 js_content"
tags: ["applewebkit", "procedure", "webfetch"]
metadata:
  date: 2026-11-14
  confidence_level: weak
  task_id: 他山之石
  source_session: "42b9be13-a446-8a36-9c69-8cd63018803e"
  severity: medium
  source_ref: "conversations/conv-https-mp.weixin.qq.com-s-2IUREDltOXzXECO7tWIoPA-阅读文章看看有值得借鉴的.md"
  scene: "外部文章调研取材"
status: draft
author: wanderingbug
generated: { by: codewiki/5.16.7, at: 2026-11-14T01:36:20Z }
stale_after: 2027-05-13
origin: conversation
source_conversations: ['conversations/conv-command-message-open-code-review-delegate-command-message-co-22dfc9.md']

---

## 适用场景

读 mp.weixin.qq.com 文章做外部调研（「他山之石」任务的常见取材入口）。本次目标：腾讯技术工程《不只是Memory：Ontology如何让Coding Agent越用越懂项目？》。区别于已有的公众号**写作/排版**类笔记，本条只管**取材**。

## 步骤

1. **先试 WebFetch**：本次返回的是微信「当前环境异常」验证页，无标题/作者/正文——不要据此判定文章不存在或无技术内容。
2. **改用 curl 带浏览器 UA**：`curl -sL --max-time 30 -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36" <url>` 落盘 HTML（本次 3.8MB）。
3. **判真伪的正确判据**：HTML 里 grep 到「环境异常」字样**不代表被拦截**（JS 错误模板里也含该串）。真判据是 `og:title` 有值且 `id="js_content"` 存在（本次 js_content 19 处命中 + og:title 为文章标题 → 真文章页）。
4. **提取正文**：写一次性 Python 脚本（放 /tmp，不污染仓库），用标准库 `HTMLParser` 跟踪进入 `id=js_content` 后收集文本：h1-h6 加标题前缀、p 换行、li 项目符号、pre/code 转围栏、img 记 `data-src`；元数据取 `og:title`、`js_name`（作者）、`createTime`/`publish_time`。本次产出 15702 字符中文正文 + 账号/作者/发布时间。
5. **运行环境回退**：本机 `uv run python /tmp/xxx.py` 报 `failed to create directory /Users/kirito/.local/share/uv/python: Permission denied (os error 13)`；一次性脚本改用系统 `python3`（本机自带 yaml）或仓库 `.venv/bin/python` 即可，无需去修 uv 目录权限。

## Rationale

WebFetch 对微信文章会静默返回验证页，若按「页面无技术内容」结案就会漏掉整篇可借鉴材料；而 curl 后 grep「环境异常」又会反向误判为失败——两个坑都必须用 og:title/js_content 判据绕过。

## 微信文章标题/日期提取：WebFetch 被拦时用 curl 带 MicroMessenger UA 下载 HTML 再 grep msg_title/publish_time

> 合并自蒸馏候选：微信文章标题/日期提取：WebFetch 被拦时用 curl 带 MicroMessenger UA 下载 HTML 再 grep msg_title/publish_time

## 补充：元数据提取变体（2026-11-28 蒸馏）

主文讲正文取材（og:title/js_content 判据 + HTMLParser 提取）；本节补一个轻量变体——**只需要标题与发布日期时**（如为 README 专栏列表补条目）：

1. curl 带**微信内置浏览器 UA**（`MicroMessenger/8.0.47`，比通用浏览器 UA 更稳）：`curl -L -A "Mozilla/5.0 (iPhone; ...) MicroMessenger/8.0.47" -o %TEMP%/wechat-article.html <url>`；
2. HTML 里 grep `msg_title`（文章标题）与 `publish_time`（Unix 时间戳），时间戳用 `date -u -d @<ts>` 转日期；
3. 实测成功提取《CodeWiki-Plus 技术白皮书》标题与 2026-10-23 发布日期。

与主文判据互补：og:title/js_content 用于判真伪+取正文；msg_title/publish_time 用于纯元数据场景，无需解析正文。
