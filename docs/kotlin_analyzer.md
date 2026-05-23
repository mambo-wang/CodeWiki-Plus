# Kotlin Analyzer Module Documentation

## Module Overview

The **Kotlin Analyzer** is a specialized language analyzer component responsible for parsing and analyzing Kotlin source code files. It extracts structural information (nodes) and identifies relationships between components (call relationships, inheritance, interface implementations) using the Tree-sitter parsing library.

### Core Purpose

- **Parse Kotlin Files**: Use Tree-sitter with Kotlin grammar to create abstract syntax trees (ASTs)
- **Extract Components**: Identify and catalog Kotlin language constructs (classes, interfaces, objects, functions, methods)
- **Discover Dependencies**: Extract relationships between components (inheritance, method calls, property types, constructor parameters)
- **Build Component Graph**: Generate data structures for dependency graph construction

### Key Responsibilities

1. **AST Parsing**: Convert Kotlin source code into navigable syntax trees
2. **Node Extraction**: Identify all relevant components and their metadata
3. **Relationship Discovery**: Find dependencies between components through various mechanisms
4. **Type Resolution**: Infer variable and parameter types to establish proper relationships

---

## Architecture & Components

### Main Component: TreeSitterKotlinAnalyzer

The `TreeSitterKotlinAnalyzer` class is the core analyzer that orchestrates Kotlin file analysis.

```
TreeSitterKotlinAnalyzer
├── Input Processing
│   ├── file_path: str
│   ├── content: str
│   └── repo_path: Optional[str]
├── Internal State
│   ├── nodes: List[Node]
│   └── call_relationships: List[CallRelationship]
└── Analysis Pipeline
    ├── _analyze()
    ├── _extract_nodes()
    └── _extract_relationships()
```

#### Key Attributes

| Attribute | Type | Purpose |
|-----------|------|---------|
| `file_path` | `Path` | Absolute path to the Kotlin source file |
| `content` | `str` | Raw source code content |
| `repo_path` | `Optional[str]` | Repository root path for relative path computation |
| `nodes` | `List[Node]` | Extracted components (classes, functions, methods, etc.) |
| `call_relationships` | `List[CallRelationship]` | Identified relationships between components |

#### Constructor Flow

```
┌─ __init__(file_path, content, repo_path)
│
├─ Store Parameters (file_path, content, repo_path)
├─ Call _analyze()
│  └─ Parse file with Tree-sitter grammar
│     └─ Create AST root node
├─ Extract Nodes from AST
│  └─ Create Node objects for each component
├─ Extract Relationships from AST  
│  └─ Create CallRelationship objects for dependencies
└─ Return initialized analyzer with nodes and relationships
```

---

## Analysis Pipeline

### Phase 1: Tree-sitter Parsing

**Method**: `_analyze()`

The analyzer initializes the Tree-sitter parser with Kotlin language support and creates an AST from the source code.

```python
# Process:
1. Load Kotlin language capsule from tree_sitter_kotlin
2. Create Parser with Kotlin language
3. Parse file content into AST
4. Get root node and source lines
5. Traverse tree for node extraction
```

**Error Handling**: Catches and logs exceptions during parsing; continues gracefully if parsing fails.

### Phase 2: Node Extraction

**Method**: `_extract_nodes(node, top_level_nodes, lines)`

Recursively traverses the AST to identify and extract all Kotlin components.

#### Supported Component Types

| Component Type | Kotlin Construct | Detection |
|---|---|---|
| `class` | Regular class | `class_declaration` without modifiers |
| `abstract class` | Abstract class | `class_declaration` with `abstract` modifier |
| `data class` | Data class | `class_declaration` with `data` modifier |
| `enum class` | Enum class | `class_declaration` with `enum` modifier |
| `annotation class` | Annotation class | `class_declaration` with `annotation` modifier |
| `interface` | Interface | Child node of `class_declaration` |
| `object` | Singleton object | `object_declaration` |
| `function` | Top-level function | `function_declaration` outside classes |
| `method` | Class member function | `function_declaration` inside classes |

