# ADR-0018: 二进制源文件保留 + markitdown 转换 sidecar

- **状态**：已接受（2026-09-27，grill-with-docs 两轮拷问后拍板）

## 背景

`ingest_source` 官方口径支持 PDF/MD/DOCX/HTML 四种格式，但二进制格式（pdf/docx）无文本提取器：`_plain_text()` 返回 None，导致版本去重门（version_sibling / supersede_declared）对二进制完全失明，且外部文档知识抽取流程读不回正文。引入 markitdown（微软开源，纯 Python，按格式分 extras）补这个洞。

## 决策

### 1. 源文件无条件保留（Q1=A）

原始文件照旧存 `raw/sources/<name>.<ext>`，转换产物存 sidecar `<name>.converted.md`。理由：① 转换有损（PDF 表格、扫描版乱码），原始文件是唯一可信输入，将来换更好的转换器可重转；② registry 的 `content_hash`（sha256）锚定原始字节，丢了原文件哈希成悬空锚点；③ 与「降状态、不物理删」的既有纪律一致。体积痛点出现时再走上限策略，不预支复杂度（YAGNI）。

### 2. ingest 时一次性转换存 sidecar（Q2=A）

不做按需转换。落盘后 `_plain_text()` 扩展为「二进制后缀 → 读 sidecar」，版本去重门自动覆盖二进制格式，指纹逻辑零改动。每次 ingest 重新转换（转换成本秒级，缓存判断属投机复杂度）；sidecar 随导入覆盖，同一源的重复导入总是拿到最新转换。

### 3. markitdown 为 optional extra（Q3=A）

`[project.optional-dependencies] convert = ["markitdown[all]>=0.1.0"]`。未安装时 fail-open 降级：行为与现状完全一致（跳过转换、跳过去重门），日志提示安装 `pip install codewiki-plus[convert]`。不做核心 extras 拆分（维护成本高于收益）。

### 4. 转换失败 fail-open + 结构化记录（Q4=A）

registry 条目记 `derived_text`（sidecar 相对路径或 null）+ `convert_error`（结构化：`dependency_missing` / `empty_output` / `converter_exception`）。导入照常成功（存储+注册），抽取流程读到 null 时明确告知「该源无可读文本，跳过抽取」。不静默、不硬拒。

### 5. 引用锚定 sidecar 行号（Q5=A）

`[^src:...]` 行范围引用锚定 `<name>.converted.md` 的行号——只有 sidecar 是行号可重读可验真的。页面 frontmatter 注明「引用基于 markitdown 转换文本，行号不对应原始 PDF 页码」。不伪造页码。

### 6. sidecar 随 auto_push 入库（Q6=A）

原始文件 + sidecar 都进 git。clone 后可检索可验真可重转。体积痛点后置处理。

### 7. 跨格式相似检测生效（Q7=A）

指纹基于正文语义（`doc_similarity.compute_fingerprint`），格式只是载体。`设计文档.docx` 与已注册的 `设计文档.md` 高度相似时触发 version_sibling 门——门是「拦下问用户」不是「自动拒」，误拦成本一次确认，漏拦成本是语料重复污染。

### 8. 官方口径：PDF/MD/DOCX/HTML/XLSX（Q8=A，2026-09-27 修订）

工具描述写「PDF, MD, DOCX, HTML, XLSX」，加一句「安装 `[convert]` extra 后二进制格式自动转换为 Markdown sidecar」。`_CONVERTIBLE_SUFFIXES` 与官方口径严格同步（`.pdf/.docx/.xlsx`）——只有验证过转换质量的格式才进承诺；pptx/epub 等 markitdown 支持但未验证的格式不承诺、不启用，验证后再扩。

## 后果

- **正面**：二进制源接入版本去重门；抽取流程对 pdf/docx 可完整走通；转换确定性缓存。
- **负面**：`raw/sources/` 体积翻倍（原始+sidecar）；大 PDF 进 git 历史需留意。
- **风险**：扫描版 PDF 转出空产物——由 `convert_error: empty_output` 结构化暴露，抽取流程明确跳过。
