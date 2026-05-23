# TypeScript Analyzer Module Documentation

## Overview

The **TypeScript Analyzer** is a specialized language analyzer component that extracts code entities and their relationships from TypeScript/JavaScript files using the tree-sitter parsing library. It's part of the CodeWiki dependency analysis system and enables accurate AST-based code understanding for TypeScript projects.

### Purpose
- Parse TypeScript/JavaScript files and extract code structure (classes, functions, interfaces, types, etc.)
- Build a dependency graph by identifying relationships between code entities
- Support both type-based and runtime-based dependency analysis
- Enable accurate documentation generation for TypeScript codebases

### Key Features
- **Tree-sitter based parsing** for accurate AST analysis
- **Multi-entity extraction**: functions, classes, interfaces, types, enums, variables
- **Relationship detection**: method calls, constructor dependencies, type annotations, inheritance
- **Scope-aware analysis**: distinguishes top-level vs nested declarations
- **Export tracking**: identifies and analyzes exported entities
- **Type system support**: analyzes TypeScript-specific features (interfaces, type aliases, generics)

---

## Architecture

### Component Structure

```
TypeScript Analyzer Module
│
├── Core Parser
│   ├── TreeSitterTSAnalyzer (Main Analyzer Class)
│   └── Tree-sitter Parser Instance
│
├── Entity Extraction System
│   ├── Function/Method Extractors
│   ├── Class/Interface Extractors
│   ├── Type Definition Extractors
│   └── Variable Declaration Extractors
│
├── Relationship Analysis
│   ├── Call Expression Analyzer
│   ├── Type Relationship Detector
│   ├── Inheritance Chain Analyzer
│   └── Dependency Resolver
│
└── Output Generation
    ├── Node Factory (creates Node objects)
    └── Relationship Factory (creates CallRelationship objects)
```

### Core Classes

#### **TreeSitterTSAnalyzer**
The primary analyzer class that orchestrates TypeScript file analysis.

**Responsibilities:**
- Initialize the tree-sitter parser for TypeScript
- Parse TypeScript source code into an AST
- Extract all code entities from the AST
- Identify and catalog relationships between entities
- Generate output Node and CallRelationship objects

**State Management:**
```
TreeSitterTSAnalyzer Instance
├── file_path: Path              # Source file location
├── content: str                 # Source code content
├── repo_path: str               # Repository root path
├── parser: Parser               # Tree-sitter parser instance
├── ts_language: Language        # TypeScript language definition
├── nodes: List[Node]            # Extracted top-level code entities
├── call_relationships: List[CallRelationship]  # Extracted dependencies
└── top_level_nodes: Dict        # Cache of top-level entities
```

---

## Data Flow

### Typical Analysis Pipeline

```
TypeScript Source File
        │
        ▼
[TreeSitterTSAnalyzer.__init__]
        │
        ├─► Initialize tree-sitter Parser
        ├─► Load TypeScript Language Spec
        └─► Store file metadata
        │
        ▼
[analyze() method]
        │
        ├─► Parse source code to AST
        │
        ▼
[_extract_all_entities]
        │
        ├─► Recursively traverse AST
        ├─► Identify node types
        ├─► Extract entity metadata
        └─► Build entity dictionary
        │
        ▼
[_filter_top_level_declarations]
        │
        ├─► Validate scope (top-level only)
        ├─► Create Node objects
        ├─► Store in nodes list
        └─► Cache for relationship resolution
        │
        ▼
[_extract_all_relationships]
        │
        ├─► Traverse AST for relationships
        ├─► Match calls to entities
        ├─► Identify type dependencies
        ├─► Track inheritance chains
        └─► Create CallRelationship objects
        │
        ▼
Output
├── nodes: Extracted code entities
└── call_relationships: Dependency connections
```

---

## Key Components & Methods

### 1. Initialization & Parsing

#### `__init__(file_path, content, repo_path)`
Initializes the analyzer with a TypeScript file.

**Process:**
1. Store file metadata and content
2. Load tree-sitter TypeScript language definition
3. Create Parser instance
4. Initialize data structures

**Error Handling:** Falls back gracefully if parser initialization fails

#### `analyze()`
Main entry point that orchestrates the entire analysis process.

**Sequence:**
1. Verify parser is initialized
2. Parse source code to AST
3. Extract all entities recursively
4. Filter to top-level declarations only
5. Extract relationships between entities

---

### 2. Entity Extraction