#### Node Creation Process

The analyzer recursively visits all AST nodes, identifying components based on their type:

- **class_declaration** → Creates class, abstract class, data class, enum class, or annotation class Node
- **object_declaration** → Creates object Node
- **function_declaration** → Creates function or method Node (depending on context)

Each identified node is enriched with metadata (location, docstring, source code) and added to both the nodes list and the top_level_nodes map for reference during relationship extraction.

#### Node Object Creation

Each extracted component becomes a `Node` object with:

```python
Node(
    id=component_id,                    # Unique identifier
    name=node_name,                      # Component name
    component_type=node_type,            # Type (class, method, etc.)
    file_path=str(self.file_path),      # Absolute path
    relative_path=relative_path,         # Path relative to repo root
    source_code=code_snippet,            # Source code excerpt
    start_line=start_line,               # Starting line number
    end_line=end_line,                   # Ending line number
    has_docstring=bool(docstring),       # Documentation present?
    docstring=docstring,                 # Documentation content
    display_name=display_name,           # Human-readable name
    component_id=component_id            # Component identifier
)
```

### Phase 3: Relationship Extraction

**Method**: `_extract_relationships(node, top_level_nodes)`

Identifies four main categories of relationships between components:

#### 1. Inheritance & Interface Implementation

**Detection**: `delegation_specifiers` in class declarations

```kotlin
class MyClass : BaseClass, MyInterface {  // delegation_specifiers contains these
    // ...
}
```

**Relationship Type**: Component → Parent Class/Interface
- Traverses delegation specifiers
- Extracts base class/interface names
- Creates `CallRelationship` for each

#### 2. Property Type Dependencies

**Detection**: Property declarations with explicit type annotations

```kotlin
class MyClass {
    val repository: UserRepository  // UserRepository is a type dependency
    val count: Int                  // Int is primitive, filtered out
}
```

**Relationship Type**: Class → Property Type

#### 3. Constructor Parameter Types

**Detection**: Class parameters in primary constructor

```kotlin
class UserService(
    private val repository: UserRepository  // type dependency
) { }
```

**Relationship Type**: Class → Parameter Type

#### 4. Method Call Dependencies

**Detection**: Function invocations via call expressions

```kotlin
val user = UserRepository()  // Call to UserRepository constructor
val name = repository.findUser()  // Call on repository
```

**Relationship Types**:
- Constructor invocations (capitalized identifiers)
- Method calls on objects (navigation expressions)
- Direct function calls

### Relationship Extraction Flow

The analyzer recursively traverses the AST to identify relationships:

- **class_declaration** nodes → Extract inheritance and interface implementations via `delegation_specifiers`
- **property_declaration** nodes → Extract property type dependencies
- **class_parameter** nodes → Extract constructor parameter type dependencies
- **call_expression** nodes → Extract method invocations and function calls

Each identified relationship is converted to a `CallRelationship` object and stored in the call_relationships list.

---

## Key Utility Methods

### Path & ID Resolution

#### `_get_module_path() -> str`
Converts file path to module path format using dot notation.

```
Example: 
  Input:  src/main/kotlin/com/example/User.kt
  Output: src/main/kotlin/com/example/User
```

#### `_get_relative_path() -> str`
Computes path relative to repository root.

#### `_get_component_id(name: str, parent_class: Optional[str]) -> str`
Generates unique component identifier in format: `{relative_path}::{component_name}`

```
Examples:
  - Class:   src/main/kotlin/User.kt::User
  - Method:  src/main/kotlin/User.kt::User.getName
```

### Type & Name Extraction

#### `_get_type_name(node) -> Optional[str]`
Extracts primary type name from type nodes, stripping generics and nullable wrappers.

```kotlin
// Extracts "List" from: List<String>
// Extracts "String" from: String?
// Extracts "UserRepository" from: UserRepository
```

#### `_get_identifier_name(node) -> str`
Gets the identifier text from an AST node.

