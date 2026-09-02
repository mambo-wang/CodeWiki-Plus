# 0003. 对端新鲜度判据用 git 提交时间而非 mtime

日期：2026-09-02
状态：已接受

## 背景

claude-mem 借鉴方案（`docs/claude-mem借鉴详细设计方案.md`）P1-4 为 `by_file`
时间线引入对端新鲜度标注 `possibly_stale`：判断"笔记描述的源文件在笔记写成之后
有没有变过"。原方案判据取文件系统 mtime（借鉴 claude-mem
`file-context.ts:255-265`），文档自身已识别到 git clone 场景下的缺陷。

## 决策

`possibly_stale` 的判据采用目标源文件的**最后一次 git 提交时间**
（`git log -1 --format=%cI -- <path>`，留 1 天缓冲吸收当天提交噪声），不采用
文件 mtime。判据不可得（文件未跟踪、git 不可用、笔记无日期）时返回 `null`。

## 理由

1. **mtime 在 clone 场景全量假阳性**。repowiki 与业务代码同仓（colocated）是
   CodeWiki 的标准形态，git clone 出来的工作树所有文件 mtime 均为 clone 时刻
   ——比任何上月笔记都新出一个多月，全部误标 `possibly_stale: true`。原方案
   的 1 天缓冲治不了这个病：缓冲吸收的是边界噪声，不是量级差。
2. **假阳性率高的标注会被调用方学会忽略**，等于花成本造一个被忽略的字段，
   还连坐损害 `stale_after`（F1/F2/F3）攒下的新鲜度语义信誉。
3. **git 提交时间语义恰好**：它就是"代码最后一次人为变动"的确定性记录，
   clone-safe 且不依赖本地文件系统时钟。CodeWiki 本就要求 repowiki 在 git
   仓内，依赖 git 不构成额外约束。
4. **成本可接受**：每次 by_file 查询对命中条目（≤ max_results=15）各一次
   `git log -1` 子进程调用，仅在 by_file 路径发生，不进默认检索热路径。

## 已知限制

- 工作树有未提交改动时，"最后一次提交"早于实际最后修改，可能漏标
  （假阴性）。保守方向可接受：把不确定的知识当新鲜，比把好知识全标过期
  的破坏性小。
- 依赖 git 可执行文件存在；不可用时诚实降级为 `null`，不猜。

## 后果

- P1-4 实现以 `git log -1 --format=%cI` 取代原方案的
  `target_path.stat().st_mtime`；CONTEXT.md 词汇表 `possibly_stale` 词条
  与本决策一致（_Avoid_: mtime 判定）。
- 原方案 §3.2/§3.3 的 mtime 实现与"跨机器时钟不可比"讨论随本决策作废。
