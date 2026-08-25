---
title: LanguageAnalyzers
type: Module
generated:
  by: codewiki/5.2.0
  at: 2026-08-02 23:41:39+00:00
stale_after: '2027-02-22'
metadata:
  depth: 2
  module_type: leaf
  component_count: 21
  generated_by: codewiki
  generator_version: '1.0'
  updated_at: 2026-07-28
description: LanguageAnalyzers 是 DependencyAnalyzer 的叶子模块，包含针对 10 种编程语言的源码分析器。每个分析器接收一个文件路径与源码内容（外加可选的
  `repo_path`），解析后产出两类标准对象：`Node`（类、函数、方法、接口等符号）与 `CallRelationship`（调用/
aliases:
- LanguageAnalyzers
status: stable
verified:
- by: human:wangbao
  at: '2026-08-25T16:48:17Z'
---

# LanguageAnalyzers 模块文档

## 概述
LanguageAnalyzers 是 DependencyAnalyzer 的叶子模块，包含针对 10 种编程语言的源码分析器。每个分析器接收一个文件路径与源码内容（外加可选的 `repo_path`），解析后产出两类标准对象：`Node`（类、函数、方法、接口等符号）与 `CallRelationship`（调用/继承/类型依赖边），定义于 [[AnalyzerModels]]。绝大多数语言使用 tree-sitter 构建 AST（Python 使用标准库 `ast`），统一以「三遍式」流程：解析 → 抽取节点 → 抽取关系。入口函数 `analyze_*_file(...)` 是各语言的薄封装，便于 [[AnalysisPipeline]] 的 `RepoAnalyzer` 按扩展名分派调用。

## 组件清单
| 组件 | 类型 | 文件 | 职责 |
| --- | --- | --- | --- |
| TreeSitterCAnalyzer | class | analyzers/c.py | C 文件解析，抽取函数/结构体/全局变量及调用关系 |
| analyze_c_file | func | analyzers/c.py | C 分析入口，返回 (nodes,rels) |
| TreeSitterCppAnalyzer | class | analyzers/cpp.py | C++ 解析，含宏恢复与类/方法/类型别名抽取 |
| analyze_cpp_file | func | analyzers/cpp.py | C++ 分析入口 |
| TreeSitterCSharpAnalyzer | class | analyzers/csharp.py | C# 解析，抽取类/接口/结构体/枚举/记录/委托 |
| analyze_csharp_file | func | analyzers/csharp.py | C# 分析入口 |
| TreeSitterGoAnalyzer | class | analyzers/go.py | Go 解析，抽取 struct/interface/func/method 及接收者类型解析 |
| analyze_go_file | func | analyzers/go.py | Go 分析入口 |
| TreeSitterJavaAnalyzer | class | analyzers/java.py | Java 解析，抽取类/接口/枚举/记录/注解与方法，含 import 解析 |
| analyze_java_file | func | analyzers/java.py | Java 分析入口 |
| TreeSitterJSAnalyzer | class | analyzers/javascript.py | JS 解析，抽取类/函数/方法、调用及 JSDoc 类型边 |
| analyze_javascript_file_treesitter | func | analyzers/javascript.py | JS 分析入口 |
| TreeSitterKotlinAnalyzer | class | analyzers/kotlin.py | Kotlin 解析，抽取类/对象/函数及委托/导航表达式关系 |
| analyze_kotlin_file | func | analyzers/kotlin.py | Kotlin 分析入口 |
| NamespaceResolver | class | analyzers/php.py | PHP 命名空间/use 别名到全限定名的解析器 |
| TreeSitterPHPAnalyzer | class | analyzers/php.py | PHP 解析，抽取类/接口/trait/枚举/函数/方法 |
| analyze_php_file | func | analyzers/php.py | PHP 分析入口 |
| PythonASTAnalyzer | class | analyzers/python.py | Python 解析（ast.NodeVisitor），抽取类/函数/方法 |
| analyze_python_file | func | analyzers/python.py | Python 分析入口 |
| TreeSitterTSAnalyzer | class | analyzers/typescript.py | TS 解析，抽取类/接口/类型别名/枚举/函数及丰富关系 |