The extraction system identifies different code constructs and creates structured entity objects.

#### Entity Types Supported

| Entity Type | Methods | Notes |
|-------------|---------|-------|
| **Functions** | `_extract_function_entity()` | Regular, async, generator functions |
| **Arrow Functions** | `_extract_arrow_function_entity()` | Variable-bound arrow functions |
| **Methods** | `_extract_method_entity()` | Class methods, static methods |
| **Classes** | `_extract_class_entity()` | Regular and abstract classes |
| **Interfaces** | `_extract_interface_entity()` | TypeScript interfaces |
| **Type Aliases** | `_extract_type_alias_entity()` | `type` declarations |
| **Enums** | `_extract_enum_entity()` | Enum declarations |
| **Variables** | `_extract_variable_entity()` | Const, let, var declarations |
| **Exports** | `_extract_export_statement_entity()` | Re-exports, default exports |

#### `_extract_all_entities(node, all_entities, depth)`
Recursively traverses the AST and extracts all entities.

**Algorithm:**
```
For each AST node:
  1. Check node type against known entity types
  2. If match found:
     - Call appropriate extractor method
     - Store entity in dictionary
     - Record depth for scope validation
     - Preserve parent context
  3. Recursively process child nodes
```

**Entity Dictionary Structure:**
```python
entity = {
    'name': str,                      # Entity identifier
    'type': str,                      # Primary type (function, class, etc.)
    'subtype': str,                   # Specific variant
    'code_snippet': str,              # Source code text
    'display_name': str,              # Human-readable name
    'start_line': int,                # Start line number
    'end_line': int,                  # End line number
    'depth': int,                     # AST depth (for scope validation)
    'node': TreeSitterNode,           # AST node reference
    'parent_context': str,            # Parent scope context
    'parameters': List[str],          # (for callables)
    'base_classes': List[str],        # (for classes/interfaces)
    'is_async': bool,                 # (for functions)
    'is_static': bool,                # (for methods)
    'has_function': bool              # (for variables)
}
```

#### `_filter_top_level_declarations(all_entities)`
Filters extracted entities to include only top-level declarations.

**Filtering Logic:**
```
For each extracted entity:
  1. Check if actually at top-level scope
  2. Validate not nested inside functions
  3. Ensure parent is program/export/ambient/module
  4. Create Node object if passes validation
  5. Store in nodes list and top_level_nodes cache
  6. Extract constructor dependencies for classes
```

#### `_is_actually_top_level(entity_data)`
Determines if an entity is truly at the top scope level.

**Validation Steps:**
1. Get AST node reference
2. Check for parent existence
3. Validate not inside function body
4. Traverse parent chain to verify top-level context
5. Accept if parent is program, export, ambient, or module

---

### 3. Scope & Context Analysis

#### `_is_inside_function_body(node)`
Determines if a node is nested inside a function.

**Logic:**
- Traverse parent chain upward
- Look for statement_block with function parent
- Return true if found, false otherwise

#### `_get_parent_context(node)`
Extracts parent scope context for entity.

**Returns:**
- `"program"` - Top-level program
- `"export"` - Export statement
- `"ambient"` - Ambient declaration
- `"module"` - Module/namespace
- `"module_block"` - Inside module block
- `"statement_block"` - Inside statement block
- `"root"` - No parent

---

### 4. Relationship Extraction

The relationship analysis system identifies dependencies between code entities.

#### `_extract_all_relationships(node, all_entities)`
Main relationship extraction orchestrator.

**Process:**
1. Traverse entire AST tree
2. Track current top-level entity context
3. For each relationship pattern found, extract and store

#### `_traverse_for_relationships(node, all_entities, current_top_level)`
Recursive traversal that identifies relationship patterns.

**Relationship Patterns Detected:**

| Pattern | Method | Description |
|---------|--------|-------------|
| **Function Calls** | `_extract_call_relationship()` | Direct function/method calls |
| **Constructor Calls** | `_extract_new_relationship()` | `new ClassName()` expressions |
| **Member Access** | `_extract_member_relationship()` | Property/field access |
| **Type Annotations** | `_extract_type_relationship()` | `: Type` dependencies |
| **Generic Types** | `_extract_type_arguments_relationship()` | `Type<Dependency>` |
| **Inheritance** | `_extract_inheritance_relationship()` | `extends`/`implements` |

#### Call Relationship Extraction

##### `_extract_call_relationship(node, caller_name, all_entities)`
Identifies and records function/method calls.

