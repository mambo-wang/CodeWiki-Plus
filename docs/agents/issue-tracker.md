# Issue tracker: GitHub（对外）+ `.scratch/`（内部工单）

本仓库的 issue 与 spec 分两处存放，按**读者是谁**路由。对外渠道是 GitHub Issues，用 `gh` CLI 操作；会话内部拆出来的实现工单默认落仓库内的 `.scratch/`，不进 GitHub。

**Why 双轨**：`mambo-wang/CodeWiki-Plus` 是公开仓库（fork 自 `FSoft-AI4Code/CodeWiki`），而多步规划历来写在本地——`.scratch/centralized-wiki-layout/`（`spec.md` + `issues/01…10.md`）、`.scratch/skill-creator/issues/t1…t6.md`。把内部路线图和半成品拆解直接发到公开 issue 区，等于替用户发布未定稿的计划。

## 路由判据

| 东西 | 去向 |
| --- | --- |
| 外部来件（用户报 bug、feature request）、`/triage` 队列、对外可见的 spec | GitHub Issues |
| `/to-spec`、`/to-tickets` 产出的本次实现工单 | `.scratch/<feature>/` |
| `/wayfinder` 地图 | 对外协作用 GitHub issue（见文末）；纯内部 feature 用 `.scratch/<feature>/map.md` |

拿不准时选 `.scratch/`：本地工单随时可以 `gh issue create` 提升为公开 issue，反过来要先删公开 issue 并留下删除痕迹。

## Conventions（GitHub）

- **创建 issue**：`gh issue create --title "..." --body "..."`，多行 body 用 heredoc。
- **读 issue**：`gh issue view <number> --comments`，评论用 `jq` 过滤，同时取 labels。
- **列 issue**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，按需加 `--label` / `--state` 过滤。
- **评论**：`gh issue comment <number> --body "..."`
- **加 / 去标签**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **关闭**：`gh issue close <number> --comment "..."`

仓库归属由 `git remote -v` 推断；在 clone 里跑 `gh` 会自动带上。**注意本机 `github.com` 直连常超时，`api.github.com` 可用，所以 `gh` 正常、`git push` 需走 `ssh.github.com:443`。**

## Conventions（本地 `.scratch/`）

- 一个 feature 一个目录：`.scratch/<feature-slug>/`
- spec 落 `spec.md`；工单一单一文件：`issues/NN-<slug>.md`（`NN` 两位递增，与既有目录同风格）
- 工单 body 顶部声明关系：`Part of <feature>`、`Blocked by: NN-<slug>`（本地没有原生依赖，边写在正文里）
- 状态用 frontmatter：`status: open | done | dropped`，完成后不删文件（保留决策轨迹）

## Pull requests as a triage surface

**PRs as a request surface: no.** _(本仓库若要把外部 PR 纳入分诊队列，把这里改成 `yes`，`/triage` 会读这个开关。)_

设为 `yes` 时，PR 走与 issue 相同的标签与状态机，命令换成 `gh pr` 等价物：

- **读 PR**：`gh pr view <number> --comments`、`gh pr diff <number>`
- **列出待分诊的外部 PR**：`gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`，只保留 `authorAssociation` 为 `CONTRIBUTOR` / `FIRST_TIME_CONTRIBUTOR` / `NONE`（丢掉 `OWNER` / `MEMBER` / `COLLABORATOR`）
- **评论 / 打标 / 关闭**：`gh pr comment`、`gh pr edit --add-label`/`--remove-label`、`gh pr close`

GitHub 的 issue 与 PR 共用一个编号空间，裸写 `#42` 两种都可能——先用 `gh pr view 42` 判，失败再 `gh issue view 42`。

## 当技能说「publish to the issue tracker」

先过一遍上面的路由判据：对外 → `gh issue create`；内部实现工单 → 在 `.scratch/<feature>/issues/` 里新建文件（编号顺延）。

## 当技能说「fetch the relevant ticket」

`gh issue view <number> --comments`；工单在本地时直接读 `.scratch/<feature>/issues/<file>.md`。

## Wayfinding operations

`/wayfinder` 用：**map** 是承载 Notes / Decisions-so-far / Fog 正文的单条 issue，**child** 是它的子工单。纯内部 feature 可把这套搬到 `.scratch/<feature>/map.md` + `issues/`，此时 child 用编号引用、blocking 写正文。

- **Map**：一条打 `wayfinder:map` 标签的 issue，正文含 Notes / Decisions-so-far / Fog。`gh issue create --label wayfinder:map`
- **Child ticket**：以 GitHub sub-issue 形式挂到 map（`gh api` 打 sub-issues 端点）。仓库没开 sub-issues 时，把 child 列进 map 正文的 task list，并在 child 顶部写 `Part of #<map>`。标签用 `wayfinder:<type>`（`research`/`prototype`/`grilling`/`task`）。认领后 child 指派给 driving dev。
- **Blocking**：用 GitHub 的 **native issue dependencies**——这是唯一 UI 可见的权威表示。加边：`gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`，其中 `<blocker-db-id>` 是阻塞方的数字 **database id**（`gh api repos/<owner>/<repo>/issues/<n> --jq .id`，**不是** `#number` 也不是 `node_id`）。GitHub 以 `issue_dependencies_summary.blocked_by` 汇报（只含未完成的阻塞方，即真正的闸门）。环境不支持 dependencies 时，退化为 child 正文顶部的 `Blocked by: #<n>, #<n>`。所有阻塞方关闭后该工单才算未阻塞。
- **Frontier query**：列出 map 的 open children（`gh issue list --state open`，按 map 的 sub-issues / task list 圈定），剔除有 open 阻塞方（`issue_dependencies_summary.blocked_by > 0`，或 `Blocked by` 行里有 open issue）或已有 assignee 的，取 map 顺序里第一条。
- **Claim**：`gh issue edit <n> --add-assignee @me`，本次会话的第一个写操作。
- **Resolve**：`gh issue comment <n> --body "<answer>"` → `gh issue close <n>` → 把上下文指针（gist + 链接）追加进 map 的 Decisions-so-far。
