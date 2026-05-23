# Language Analyzers Module

## Overview

The **Language Analyzers** module is a comprehensive multi-language code analysis framework that extracts structural information and dependency relationships from source code across 9 programming languages (C, C++, C#, Java, JavaScript, Kotlin, PHP, Python, and TypeScript).

This module is a core component of the CodeWiki dependency analyzer, responsible for parsing source files, extracting semantic information (classes, functions, methods, interfaces, etc.), and identifying relationships between code components.

## Purpose

The Language Analyzers module provides:
- **Multi-language support**: Consistent API across 9 different programming languages
- **Semantic extraction**: Identification of classes, functions, methods, interfaces, enums, and other code components
- **Dependency mapping**: Detection of relationships such as inheritance, method calls, type usage, and instantiation
- **Unified data structures**: Returns standardized `Node` and `CallRelationship` objects regardless of language

## Architecture Overview

The Language Analyzers module is organized in a layered architecture:

```
┌─────────────────────────────────────────────────────────┐
│          Language Analyzer Interface                    │
│  (analyze_*_file: file_path, content → nodes, rels)    │
└─────────────────────────────────────────────────────────┘
                           ↓
    ┌─────────────────────┬─────────────────────┐
    ↓                     ↓                     ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Tree-Sitter  │  │ Tree-Sitter  │  │ Python AST   │
│ Analyzers    │  │ Analyzers    │  │ Analyzer     │
│ (C/C++/Java/ │  │ (JavaScript/ │  │ (Python)     │
│  C#/Kotlin)  │  │  TypeScript) │  │              │
│              │  │              │  │              │
│ 5 Languages  │  │ 2 Languages  │  │ 1 Language   │
└──────────────┘  └──────────────┘  └──────────────┘
        ↓                 ↓                 ↓
     PHP/TS Lib       Tree-Sitter      Python AST
     
                           ↓
                ┌──────────────────────┐
                │  Node Extraction     │
                │  Relationship        │
                │  Extraction          │
                └──────────────────────┘
                           ↓
                ┌──────────────────────┐
                │  Core Data Models    │
                │  - Node              │
                │  - CallRelationship  │
                └──────────────────────┘
```

## Key Components

### 1. **Analyzer Classes** (Language-Specific)

Each language has a dedicated analyzer class that handles parsing and extraction:

| Language | Analyzer Class | Parser | Module |
|----------|---|---|---|
| C | `TreeSitterCAnalyzer` | Tree-Sitter | [c_analyzer.md](c_analyzer.md) |
| C++ | `TreeSitterCppAnalyzer` | Tree-Sitter | [cpp_analyzer.md](cpp_analyzer.md) |
| C# | `TreeSitterCSharpAnalyzer` | Tree-Sitter | [csharp_analyzer.md](csharp_analyzer.md) |
| Java | `TreeSitterJavaAnalyzer` | Tree-Sitter | [java_analyzer.md](java_analyzer.md) |
| JavaScript | `TreeSitterJSAnalyzer` | Tree-Sitter | [javascript_analyzer.md](javascript_analyzer.md) |
| Kotlin | `TreeSitterKotlinAnalyzer` | Tree-Sitter | [kotlin_analyzer.md](kotlin_analyzer.md) |
| PHP | `TreeSitterPHPAnalyzer` | Tree-Sitter | [php_analyzer.md](php_analyzer.md) |
| Python | `PythonASTAnalyzer` | Python AST | [python_analyzer.md](python_analyzer.md) |
| TypeScript | `TreeSitterTSAnalyzer` | Tree-Sitter | [typescript_analyzer.md](typescript_analyzer.md) |

### 2. **Data Models**

Both models are defined in [dependency_analyzer_models.md](dependency_analyzer_models.md):

**Node**: Represents a code component (class, function, method, interface, etc.)
- `id`: Unique identifier (file_path::component_name)
- `name`: Component name
- `component_type`: Type of component (class, function, interface, etc.)
- `file_path`: Absolute file path
- `relative_path`: Path relative to repository root
- `source_code`: Original source code snippet
- `start_line`, `end_line`: Line numbers in source file
- `has_docstring`, `docstring`: Documentation information
- `parameters`: Function/method parameters
- `base_classes`: Inherited classes
- `class_name`: Parent class for methods

**CallRelationship**: Represents a dependency relationship between components
- `caller`: ID of the calling/dependent component
- `callee`: ID of the called/dependency component
- `call_line`: Line number where relationship occurs
- `is_resolved`: Boolean indicating if relationship is within same file

## Module Organization

```
codewiki/src/be/dependency_analyzer/analyzers/
├── c.py                    # C language analyzer
├── cpp.py                  # C++ language analyzer
├── csharp.py              # C# language analyzer
├── java.py                # Java language analyzer
├── javascript.py          # JavaScript language analyzer
├── kotlin.py              # Kotlin language analyzer
├── php.py                 # PHP language analyzer with NamespaceResolver
├── python.py              # Python AST analyzer
└── typescript.py          # TypeScript language analyzer
```

## Common Analysis Flow

Each analyzer follows a consistent two-pass workflow:

**Pass 1 - Node Extraction:**
- File input (path, content, repo_path)
- Parser initialization (Tree-Sitter or Python AST)
- AST/parse tree generation
- Component identification (classes, functions, interfaces, etc.)
- Node object creation

**Pass 2 - Relationship Extraction:**
- AST traversal for semantic relationships
- Detection of inheritance, calls, type usage
- Relationship deduplication
- CallRelationship object creation

**Output:**
- Tuple of (List[Node], List[CallRelationship])
- Ready for dependency graph construction

## Parsing Strategies

### Tree-Sitter Based Analyzers
8 of the 9 analyzers use **Tree-Sitter**, a fast and accurate parser generator:
- **Advantages**: 
  - Consistent API across languages
  - Handles partial/malformed code gracefully
  - Efficient parsing
  - Good error recovery

- **Languages**: C, C++, C#, Java, JavaScript, Kotlin, PHP, TypeScript

### Python AST Analyzer
Python uses the **native AST module**:
- **Advantages**:
  - Native Python support
  - Deep semantic understanding
  - Access to Python's built-in analysis capabilities
- **Trade-offs**:
  - Requires valid Python syntax (no partial code)
  - Uses Python's own parser instead of Tree-Sitter

## Extracted Component Types

Each analyzer extracts different types of components depending on language capabilities:

### Universal Components
- **Classes**: User-defined classes
- **Functions**: Top-level functions and methods
- **Interfaces**: Interface declarations
- **Enums**: Enumeration types

### Language-Specific Components
- **C/C++**: Structs, namespaces, macros
- **C#**: Records, delegates, static classes
- **Java**: Annotations, abstract classes
- **JavaScript/TypeScript**: Arrow functions, generators, type aliases
- **Kotlin**: Objects, extension functions, sealed classes
- **PHP**: Traits, traits as mixins, namespaces
- **Python**: Decorators, async functions
- **TypeScript**: Generic types, utility types, type parameters

## Relationship Types

Different analyzers identify relationships relevant to their language:

| Relationship Type | Languages | Example |
|---|---|---|
| Inheritance (extends) | All OOP languages | Class A extends Class B |
| Interface Implementation | Java, C#, TypeScript, PHP | Class A implements Interface B |
| Type Usage | Typed languages | Field of type SomeClass |
| Method Calls | All languages | functionA() calls functionB() |
| Object Creation | OOP languages | new ClassName() |
| Imports/Uses | All languages | use ClassName, import X from Y |
| Trait Usage | PHP, Kotlin | use TraitName, with TraitName |
| Static Calls | C++, C#, Java, PHP, Kotlin | Class::staticMethod() |

## Integration Points

### Input Dependencies
- **From**: [dependency_analyzer_models](dependency_analyzer_models.md) - `Node`, `CallRelationship` data structures
- **From**: File content and path information

### Output Dependencies
- **To**: [dependency_graph_construction](dependency_graph_construction.md) - Provides nodes and relationships for graph building
- **To**: [dependency_analysis_services](dependency_analysis_services.md) - Consumed by analysis services

### Processing Pipeline
```
Language Analyzer
    ↓
Extract Nodes & Relationships
    ↓
Dependency Graph Builder
    ↓
Analysis Service (Call Graph, Repo Analysis)
    ↓
Documentation Generator
```

## Common Patterns

### Node ID Generation
All analyzers generate component IDs in consistent format:
```
relative_file_path::component_name
relative_file_path::ClassName.method_name  // For methods
```

### Primitive Type Filtering
Each analyzer maintains a set of primitive/built-in types to exclude from dependency analysis:
- Prevents noise from standard library dependencies
- Focuses on user-defined dependencies
- Language-specific (e.g., `int`, `string` in Java vs `int`, `str` in Python)

### Top-Level Detection
Analyzers identify truly top-level components by:
- Checking parent node types
- Filtering out nested classes/functions
- Excluding template/variable scope declarations

### Docstring Extraction
When available, extractors capture documentation:
- JavaScript/TypeScript: JSDoc comments
- Python: Python docstrings
- PHP: PHPDoc comments
- Kotlin: KDoc comments

## Error Handling

### Robust Parsing
- **Tree-Sitter analyzers**: Gracefully handle partial/malformed code
- **Python analyzer**: Catches `SyntaxError` and logs warnings

### Fallback Strategies
- Missing nodes are skipped without stopping analysis
- Unresolved relationships are marked as `is_resolved=False`
- Parser initialization failures are logged

## Performance Characteristics

### Parsing Speed
- **Tree-Sitter**: O(n) linear time complexity, very fast
- **Python AST**: Fast, uses native Python parser

### Memory Usage
- Single-pass analysis for most languages (except PHP which does 3 passes)
- AST kept in memory only during analysis
- Streaming output of nodes and relationships

### Scalability
- Handles large files (1000+ lines) efficiently
- PHP analyzer includes recursion depth limits to prevent stack overflow
- JavaScript/TypeScript handle complex nested structures

## Configuration & Customization

### Per-Analyzer Exclusions
- **JavaScript/TypeScript**: Excludes built-in types and methods
- **PHP**: Filters template files, skips view directories
- **Python**: Excludes test functions starting with `_test_`
- **C/C++**: Filters system/library functions

### Optional Parameters
- `repo_path`: Repository root for relative path calculation
- Affects all relative path computations and component ID generation

## Detailed Sub-Module Documentation

For in-depth information about each language analyzer implementation, refer to the specialized sub-module documentation:

### Tree-Sitter Based Analyzers (8 languages)

1. **[C Analyzer](c_analyzer.md)** - `TreeSitterCAnalyzer`
   - Function and struct extraction
   - Global variable tracking
   - System function filtering
   
2. **[C++ Analyzer](cpp_analyzer.md)** - `TreeSitterCppAnalyzer`
   - Class method extraction
   - Inheritance and polymorphism
   - Namespace support
   
3. **[C# Analyzer](csharp_analyzer.md)** - `TreeSitterCSharpAnalyzer`
   - Records, delegates, static classes
   - Property and field type analysis
   - Abstract class detection
   
4. **[Java Analyzer](java_analyzer.md)** - `TreeSitterJavaAnalyzer`
   - Abstract class and annotation support
   - Generic type handling
   - Constructor parameter analysis
   
5. **[JavaScript Analyzer](javascript_analyzer.md)** - `TreeSitterJSAnalyzer`
   - Arrow functions and generators
   - Async/await support
   - JSDoc type extraction
   
6. **[Kotlin Analyzer](kotlin_analyzer.md)** - `TreeSitterKotlinAnalyzer`
   - Data classes and sealed classes
   - Extension function support
   - Nullable type handling
   
7. **[PHP Analyzer](php_analyzer.md)** - `TreeSitterPHPAnalyzer` + `NamespaceResolver`
   - Namespace resolution
   - Use statement tracking
   - Trait usage analysis
   - Template file filtering
   
8. **[TypeScript Analyzer](typescript_analyzer.md)** - `TreeSitterTSAnalyzer`
   - Type annotation extraction
   - Generic type parameters
   - Interface implementation

### Native Parser Analyzer (1 language)

9. **[Python Analyzer](python_analyzer.md)** - `PythonASTAnalyzer`
   - Native AST parsing
   - Decorator support
   - Base class extraction
   - Async function detection

## Usage Examples

### Basic Analysis
```python
from codewiki.src.be.dependency_analyzer.analyzers.python import analyze_python_file

file_content = """
class DataProcessor:
    def process(self, data):
        return self.transform(data)
    
    def transform(self, data):
        return data.upper()
"""

nodes, relationships = analyze_python_file("example.py", file_content, "/repo")
```

### Cross-Language Consistency
```python
# Each analyzer follows the same interface
nodes_c, rels_c = analyze_c_file(file_path, content, repo_path)
nodes_js, rels_js = analyze_javascript_file_treesitter(file_path, content, repo_path)
nodes_py, rels_py = analyze_python_file(file_path, content, repo_path)

# All return: Tuple[List[Node], List[CallRelationship]]
```

## Testing & Validation

### Coverage
- Each analyzer tested against real-world code samples
- Tests verify:
  - Node extraction accuracy
  - Relationship detection
  - Primitive type filtering
  - Relative path calculation

### Known Limitations
- Template files (views, templates) skipped in PHP
- Partial/incomplete code may have reduced accuracy
- Cross-file relationships marked as unresolved (resolved by CallGraphAnalyzer)
- Generic type parameters not fully extracted in all languages

## Future Enhancements

- [ ] Go language support
- [ ] Rust language support
- [ ] Ruby language support
- [ ] Generic type parameter extraction
- [ ] Type inference for method returns
- [ ] Cross-file relationship resolution optimization
- [ ] Incremental parsing support
- [ ] LSP (Language Server Protocol) integration

## Documentation Summary

This documentation set provides comprehensive coverage of the Language Analyzers module:

### Main Documentation (This File)
- **Overview & Architecture**: High-level design and purpose
- **Common Patterns**: Shared design patterns across all analyzers
- **Integration Points**: How this module fits into the larger system
- **Comparison & Selection**: Guide for choosing which analyzer to use

### Sub-Module Documentation (9 Specialized Guides)

#### Quick Reference by Language

| Language | Analyzer Type | Key Features | Doc Link |
|----------|---|---|---|
| C | Tree-Sitter | Functions, structs, globals | [c_analyzer.md](c_analyzer.md) |
| C++ | Tree-Sitter | Classes, namespaces, methods | [cpp_analyzer.md](cpp_analyzer.md) |
| C# | Tree-Sitter | Records, delegates, properties | [csharp_analyzer.md](csharp_analyzer.md) |
| Java | Tree-Sitter | Annotations, generics, interfaces | [java_analyzer.md](java_analyzer.md) |
| JavaScript | Tree-Sitter | Arrow funcs, async, JSDoc | [javascript_analyzer.md](javascript_analyzer.md) |
| Kotlin | Tree-Sitter | Data classes, extensions, nullability | [kotlin_analyzer.md](kotlin_analyzer.md) |
| PHP | Tree-Sitter | Namespaces, traits, uses | [php_analyzer.md](php_analyzer.md) |
| Python | Native AST | Classes, decorators, async | [python_analyzer.md](python_analyzer.md) |
| TypeScript | Tree-Sitter | Types, generics, interfaces | [typescript_analyzer.md](typescript_analyzer.md) |

### How to Use This Documentation

**For Implementers:**
1. Start with this file for overall architecture
2. Refer to specific language sub-modules when implementing or debugging
3. Check [dependency_analyzer_models](dependency_analyzer_models.md) for data structures

**For Integrators:**
1. Understand the common interface in this file
2. Review specific analyzers needed for your use case
3. Refer to [dependency_graph_construction](dependency_graph_construction.md) for consuming output

**For Contributors:**
1. Study the common patterns in this file
2. Review existing language analyzer (sub-module doc)
3. Use as template for implementing new language support

## Key Takeaways

1. **Consistency**: All 9 analyzers expose the same interface (`Tuple[List[Node], List[CallRelationship]]`)

2. **Performance**: Tree-Sitter gives O(n) parsing; Python uses native AST for semantic accuracy

3. **Language Coverage**: 
   - C/C++-style languages (C, C++): Structs, pointers, namespaces
   - .NET languages (C#): Records, delegates, properties
   - JVM languages (Java, Kotlin): Generics, annotations, sealed classes
   - Web languages (JS, TS): Modern async, JSDoc, type annotations
   - Scripting language (Python): Native AST, decorators, type hints
   - Server language (PHP): Namespaces, traits, use statements

4. **Extensibility**: New languages can be added by creating a new analyzer class following established patterns

5. **Robustness**: Error handling varies by parser:
   - Tree-Sitter: Graceful partial-code handling
   - Python AST: Syntax validation with clear error reporting

---

**Last Updated**: 2024
**Status**: Core module - Stable
**Documentation Version**: v2.0 (Comprehensive multi-module)
**Maintainer**: CodeWiki Team

**Quick Links:**
- [Architecture Patterns](language_analyzers.md#common-patterns)
- [Integration Guide](language_analyzers.md#integration-points)
- [C Analyzer Details](c_analyzer.md)
- [Python Analyzer Details](python_analyzer.md)
- [Dependency Models](dependency_analyzer_models.md)