**Logic:**
```
For each call_expression node:
  1. Extract callee name
  2. Check if builtin (skip if true)
  3. Check if method call (this. / super.)
  4. Verify callee exists in top-level nodes or entities
  5. Create CallRelationship object
  6. Add to relationships list
```

**Method Call Handling:**
- Skips internal method-to-method calls
- Tracks cross-entity calls
- Preserves context information

##### `_extract_new_relationship(node, caller_name, all_entities)`
Tracks constructor usage (dependency injection).

**Logic:**
```
For each new_expression:
  1. Extract constructor name
  2. Skip builtins
  3. Add relationship
```

##### `_extract_parameter_dependencies(formal_params, caller_name)`
Extracts dependencies from constructor parameters.

**Process:**
- Analyzes formal parameters
- Extracts type annotations
- Identifies type-based dependencies
- Creates relationships from parameter types to class

#### Type Relationship Extraction

##### `_extract_type_relationship(node, caller_name, all_entities)`
Identifies type-based dependencies.

**Algorithm:**
```
For each type_annotation:
  1. Find all type identifiers
  2. Filter builtin types
  3. Resolve to top-level entities
  4. Create relationships
```

##### `_extract_inheritance_relationship(node, caller_name, all_entities)`
Tracks inheritance and implementation chains.

**Logic:**
```
For extends_clause and implements_clause:
  1. Extract base type names
  2. Verify they exist in entities
  3. Create inheritance relationships
```

---

### 5. Node Creation

#### `_create_node_from_entity(entity_data)`
Factory method that converts entity data to Node objects.

**Output Structure:**
```python
Node(
    id=component_id,                  # Unique identifier
    name=name,                        # Entity name
    component_type=type,              # class, function, interface, etc.
    file_path=str(file_path),        # Absolute file path
    relative_path=relative_path,      # Relative to repo root
    source_code=snippet,              # Source code text
    start_line=line,                  # Starting line number
    end_line=line,                    # Ending line number
    has_docstring=False,              # Documentation presence
    docstring="",                     # Documentation text
    parameters=params,                # Parameter list
    node_type=node_type,              # Specific node type
    base_classes=bases,               # Inherited types
    display_name=name,                # Human-readable display
    component_id=id                   # Component identifier
)
```

#### `_should_include_node(node)`
Filters nodes that shouldn't be included in output.

**Exclusions:**
- Variables (except those with functions)
- Internal/special names (constructor, __proto__, prototype)

---

### 6. Helper Utilities

#### AST Navigation
- **`_find_child_by_type(node, type)`** - Locate first matching child
- **`_get_node_text(node)`** - Extract text content from node

#### Identifier Resolution
- **`_extract_callee_name(call_node)`** - Extract function being called
- **`_get_top_level_name(node)`** - Get entity name from declaration

#### Path Management
- **`_get_relative_path()`** - Path relative to repo root
- **`_get_module_path()`** - Module identifier path
- **`_get_component_id(name)`** - Generate component identifier

#### Type & Scope Validation
- **`_is_builtin_type(name)`** - Check if TypeScript builtin type
- **`_is_builtin_function(name)`** - Check if JavaScript builtin
- **`_resolve_to_top_level(entity_name, all_entities)`** - Map to top-level entity

#### Extraction Helpers
- **`_extract_parameters(node)`** - Parse function parameters
- **`_extract_inheritance(node)`** - Get base classes/interfaces
- **`_find_all_type_identifiers(node, list)`** - Recursively find type refs

---

## Integration with Other Modules

### Data Model Dependencies

The analyzer creates objects from [dependency_analyzer_models](dependency_analyzer_models.md):

**Inputs from:**
- `codewiki/src/be/dependency_analyzer/models/core.py`
  - `Node` - Represents a code entity
  - `CallRelationship` - Represents a dependency link

### System Integration

```
┌─────────────────────────────────────────┐
│   RepoAnalyzer (dependency_analysis)    │
│   (coordinates all language analyzers)  │
└──────────────┬──────────────────────────┘
               │
        ┌──────┴──────────────────┐
        │                         │
        ▼                         ▼
   PythonAnalyzer      TreeSitterTSAnalyzer
   (python.py)         (typescript.py) ◄─── Current Module
        │                         │
        ├────────────┬────────────┤
        │            │            │
        ▼            ▼            ▼
   [Plus other language analyzers...]
        │
        ▼
┌─────────────────────────────────────┐
│  DependencyGraphBuilder             │
│  Combines all analyzer outputs      │
└──────────────┬──────────────────────┘
               │
        ┌──────┴──────────────┐
        │                     │
        ▼                     ▼
   Call Graph          Repository Model
   (Analysis)          (Complete graph)
```

