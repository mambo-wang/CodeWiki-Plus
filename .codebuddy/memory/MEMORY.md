# 长期记忆 (MEMORY.md)

## 环境偏好 / 约定

### npm 镜像源
- 当前环境（推测国内网络）使用 npm 官方源 `registry.npmjs.org` 下载**大体积原生二进制**（如 `@next/swc-darwin-x64`、better-sqlite3 预编译包）时速度极慢（<1KB/s，曾卡死 25+ 分钟）。
- 改用 `https://registry.npmmirror.com` 镜像源后速度约快 6 倍，全局安装 `npm install -g <pkg> --registry=https://registry.npmmirror.com` 是稳妥做法。
- 注意：npm 11 已不再识别 `--disturl` / `--prebuild-install-binary-host-mirror` 这类 CLI flag（会报 unknown config 警告），原生模块的二进制镜像需改用 `.npmrc` 配置。

## 已安装工具
- `omniroute`（AI 网关，v3.8.48，全局 npm 安装）：Dashboard `http://localhost:20128`，API `http://localhost:20128/v1`。编码工具 Base URL 指向 `/v1`、Model 用 `auto` 即可走免费后端。要求 Node ≥ 22.22.2（本机 v25.8.1 满足）。
- `curl.exe`（v7.55.1，Windows 自带）：**太老，不支持 `-K` 配置文件的 `form-string`/`form-file` 长选项**（curl 7.84+ 才支持）。传 multipart 表单需用 Python 构造 body + `curl.exe --data-binary @body.bin`。

## 发版本（PyPI 发布）关键约定

### 本机网络对 upload.pypi.org 的 TLS 握手干扰
- 本机网络对 `upload.pypi.org` 的 Python OpenSSL TLS 握手被干扰：`uv publish` / `twine` / `requests` 全部连接超时（TCP 通、curl.exe 秒通）。
- **绕法**：用 Python 构造完整的 `multipart/form-data` body（含 boundary、所有元数据字段、文件内容）写到 `.bin` 文件，再用 `curl.exe --data-binary @body.bin -H "Content-Type: multipart/form-data; boundary=..."` 发送（curl.exe 用 schannel 栈，不受干扰）。

### PyPI legacy API 字段名约定
- 字段名用**下划线**（`metadata_version`），不是连字符（`metadata-version`）。METADATA/PKG-INFO 头用连字符，但表单字段必须转成下划线。
- 必须字段：`:action=file_upload`（没有这个字段 PyPI 返回 405 Method Not Allowed）。
- digest 字段名：`sha256_digest`（不是 `digests_sha256`）。
- `email.parser` 的 `Message.keys()` 对重复头返回 N 次，循环内再 `get_all(key)` 会产生 N×N 重复字段——遍历前必须对 key 去重。