#### `_get_class_modifiers(class_node) -> set`
Extracts modifier keywords (abstract, data, enum, annotation) from class declarations.

### Type Resolution

#### `_find_variable_type(node, variable_name, top_level_nodes) -> Optional[str]`
Attempts to resolve variable types by searching:

1. **Function Parameters**: Direct type annotation
2. **Local Variables**: Type annotations in function body
3. **Constructor Parameters**: Primary constructor parameters
4. **Class Properties**: Property declarations with type annotations
5. **Type Inference**: Infers type from initialization expressions

```kotlin
fun processUser(user: User) {      // param type from annotation
    val name = user.getName()       // resolved via param type
    val count: Int = 42             // explicit annotation
    val factory = UserFactory()     // inferred from constructor call
}
```

#### `_search_variable_declaration(block_node, variable_name) -> Optional[str]`
Recursively searches a code block for variable declarations with type information.

### Filtering & Validation

#### `_is_primitive_type(type_name: str) -> bool`
Filters out Kotlin primitive and standard library types to focus on user-defined types.

**Filtered Types Include**:
- Primitives: Boolean, Byte, Char, Double, Float, Int, Long, Short, String, Unit, Nothing, Any
- Collections: List, Set, Map, Collection, Iterable, Sequence, MutableList, MutableSet, MutableMap
- Arrays: Array, IntArray, LongArray, FloatArray, DoubleArray, etc.
- Pairs: Pair, Triple

#### `_find_containing_class_name(node) -> Optional[str]`
Walks up AST parent chain to find enclosing class/object/interface name.

#### `_find_containing_method(node) -> Optional[str]`
Walks up to enclosing function and returns its component ID.

#### `_get_root_identifier(nav_node) -> Node`
Extracts root identifier from navigation expression chains.

```kotlin
obj.service.repository.find()  // Extracts 'obj' as root
```

---

## Data Structures

### Node Structure
(Defined in [dependency_analyzer_models.md](dependency_analyzer_models.md))

Core component representation with metadata about location, type, and documentation.

### CallRelationship Structure
(Defined in [dependency_analyzer_models.md](dependency_analyzer_models.md))

Represents a directional relationship from a caller to a callee component.

```python
CallRelationship(
    caller: str,           # Calling component ID
    callee: str,           # Called component ID
    call_line: int,        # Line number of call
    is_resolved: bool      # Whether type is resolved
)
```

---

## Integration Points

### Upstream Dependencies

The analyzer depends on:

- **Tree-sitter Library**: Core parsing engine (`tree-sitter` package)
- **Kotlin Grammar**: Language definitions (`tree_sitter_kotlin` package)
- **Node Model**: Component representation structure
- **CallRelationship Model**: Relationship structure

### Downstream Usage

The analyzer output feeds into the broader dependency analysis pipeline:

```
TreeSitterKotlinAnalyzer
    ├─ Output: nodes (List[Node])
    └─ Output: call_relationships (List[CallRelationship])
        │
        ├─→ DependencyGraphBuilder (dependency_graph_construction)
        │   └─→ Builds Dependency Graph
        │
        └─→ AnalysisService (dependency_analysis_services)
            └─→ Produces Analysis Results
```

### Module Dependencies

| Module | Purpose | Integration |
|--------|---------|---|
| [language_analyzers](language_analyzers.md) | Sibling analyzers for other languages | Parallel implementation, shared interface pattern |
| [dependency_graph_construction](dependency_graph_construction.md) | Graph building from analyzer output | Consumes nodes and relationships |
| [dependency_analysis_services](dependency_analysis_services.md) | High-level analysis orchestration | Receives analyzed components |
| [dependency_analyzer_models](dependency_analyzer_models.md) | Data structure definitions | Uses Node, CallRelationship models |

---

## Analysis Capabilities

### What the Analyzer Discovers

#### Component Structure
- ✅ Classes, interfaces, objects, functions
- ✅ Class modifiers (abstract, data, enum, annotation)
- ✅ Method/function declarations
- ✅ Component metadata (location, docstrings, source code)

