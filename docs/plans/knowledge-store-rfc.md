# Plan: 统一知识存储层——把散落的存储管道代码收拢为动词式门面（RFC）

> **Status**: open | **Date**: 2026-08-31 | **Origin**: 架构评审（/improve-codebase-architecture，候选 1/5）

## Problem

`repowiki/`（git 管理的知识库：`notes/`、`wiki/`、`raw/`、`tasks/`、`.meta/`）**没有存储层**——15+ 个 MCP 工具 handler 各自拼路径、各自解析 frontmatter、各自实现原子写。已核实的重复清单：

| 概念 | 份数 | 位置示例 |
|---|---|---|
| frontmatter 解析 | ≥13 | `cache.py:2439`、`knowledge_loop.py:1246+2552`、`task_manager.py:266`、`wiki_search.py:226`、`wiki_index.py:347`、`wiki_lint.py:1002`、`distill_conversation.py:351`、`capture_conversation.py:431`、`note_consolidation.py:103`、`note_merge.py:30`、`workspace_layout.py:218`、`doc_writer.py:174`。注：`src/frontmatter.py` 是"官方"模块却**只有写侧**（`inject_okf_frontmatter`），无解析侧 |
| `_resolve_output_dir` | 5 | `capture_conversation.py:191`、`distill_conversation.py:200`、`note_consolidation.py:316`、`source_ingest.py:54`、`knowledge_loop.py:513`（内联） |
| `_slugify` | 4 | `capture_conversation.py:128`、`knowledge_loop.py:114`、`note_merge.py:53`、`review_changes.py:439` |
| 原子写 tmp+os.replace | ≥7 | `wiki_index.py:452`、`wiki_search.py:193`、`capture_conversation.py:384`、`distill_conversation.py:1274`、`task_manager.py:166/322/367`、`telemetry.py:117`、`doctrine.py:313`、`aggregation_state.py:78` |
| `raw/.index.json` schema | 双处维护 | `capture_conversation.py:384`（`_write_index`）vs `distill_conversation.py:1248`（`_sync_raw_index_on_distill`） |

接缝处的集成风险：

- `capture_conversation.py:154` 注释自认：因 capture↔task_manager **循环依赖**，tasks 目录名常量被有意复制一份
- `task_manager._append_memory_atomic` 自述无跨进程锁，而多个 stdio MCP server 进程可能并发写同一 `memories/<user_id>.md`
- Windows"持锁句柄禁止对被锁文件做 replace"冲突：`_atomic_replace_with_retry` 的退避重试正是该冲突的症状，各处自行重试
- 状态改写两套（`knowledge_loop._apply_status_to_file` 743-910 vs distill 的 `_mark_distilled`）；索引自愈逻辑（目录扫描为真相、失配重建）在 `task_manager`（92-172）与 capture 的 `_rebuild_index` 中各写一份
- 理解一次"笔记落盘"需跳 4-6 个文件；新增工具需重新发现全部隐性契约

## Proposed Interface

核心形状：**纯存储库 + MCP 桥**。存储库只接收已解析的 root 路径（纯文件系统、零 MCP 依赖）；桥是唯一接触 `SessionState` 的地方，负责 session/arguments → root 解析，布局路由委托 `workspace_layout`，不重演。

```python
# 存储库（纯 FS）
class KnowledgeStore:
    def __init__(self, root: Path): ...

    # ── 高频读 ──
    def page(self, relpath: str) -> Page | None
        # Page.fm / .body / .get(key, default)：顶层优先、metadata 回退，解析只发生一次
    def iter_pages(self, scope: str = "", keys: tuple = ()) -> Iterator[Page]

    # ── 高频写：一个动词一个场景 ──
    def ingest_note(self, note_type, title, content, *, status="draft",
                    task_id="", metadata=None) -> WriteRef
    def capture_raw(self, turns, *, source_session_id="", task_id="",
                    link_to="", keep_raw=False) -> CaptureResult
        # 去重(content_hash)/会话级 supersede/task_id 继承/绑定消费/索引维护全在内部；
        # result.kind ∈ captured | duplicate | superseded
    def append_memories(self, task_id, entries, *, user=None) -> int
        # file_lock 内读-追加-写；### YYYY-MM-DD HH:MM 头；per-user 文件；幽灵任务返回 0
    def set_status(self, relpath, status, *, verified_by="", reason="",
                   renew_stale_after=False) -> None
    def finish_raw(self, conversation_id, *, archive=True) -> str | None
    def pending_raws(self, task_id="") -> list[RawEntry]   # 索引优先、失配自愈
    def read_memories(self, task_id, *, max_entries=20, include_warm=True) -> MemoriesView

    # ── 逃生舱口（低频）──
    def atomic_write(self, relpath, text) -> Path
    def update_frontmatter(self, relpath, **fields) -> None
        # 只改指定字段，保留其余全部已有键

# 桥（唯一接触 SessionState）
def store_for(session, arguments) -> KnowledgeStore
```

