# bootstrap.ps1 — 初始化 Harness 工作区：克隆全部业务子仓
# 用法：在本仓根目录执行 .\bootstrap.ps1
# 幂等：已存在的目录自动跳过，可重复执行。
# 注意：登记表骨架行 `$repos = [ordered]@{` 与配对的 `}` 由 CodeWiki 的
# init_workspace / add_workspace_repo 工具定位维护，请勿改动这两行的结构
# （表内条目内容可自由增删改）。

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# 业务仓登记表：目录名 -> 仓库 URL
# 新增业务仓时同步更新 .gitignore 与 repowiki/wiki/repo-map.md
$repos = [ordered]@{
{{REPO_TABLE_PS}}
}

foreach ($name in $repos.Keys) {
    $dest = Join-Path $root $name
    if (Test-Path (Join-Path $dest ".git")) {
        Write-Host "[skip] $name 已存在"
    } elseif (Test-Path $dest) {
        Write-Warning "[warn] $name 目录存在但不是 git 仓库，请人工检查：$dest"
    } else {
        Write-Host "[clone] $name -> $dest"
        git clone $repos[$name] $dest
        if ($LASTEXITCODE -ne 0) { throw "克隆失败：$name" }
    }
}

Write-Host ""
Write-Host "完成。业务子仓已就位于本仓目录下（harness 仓的 git 不追踪它们）。"
Write-Host "验证：git status 应保持干净；若出现业务仓目录，检查 .gitignore。"