### Consumer Relationships

The analyzer output is consumed by:

1. **[DependencyGraphBuilder](dependency_graph_construction.md)**
   - Receives Node and CallRelationship objects
   - Merges with other language analyzers
   - Builds unified dependency graph

2. **[DocumentationGenerator](documentation_generation.md)**
   - Uses nodes to document entities
   - Uses relationships for structure
   - Creates comprehensive documentation

3. **[AnalysisService](dependency_analysis_services.md)**
   - Orchestrates overall analysis
   - Coordinates multiple language analyzers
   - Manages analysis pipeline

---

## Supported Language Features

### TypeScript-Specific Support

| Feature | Support | Extraction Method |
|---------|---------|-------------------|
| **Interface** | ✓ Full | `_extract_interface_entity()` |
| **Type Alias** | ✓ Full | `_extract_type_alias_entity()` |
| **Enum** | ✓ Full | `_extract_enum_entity()` |
| **Generic Types** | ✓ Partial | `_extract_type_arguments_relationship()` |
| **Union Types** | ✓ Partial | Type annotation tracking |
| **Decorators** | ✗ Not extracted | - |
| **Namespaces** | ✓ Partial | Ambient declaration handling |
| **Ambient Declarations** | ✓ Full | `_extract_ambient_declaration_entity()` |
| **Module Re-exports** | ✓ Full | Export statement handling |

### JavaScript Support

The analyzer also supports modern JavaScript:
- ES6+ modules (import/export)
- Arrow functions
- Class declarations
- Template literals
- Destructuring (in parameters)

### Modifiers & Keywords

**Function/Method Modifiers:**
- `async` - Asynchronous functions
- `static` - Static methods
- `generator` - Generator functions

**Class/Interface Modifiers:**
- `abstract` - Abstract classes
- `readonly` - Read-only properties
- Export visibility

---

## Error Handling & Robustness

### Parser Initialization

```python
try:
    language_capsule = tree_sitter_typescript.language_typescript()
    self.ts_language = Language(language_capsule)
    self.parser = Parser(self.ts_language)
except Exception as e:
    logger.error(f"Failed to initialize TypeScript parser: {e}")
    self.parser = None  # Graceful degradation
```

### Analysis Resilience

- **Skip on parser failure** - Returns empty results if parser unavailable
- **Per-entity error handling** - Individual extraction errors don't crash analysis
- **Logging** - Detailed debug logging for troubleshooting
- **Validation** - Multiple checks before creating nodes

### Known Limitations

1. **Decorator Support** - Decorators are not extracted as entities
2. **Dynamic Imports** - `import()` calls may not be fully resolved
3. **Complex Generics** - Deeply nested generic types may be simplified
4. **Circular Dependencies** - Detected but not specially handled
5. **Implicit Dependencies** - Implicit type inference not tracked

---

## Usage Example

### Basic Analysis

```python
from codewiki.src.be.dependency_analyzer.analyzers.typescript import (
    TreeSitterTSAnalyzer,
    analyze_typescript_file_treesitter
)

# Method 1: Direct class usage
analyzer = TreeSitterTSAnalyzer(
    file_path="src/app.ts",
    content=source_code,
    repo_path="/path/to/repo"
)
analyzer.analyze()

nodes = analyzer.nodes
relationships = analyzer.call_relationships

# Method 2: Using convenience function
nodes, relationships = analyze_typescript_file_treesitter(
    file_path="src/app.ts",
    content=source_code,
    repo_path="/path/to/repo"
)
```

### Output Interpretation

```python
# Each node represents a code entity
node = nodes[0]
print(f"Entity: {node.name}")
print(f"Type: {node.component_type}")
print(f"Location: {node.file_path}:{node.start_line}")
print(f"Code: {node.source_code[:100]}...")

# Each relationship represents a dependency
rel = relationships[0]
print(f"Caller: {rel.caller}")
print(f"Callee: {rel.callee}")
print(f"Call Line: {rel.call_line}")
```

---

## Performance Characteristics