使用示例（前 → 后）：

```python
# ingest_note：原 ~60 行手拼 frontmatter + 查重 + write_text
ref = store.ingest_note(note_type, title, content, task_id=tid,
                        metadata={"related_modules": mods})

# capture：原 ~120 行索引读写 + supersede + 绑定消费
res = store.capture_raw(turns, source_session_id=sid, task_id=tid)

# memory 追加：原 _append_memory_atomic 无跨进程锁
store.append_memories(task_id, memories)
```

内部藏掉的复杂度：13 份 frontmatter 解析合一（解析侧补齐 `src/frontmatter.py`）；5 份 output_dir 解析合一；4 份 slugify 合一；≥7 份原子写合一；`raw/.index.json` 单写者；索引自愈（目录扫描为真相）统一；文件命名策略（日期前缀、碰撞后缀、目录归属）全入实现；capture↔task_manager 循环依赖随常量收口消失。

## Dependency Strategy

依赖类别 **In-process**（纯文件系统），测试用 `tmp_path`。

- **locks**：复用 `src/locks.py` 的 `file_lock`；锁目标为旁挂文件 `<target>.lck`（规避 Windows 下"持锁句柄禁止对被锁目标做 replace"），块内所有 I/O 走让渡句柄；纯新建文件走原子替换不加锁
- **workspace_layout**：桥调用 `default_output_dir` / `routing_for_write` 得到 root 后传入；存储库不参与布局路由、不重复其逻辑
- **config**：目录名常量仅在存储库层 import 一次
- **frontmatter**：解析侧补进 `src/frontmatter.py` 作为唯一真源；写侧沿用 `inject_okf_frontmatter`——磁盘格式（markdown + YAML frontmatter）是契约，被 git 管理、人类手编、外部 Agent 读取，不做格式迁移，也不引入强类型投影（自由格式键保证写回不丢）

## Testing Strategy

**新增边界测试**（`KnowledgeStore(tmp_path/"repowiki")` 直测）：

- ingest / capture / memory 写盘 round-trip：断言磁盘产物（frontmatter 字段、文件命名、索引条目）
- capture 去重（content_hash）与同源会话 supersede 语义、绑定消费后 `task_id` 继承
- 索引自愈：手工损坏 `.index.json` → 扫描重建后一致
- 并发：多进程/多线程并发 `append_memories` 零丢失
- `set_status` 状态流转 + `renew_stale_after`；`update_frontmatter` 不丢未指定键

**旧测试处置**：`handle_*` 签名冻结，现有边界测试（如 `test_task_manager.py` 的 126 次 handler 调用）在迁移期原样保留作回归网；全 tests 目录对模块私有函数的引用仅约 10 处（`_split_memories`、`_parse_priority` 等），迁移时旧私有函数改薄壳委托存储库，调用点归零即删除。

**环境需求**：仅 `tmp_path`；布局相关用例用临时 `workspace.json` + `workspace_layout.clear_cache()` 隔离。

## Implementation Recommendations

- **模块应拥有**：frontmatter 读写（唯一解析/序列化）、路径与输出目录解析、文件命名（slugify + 碰撞策略）、原子写与锁、索引缓存自愈（单写者）、目录名常量、状态字段的原子改写（`set_status`）
- **模块应隐藏**：文件命名策略、索引 schema 与重建、锁细节与 Windows 重试、绑定文件消费、`###` 标题切条的解析细节
- **模块应暴露**：动词 + `Page` 轻对象；契约是"迁移后 handler 不得再直接 `open()` `repowiki/` 下的文件"
- **不属于存储层**：冲突裁决、新鲜度/晋升评分、记忆分层渲染、蒸馏提示词——留在 handler，防止动词退化为业务管道
- **迁移路径**：按工具逐个迁移（建议顺序：capture/distill → task_manager → knowledge_loop → 其余）；过渡期旧私有函数改薄壳委托，避免双写路径漂移；旧路径调用点归零后物理删除
- **拒绝的设计**：强类型 dataclass 投影（markdown 自由格式与强类型的张力真实存在，未知键只能落 extra bag，类型安全感是假的）；可插拔 Backend/DocType 注册体系（服务于尚不存在的需求，现在就付抽象税）
