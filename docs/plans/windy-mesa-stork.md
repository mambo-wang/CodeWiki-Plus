# Plan: close_session 时自动注入 AGENTS.md Wiki 使用说明

## Context

用户希望 CodeWiki 在为目标项目生成 wiki 后，自动往该项目的 `AGENTS.md` 注入一段说明，让任何使用该项目 IDE Agent 都能知道 wiki 的存在并学会查询它。目前 CodeWiki 不会向目标仓库写入用户可见的文件，Agent 无法自动感知 wiki。

## 修改范围

### 1. 新建 `codewiki/mcp/tools/agents_md.py`

新增 `write_agents_md(session: SessionState) -> None` 函数，逻辑如下：

1. 计算 `rel_path = os.path.relpath(session.output_dir, session.repo_path)`，得到 wiki 相对于项目根的路径
2. 从 `session.module_tree` 提取模块名列表（顶层 key）
3. 拼接 Markdown 段落，用 HTML 注释做区段标记：
   ```
   <!-- CodeWiki LLM Wiki -->
   ## CodeWiki LLM Wiki
   本项目已生成 LLM Wiki 文档...
   <!-- /CodeWiki LLM Wiki -->
   ```
4. 段落内容包含：
   - Wiki 位置：`<rel_path>/`
   - 入口文件：`overview.md`（总览）、`index.md`（目录）
   - 模块列表（从 module_tree 提取，附链接）
   - `query_wiki` 工具用法示例（JSON 参数）
   - `ingest_note` 工具用法示例
   - `lint_wiki` 用途说明
5. 写入策略：
   - `<repo_path>/AGENTS.md` 不存在 → 创建文件并写入
   - 已存在且包含 `<!-- CodeWiki LLM Wiki -->` 标记 → 替换该标记之间的内容
   - 已存在但无标记 → 追加到文件末尾

### 2. 修改 `codewiki/mcp/server.py`

在 `close_session` 处理分支（约 698-711 行）中，`build_full_index` 之后、`session.workspace.cleanup()` 之前，添加调用：

```python
# Inject wiki usage instructions into target project's AGENTS.md
if session.docs_written > 0:
    try:
        from codewiki.mcp.tools.agents_md import write_agents_md

        write_agents_md(session)
    except Exception:
        logger.debug("Failed to update AGENTS.md", exc_info=True)
```

与 `_write_generation_metadata`、`rebuild_index` 同级，遵循相同的 try/except 容错模式。

## 关键设计决策

- **区段标记**：用 `<!-- CodeWiki LLM Wiki -->` / `<!-- /CodeWiki LLM Wiki -->` 做幂等更新，不覆盖用户自己写的内容
- **仅在有文档产出时注入**：复用 `session.docs_written > 0` 守卫，避免空 session 产生无意义的 AGENTS.md
- **相对路径**：用 `os.path.relpath` 而非绝对路径，让 AGENTS.md 可移植
- **容错**：整个操作包裹在 try/except 中，失败不影响 session 清理

## 验证方式

1. 对一个测试仓库调用 `analyze_repo` → `write_doc_file` → `close_session`
2. 检查 `<repo>/AGENTS.md` 是否被创建/更新，内容包含 wiki 路径和工具用法
3. 再次执行 `close_session`（模拟增量更新），确认 AGENTS.md 中的区段被更新而非重复追加
4. 手动在 AGENTS.md 中添加自定义内容，确认重新生成后自定义内容被保留