## 关键设计

### 公共约定
所有分析器构造时即执行 `_analyze()`，产出 `self.nodes`（`List[Node]`）与 `self.call_relationships`（`List[CallRelationship]`）。`component_id` 统一格式为 `<relative_path>::<name>`，方法/接收者限定名写作 `<relative_path>::<Class>.<name>`。

### C / C++
`TreeSitterCAnalyzer` 递归收集 `function_definition`/`struct_specifier`/`typedef`/全局 `declaration`，`call_expression` 记录调用（被调名以简单名留下供跨文件解析），全局变量引用标 `is_resolved=True`。
`TreeSitterCppAnalyzer` 更复杂：先用 `_parse_with_macro_recovery` 在含语法错误时做 ALL_CAPS 宏规范化并重试比对错误数；抽取类/结构体/命名空间/方法/`type_alias`（`using`/`typedef` 视作 API 表面），并做 `new`、基类子句、`field_expression` 接收者类型推断，使用 [[AnalyzerUtils]] 的 `is_external_symbol`/`is_macro_name` 过滤噪声。

### C#
`TreeSitterCSharpAnalyzer` 识别 `class`/`interface`/`struct`/`enum`/`record`/`delegate`（含 abstract/static 修饰），关系侧重类型使用：基类 `base_list`、属性/字段/方法参数类型边（`_is_primitive_type` 过滤内建类型）。

### Go
`TreeSitterGoAnalyzer` 抽取 `type_declaration`（struct/interface）、`function_declaration`、`method_declaration`（接收者类型经 `_get_receiver_type` 限定），并采集 `package`、注释 docstring、参数。`_resolve_type_name` 解析指针/切片/map/channel 等，调用经 `selector_expression` 做变量类型推断，`_is_stdlib_package` 过滤 `fmt`/`http` 等标准库。

### Java
`TreeSitterJavaAnalyzer` 抽取 `class`/`interface`/`enum`/`record`/`annotation` 及方法，并解析 `package` 与 `import`（map 与通配）。关系覆盖 `extends`、`implements`、字段类型、方法调用、`object_creation_expression`；`_resolve_java_type`/`_resolve_java_member` 经 import 与包名做全限定名解析，配合 [[AnalyzerUtils]] 的 `JAVA_OBJECT_METHODS`/`is_external_symbol` 过滤 JDK 类型与 `java.lang.Object` 继承方法。

### JavaScript / TypeScript
`TreeSitterJSAnalyzer`（JS）与 `TreeSitterTSAnalyzer`（TS，用 `tree_sitter_typescript.language_typescript()`）共享逻辑：抽取类（含 `class_heritage` 继承）、函数、箭头函数、方法；关系含调用、`new`、`await`，JS 额外解析 JSDoc `@param/@return/@type` 类型边。TS 版本更精细：先 `_extract_all_entities` 收集所有声明再 `_filter_top_level_declarations`（依据 `program`/`export`/`module` 上下文与 `_is_inside_function_body` 判断真正顶层），并抽取构造器参数依赖、类型注解/泛型关系。`_add_relationship` 用 `(caller,callee,line)` 去重。

### Kotlin
`TreeSitterKotlinAnalyzer` 抽取 class（含 abstract/data/enum/annotation 修饰）、object、function/method，关系含 `delegation_specifiers` 继承/实现、属性类型、构造参数类型、`call_expression`/`navigation_expression`（经 `_find_variable_type` 推断接收者）。

