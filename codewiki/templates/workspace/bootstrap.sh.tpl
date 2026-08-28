#!/usr/bin/env bash
# bootstrap.sh — 初始化 Harness 工作区：克隆全部业务子仓
# 用法：在本仓根目录执行 ./bootstrap.sh
# 幂等：已存在的目录自动跳过，可重复执行。
# 注意：登记表骨架行 `declare -A repos=(` 与配对的 `)` 由 CodeWiki 的
# init_workspace / add_workspace_repo 工具定位维护，请勿改动这两行的结构
# （表内条目内容可自由增删改）。
set -euo pipefail

root="$(cd "$(dirname "$0")" && pwd)"

# 业务仓登记表：目录名 -> 仓库 URL
# 新增业务仓时同步更新 .gitignore 与 repowiki/wiki/repo-map.md
declare -A repos=(
{{REPO_TABLE_SH}}
)

for name in "${!repos[@]}"; do
    dest="$root/$name"
    if [ -d "$dest/.git" ]; then
        echo "[skip] $name 已存在"
    elif [ -d "$dest" ]; then
        echo "[warn] $name 目录存在但不是 git 仓库，请人工检查：$dest" >&2
    else
        echo "[clone] $name -> $dest"
        git clone "${repos[$name]}" "$dest"
    fi
done

echo ""
echo "完成。业务子仓已就位于本仓目录下（harness 仓的 git 不追踪它们）。"
echo "验证：git status 应保持干净；若出现业务仓目录，检查 .gitignore。"