### Time Complexity

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| Parsing | O(n) | Tree-sitter parsing is linear in source size |
| Entity extraction | O(n) | Single tree traversal |
| Relationship extraction | O(n·m) | Traversal × entity lookups |
| Node filtering | O(k) | k = number of extracted entities |

### Space Complexity

| Data Structure | Space | Notes |
|---|---|---|
| AST | O(n) | Proportional to source code size |
| Entities dict | O(k) | k = number of entities found |
| Nodes list | O(t) | t = top-level entities only |
| Relationships list | O(r) | r = number of relationships |

**Total**: Approximately O(n + r) where n is source size and r is relationship count

### Typical Metrics

- **Parse Time**: 5-50ms per file (depends on file size)
- **Analysis Time**: 10-100ms per file
- **Memory per File**: 1-10 MB

---

## Architecture Diagrams

### Entity Extraction Process

```
TypeScript Source
       |
       v
   [Parse to AST]
       |
       v
[_extract_all_entities]
Recursively traverse AST nodes
Extract: functions, classes, interfaces,
         types, enums, variables
       |
       v
[Entity Dictionary]
     stored
       |
       v
[_filter_top_level_declarations]
Check: parent context, scope depth,
       nesting level
       |
    ---|---
   |       |
   v       v
 Valid   Invalid
   |       |
   v       v
Create   Discard
 Node
   |
   v
[Output Nodes]
```

### Relationship Analysis Flow

```
[Extracted Nodes]
       |
       v
[AST Traversal]
For each node, identify pattern:
       |
  |----|----|----|-------|
  |    |    |    |       |
  v    v    v    v       v
Call  New  Type Inheritance Member
Expr  Expr Anno   Chain     Access
  |    |    |    |         |
  |____|____|____|_________|
            |
            v
    [Create Relationships]
            |
            v
    [Output Relationships]
```

### Top-Level Validation Decision

```
[Check Entity]
   |
   v
Does parent exist?
   |-----> No  -----> [INCLUDE]
   |
   v
Is parent program/export/ambient/module?
   |-----> Yes -----> [INCLUDE]
   |
   v
Is inside function body?
   |-----> Yes -----> [EXCLUDE]
   |
   v
Found program/module in parent chain?
   |-----> Yes -----> [INCLUDE]
   |
   v
[EXCLUDE]
```

### Module Integration Flow

```
TS/JS Files
   |
   v
[TreeSitterTSAnalyzer]
   |
   |-----> Node Extraction
   |-----> Relationship Detection
   |
   v
[Output: Nodes + Relationships]
   |
   |-----> DependencyGraphBuilder
   |-----> AnalysisService
   |-----> DocumentationGenerator
   |
   v
[Complete Analysis]
```

---

## Configuration & Dependencies

### External Dependencies

- **tree-sitter**: AST parsing framework
- **tree_sitter_typescript**: TypeScript language binding
- **Python built-ins**: logging, pathlib, typing

### Configuration

The analyzer uses standard Python logging:

```python
logger = logging.getLogger(__name__)
```

Debug logging is enabled to track analysis progress and issues.

---

## Testing Considerations

### Key Test Cases

1. **Basic Entity Extraction**
   - Simple function declarations
   - Class definitions
   - Interface declarations
   - Variable declarations

2. **Complex Entities**
   - Async/generator functions
   - Abstract classes
   - Generic types
   - Decorator patterns

3. **Relationship Detection**
   - Function calls
   - Constructor usage
   - Type annotations
   - Inheritance chains

4. **Scope Validation**
   - Top-level vs nested detection
   - Export handling
   - Module/namespace context

5. **Edge Cases**
   - Empty files
   - Malformed syntax
   - Missing type information
   - Circular dependencies

---

## Future Enhancements

### Potential Improvements

1. **Decorator Support** - Extract and track decorator usage
2. **Template Literal Types** - Support for template literal type extraction
3. **Advanced Generics** - Better handling of complex generic constraints
4. **JSDoc Comments** - Extract and link JSDoc documentation
5. **Import Tracking** - Detailed import/export relationship analysis
6. **Performance** - Incremental analysis for large codebases

---

## References

- **Core Models**: [dependency_analyzer_models.md](dependency_analyzer_models.md)
- **Analysis Services**: [dependency_analysis_services.md](dependency_analysis_services.md)
- **Graph Construction**: [dependency_graph_construction.md](dependency_graph_construction.md)
- **Related Analyzers**: [language_analyzers.md](language_analyzers.md)
- **Tree-sitter Documentation**: https://tree-sitter.github.io/