#### Dependencies
- ✅ Inheritance relationships
- ✅ Interface implementations
- ✅ Property type dependencies
- ✅ Constructor parameter types
- ✅ Method/function invocations
- ✅ Variable type resolution

#### Limitations
- ⚠️ Does not resolve external library types (filtered as unresolved)
- ⚠️ Type inference limited to explicit annotations and simple patterns
- ⚠️ Cannot trace complex generic type hierarchies
- ⚠️ Relies on local context for variable type resolution

---

## Data Flow Diagram

```
Input: Kotlin Source File
   ↓
TreeSitterKotlinAnalyzer.__init__(file_path, content, repo_path)
   ├─ Parsing Phase: _analyze()
   │  └─ Tree-sitter generates AST
   │
   ├─ Node Extraction: _extract_nodes()
   │  ├─ Identify components by type (class, function, etc.)
   │  └─ Create Node objects with metadata
   │     └─ Output: nodes: List[Node]
   │
   └─ Relationship Extraction: _extract_relationships()
      ├─ Identify dependencies (inheritance, calls, types)
      └─ Create CallRelationship objects
         └─ Output: call_relationships: List[CallRelationship]

Final Output:
   ├─ nodes: List[Node] → Dependency Graph Construction
   └─ call_relationships: List[CallRelationship] → Analysis Service
```

---

## Processing Example

### Input Kotlin Code

```kotlin
// User.kt
package com.example

interface UserRepository {
    fun findById(id: Int): User?
}

data class User(
    val id: Int,
    val name: String,
    val email: String
)

class UserService(
    private val repository: UserRepository
) {
    fun getUser(id: Int): User? {
        return repository.findById(id)
    }
    
    fun updateUser(user: User): Boolean {
        // implementation
        return true
    }
}
```

### Extracted Nodes

```
1. Node(
     name="User",
     component_type="interface",
     id="User.kt::User"
   )

2. Node(
     name="User",
     component_type="data class",
     id="User.kt::User"
   )

3. Node(
     name="UserService",
     component_type="class",
     id="User.kt::UserService"
   )

4. Node(
     name="UserService.getUser",
     component_type="method",
     id="User.kt::UserService.getUser"
   )

5. Node(
     name="UserService.updateUser",
     component_type="method",
     id="User.kt::UserService.updateUser"
   )
```

### Extracted Relationships

```
1. CallRelationship(
     caller="User.kt::UserService",
     callee="User.kt::UserRepository",
     call_line=11,
     is_resolved=False
   )
   → Constructor parameter type dependency

2. CallRelationship(
     caller="User.kt::UserService.getUser",
     callee="User.kt::UserRepository",
     call_line=15,
     is_resolved=False
   )
   → Method call on injected dependency

3. CallRelationship(
     caller="User.kt::UserService.updateUser",
     callee="User.kt::User",
     call_line=19,
     is_resolved=False
   )
   → Parameter type reference
```

---

## Usage Pattern

### Direct Usage

```python
from codewiki.src.be.dependency_analyzer.analyzers.kotlin import analyze_kotlin_file

# Analyze a single file
file_path = "src/main/kotlin/com/example/User.kt"
with open(file_path, 'r') as f:
    content = f.read()

nodes, relationships = analyze_kotlin_file(
    file_path=file_path,
    content=content,
    repo_path="/path/to/repo"
)

# Process results
for node in nodes:
    print(f"Found {node.component_type}: {node.name}")

for rel in relationships:
    print(f"{rel.caller} → {rel.callee}")
```

### Integration via AnalysisService

The analyzer is typically invoked through the broader analysis pipeline:

```python
from codewiki.src.be.dependency_analyzer.analysis.analysis_service import AnalysisService

service = AnalysisService(repo_path="/path/to/repo")
analysis_result = service.analyze_repository()
# Service internally delegates to appropriate language analyzers
```

---

## Configuration & Extensibility

