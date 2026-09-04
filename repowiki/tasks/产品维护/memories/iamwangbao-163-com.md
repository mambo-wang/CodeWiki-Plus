### 2026-08-28 12:16

用户询问 .meta/telemetry/Administrator.jsonl.tmp.19748 孤儿临时文件来源与清理时机：根因是 telemetry.py 的 _atomic_write_lines 崩溃安全写入（临时文件+os.replace）在进程被强杀/崩溃/断电或抛非 OSError 异常时残留；无自动清理机制，不影响 aggregate_usage（glob *.jsonl 不匹配），手动删除即可。

### 2026-08-28 12:16

用户在该会话中报告 codewiki get_task_context 调用很慢，需定位性能瓶颈原因（raw 捕获不完整，仅 user 消息无 assistant 回复，问题转主 Agent 跟进）。

### 2026-09-04 16:17

2026-09-04：D19 锁文件集中化变更完成 review（7 文件 +109/−13，`store.py` 新增 `_lock_path_for()` 将 `.lck` 从目标旁边车迁到 `<wiki-root>/.meta/locks/<sha256(abs)[:20]>.lck`，无 `.meta` 祖先时回退就地 sidecar）。结论：代码质量良好，可直接提交，无必须修改项。

### 2026-09-04 16:17

2026-09-04：D19 相关测试全绿——`tests/test_phase2_concurrency.py` 16 passed（含新增 3 个），加 test_locks/knowledge_store/layout_routing/phase3_4/phase4_second_slice 共 63 passed，合计 79 passed（Windows / Python 3.14.5）；新增跨进程测试真实起 2 个 subprocess 各 +15 断言 =30 且仅 1 个锁文件，证明集中锁与旧实现互斥等价。

### 2026-09-04 16:17

2026-09-04：针对 `.meta/locks/` 锁文件累积问题，用户已拍板选「仅 Windows 释放即删」方案——下一步是在 `store.locked()` 出口做 best-effort unlink（吞错），Unix 因 inode race 保留不删，并在 `locks.py`/docstring 注明原因，约 10 行 + 测试。实现时务必只改 sidecar 语义的 `store.locked()`，不要下沉到 `file_lock` 通用层（`wiki_index`/`workspace_bootstrap` 锁的是数据文件本身）。

### 2026-09-04 16:17

2026-09-04：评估后否决了 `lint_wiki` 补刀清扫锁文件——锁文件存在是常态非问题（只能 fix-only 不能当 check 上报），Unix 下同样踩 inode race，且释放即删生效后残留量被钉死在上界，补刀收益极低。

### 2026-09-04 16:17

2026-09-04：D19 review 记录的非阻塞观察（未处理）：`_lock_path_for()` 每次调用做 resolve+祖先遍历+mkdir（低频可接受，热点可加「root→locks_dir」缓存）；Windows 下路径大小写不同会导致哈希不同、锁不互斥（内部路径已归一化，风险极低）；升级窗口内新旧进程锁路径不同、互不互斥，升级须重启 server。
