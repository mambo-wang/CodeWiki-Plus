---
type: decision
title: "Zig analyzer 应保留组件 ID 并按导入与构建模块精确解析"
tags: ["callgraph", "codewiki", "decision"]
aliases: ["Zig", "zig analyzer", "build.zig", "@import", "组件身份", "增量重解析"]
metadata:
  date: 2026-11-27
  confidence_level: weak
  related_modules: ["dependency_analyzer", "mcp"]
  related_components: ["src/main.zig::main", "build.zig::build"]
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T08:39:32Z }
stale_after: 2027-11-27
---

## 背景

CodeWiki-Plus 需要分析 Zig 仓库，但本地已有组件 ID、CallGraph 与 SQLite 增量缓存契约，不能整包覆盖 dependency_analyzer。上游 Zig analyzer 依赖新版 AST 与 language-pack 首次运行下载，直接复制会带来离线失败和语义分叉。

## 核心内容

使用独立 tree-sitter-zig wheel 和 grammar preflight，保留 <relative_path>::<logical_name> 组件 ID。解析 struct/enum/union/opaque、嵌套与泛型容器、函数和方法，以及 @import alias、仓库内 re-export、@This()、构造器、实例化和类型引用。build.zig 的 addModule 两种 root_source_file 写法参与模块名到仓库文件的精确映射。

跨文件调用只发送完整 path::logical_name，由 CallGraph exact-only 解析；未知 receiver 不保留裸方法名回退。显式类型变量的初始化表达式仍递归提取调用边，局部类型按 block 作用域保存/恢复，内层同名变量不污染外层。任一 Zig 文件变化时保守重解析全部现存 Zig，避免 import、re-export 或构建模块映射留下旧边；非 Zig 增量只合并仍存活的缓存节点与目标边。alias-only 文件同样写入指纹，删除文件后清除对应指纹，保证下一轮无变更收敛。build.zig 同时作为构建 artifact，并提取字面源码路径引用。

## 原因

独立 wheel 保证离线首用，显式 grammar 失败避免把环境问题伪装成零组件。完整组件 ID 与精确导入语义可防止同尾名误绑；保守全量重解析用可接受的计算成本换增量正确性。将无组件的 directive-only 文件纳入指纹，可消除无变更重复误报。

## 边界

不跟随 usingnamespace，不推断 comptime 动态类型；跨文件字段链类型、匿名容器和 test blocks 不进入组件图。不执行 build.zig 或 Zig 编译器。外部包、缺失文件与越界 import 不生成项目组件边。