### Language Support

The analyzer uses Tree-sitter with the Kotlin grammar. To use:

1. **Tree-sitter Library**: Must be installed (`pip install tree-sitter`)
2. **Kotlin Grammar**: Loaded from `tree_sitter_kotlin` package
3. **Parser Initialization**: Creates `Parser(Language(kotlin_language))`

### Adding New Kotlin Constructs

To track additional Kotlin constructs:

1. **Identify AST node type** for the construct using Tree-sitter documentation
2. **Add detection** in `_extract_nodes()` for the node type
3. **Create appropriate Node** with metadata
4. **For relationships**, add detection in `_extract_relationships()`

### Adding New Relationship Types

To detect new dependency patterns:

1. **Identify AST node pattern** for the dependency
2. **Add extraction logic** in `_extract_relationships()`
3. **Resolve types** using existing utility methods
4. **Filter primitives** with `_is_primitive_type()`
5. **Create CallRelationship** with caller/callee IDs

---

## Error Handling & Robustness

### Error Management Strategy

- **Parse Errors**: Caught in `_analyze()`, logged but don't crash
- **Missing Nodes**: Methods return `None` for optional constructs
- **Type Resolution Failures**: Gracefully continue, mark relationships as unresolved
- **Path Issues**: Falls back to absolute paths when relative paths fail

### Logging

Uses Python's standard logging module with logger name: `__name__` (typically "codewiki.src.be.dependency_analyzer.analyzers.kotlin")

---

## Performance Considerations

### Complexity Analysis

- **Parsing**: O(n) where n = file size
- **Node Extraction**: O(n) single pass through AST
- **Relationship Extraction**: O(n) recursive traversal
- **Type Resolution**: O(m) where m = scope depth (typically small)

### Memory Usage

- Stores all nodes in memory
- All relationships stored in memory
- Source code snippets included (not lazy-loaded)

### Optimization Opportunities

- ✅ Lazy loading of source code snippets
- ✅ Incremental analysis for large files
- ✅ Caching of type resolution results

---

## Testing Considerations

### Test Scenarios to Cover

1. **Component Extraction**
   - Regular classes, data classes, abstract classes
   - Objects, interfaces, annotations
   - Top-level and nested functions
   - Methods with various modifiers

2. **Relationship Detection**
   - Inheritance and interface implementation
   - Constructor parameter types
   - Property type annotations
   - Method calls (direct and chained)
   - Variable type resolution

3. **Edge Cases**
   - Generic types and wildcards
   - Nullable types
   - Nested classes
   - Anonymous objects and lambdas
   - Complex call chains

4. **Error Scenarios**
   - Malformed Kotlin code
   - Missing file paths
   - Empty files
   - Files with only comments

---

## Related Modules

- **[language_analyzers.md](language_analyzers.md)** - Overview of all language-specific analyzers
- **[dependency_analyzer_models.md](dependency_analyzer_models.md)** - Data structures (Node, CallRelationship)
- **[dependency_graph_construction.md](dependency_graph_construction.md)** - Graph building from analyzed components
- **[dependency_analysis_services.md](dependency_analysis_services.md)** - High-level analysis orchestration
- **[c_analyzer.md](c_analyzer.md)** - C language analyzer (similar pattern)
- **[java_analyzer.md](java_analyzer.md)** - Java language analyzer (similar JVM language)

---

## Summary

The **Kotlin Analyzer** module provides specialized AST parsing and semantic analysis for Kotlin source code. It identifies components and their relationships through pattern-based detection, enabling comprehensive dependency graph construction. Its modular design allows reuse across the analysis pipeline and easy extension for new Kotlin constructs.

**Key Strengths**:
- ✅ Accurate AST-based analysis
- ✅ Multi-faceted relationship detection
- ✅ Type inference and resolution
- ✅ Comprehensive component classification

**Integration Role**:
- Feeds component and relationship data to dependency graph construction
- Part of the larger language analyzer family
- Enables cross-module dependency analysis for Kotlin projects