### PHP（含 NamespaceResolver）
`TreeSitterPHPAnalyzer` 使用 `tree_sitter_php.language_php()` 处理混编 HTML 的 PHP，先 `_extract_namespace_info` 收集 `namespace`/`use`，由 `NamespaceResolver` 把别名/部分限定名解析为全限定名（以 `\` 分隔并替换为 `.`），再抽取 class/interface/trait/enum/function/method。关系覆盖 use 引入、extends、implements、`new`、`scoped_call_expression`（静态调用）、构造器属性提升。`_is_template_file` 跳过 `.blade.php` 等模板，`MAX_RECURSION_DEPTH` 防栈溢出。

### Python
`PythonASTAnalyzer` 继承 `ast.NodeVisitor`，用标准库 `ast` 而非 tree-sitter。`visit_ClassDef`/`visit_FunctionDef`/`visit_AsyncFunctionDef` 收集节点，`visit_Call` 记录调用（`_get_call_name` 过滤 `print`/`len` 等内建与 `obj.method` 形式），`_should_include_function` 排除 `_test_` 前缀函数。

## 数据流
```mermaid
flowchart TD
    A[源码文件 + repo_path] --> B[TreeSitter / ast 解析]
    B --> C[抽取 Nodes<br/>类/函数/方法/接口/...]
    B --> D[抽取 CallRelationship<br/>调用/继承/类型依赖]
    C --> E[Node 列表]
    D --> F[CallRelationship 列表]
    E --> G[[AnalysisPipeline]] / [[GraphAndSort]]
    F --> G
```

## 依赖关系
- [[DependencyAnalyzer]]（父模块）
- [[AnalyzerModels]]（Node / CallRelationship 定义）
- [[AnalyzerUtils]]（`is_external_symbol`、`is_macro_name`、`normalize_symbol` 等符号过滤）
- [[AnalysisPipeline]]（RepoAnalyzer 分派调用 `analyze_*_file`）
- [[GraphAndSort]]（消费产出的 nodes/relationships 构建依赖图）
- [[RouteExtractors]]（同目录下路由抽取，复用相似 AST 模式）

## 使用示例
```python
from codewiki.src.be.dependency_analyzer.analyzers.java import analyze_java_file

nodes, rels = analyze_java_file(
    "src/main/java/com/foo/Service.java",
    open("src/main/java/com/foo/Service.java").read(),
    repo_path=".",
)
for n in nodes:
    print(n.component_id, n.component_type)
for r in rels:
    print(r.caller, "->", r.callee, "resolved=", r.is_resolved)
```
入口函数亦可被 [[MCP_Tools_Analysis]] 的 `handle_analyze_repo` 与 [[LLM_Backend]] 的文档生成流程复用。

## 扩展点（新增语言分析器）
1. 在 `codewiki/src/be/dependency_analyzer/analyzers/` 下新建 `<lang>.py`。
2. 实现 `<Lang>Analyzer`：构造时调用 `_analyze()`，产出 `self.nodes` 与 `self.call_relationships`；`component_id` 遵循 `<rel_path>::<name>` 约定（方法加 `<Class>.` 限定）。
3. 提供 `analyze_<lang>_file(file_path, content, repo_path=None) -> (nodes, rels)` 入口。
4. 外部/内建符号过滤复用 [[AnalyzerUtils]] 的 `is_external_symbol("lang", name)`、`is_macro_name`，或补充语言专属 `primitive` 集合。
5. 在 [[AnalysisPipeline]] 的 `RepoAnalyzer` 扩展名分派表中登记，使新语言纳入 [[GraphAndSort]] 与 [[RouteExtractors]] 的处理范围。
6. 如需跨文件依赖解析，未解析边（`is_resolved=False`，保留简单名）交由 `CallGraphAnalyzer`（属 [[AnalysisPipeline]]）统一处理。

## 相关模块
- [[DependencyAnalyzer]]：本模块的直接父节点，统筹语言分析。
- [[AnalysisPipeline]]：驱动分析、跨文件解析与调用图超时控制。
- [[AnalyzerModels]]：Node / CallRelationship / Repository 数据契约。
- [[AnalyzerUtils]]：外部符号判定、路径规范化与模式工具。
- [[GraphAndSort]]：消费产出构建依赖图与拓扑排序。
- [[RouteExtractors]]：同目录下的路由/MQ 抽取器，复用 AST 遍历模式。
- [[LLM_Backend]]：基于结构化组件生成 Wiki 文档。
- [[MCP_Tools_Analysis]]：通过 MCP 暴露分析能力。
- [[SharedConfig]]：提供路径与运行配置。