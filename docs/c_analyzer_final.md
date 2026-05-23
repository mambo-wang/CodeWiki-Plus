# C Analyzer Module Documentation

## Overview

The **c_analyzer** module is a specialized code analysis component for C language files within the CodeWiki dependency analysis system. It uses Tree-Sitter, a general-purpose incremental parsing library, to parse and extract structural information from C source code, including function definitions, struct declarations, global variables, and their relationships.

### Purpose

- **Parse C Code**: Uses Tree-Sitter to efficiently parse C syntax and build abstract syntax trees (ASTs)
- **Extract Constructs**: Identifies top-level C language constructs (functions, structs, global variables)
- **Build Dependency Graph**: Extracts relationships between identified constructs (function calls, variable usage)
- **Enable Documentation**: Provides the foundation for automated documentation generation by making code structure machine-readable

### Key Capabilities

- Recursive AST traversal for comprehensive node extraction
- Multi-type relationship detection (function calls, variable access)
- System function filtering to exclude standard library calls
- Cross-file relationship support for call graph construction
- Component ID generation for unique node identification

---

## Architecture

### System Integration

**High-Level Architecture**:

```
CLI Layer (CLIDocumentationGenerator)
    ↓
Backend Services (DocumentationGenerator)
    ↓
AnalysisService (Orchestrator)
    ↓
Language Analyzers
    ├─ TreeSitterCAnalyzer (c_analyzer)
    ├─ TreeSitterCppAnalyzer (cpp_analyzer)
    └─ Other Language Analyzers
    ↓
Produces: Node objects and CallRelationship objects
    ↓
Dependency Analysis Services
    ├─ RepoAnalyzer (Coordinates repository-wide analysis)
    └─ CallGraphAnalyzer (Resolves relationships)
```

**Module Dependencies**:
- Consumes from: `AnalysisService`
- Produces: `Node` and `CallRelationship` objects (from models/core.py)
- Feeds to: `CallGraphAnalyzer` for relationship resolution
- Coordinates by: `RepoAnalyzer` for repository-wide analysis

---

## Component Architecture

### TreeSitterCAnalyzer

The core component of the c_analyzer module, responsible for parsing individual C files and extracting their structural information.

**Processing Pipeline**:

```
Input Files
    │
    ├─ File Path
    ├─ File Content (string)
    └─ Repository Path (context)
    │
    ↓
TreeSitterCAnalyzer.__init__()
    │
    ├─ Store metadata (path, content, repo context)
    ├─ Initialize nodes list []
    ├─ Initialize relationships list []
    └─ Call _analyze()
    │
    ↓
_analyze() Method
    │
    ├─ Create Tree-Sitter parser (C language)
    ├─ Parse file content → AST (Abstract Syntax Tree)
    └─ Call _extract_nodes() and _extract_relationships()
    │
    ↓
Output
    ├─ List[Node] - extracted constructs
    └─ List[CallRelationship] - dependencies
```

---

## Component Details

### TreeSitterCAnalyzer Class

**Location**: `codewiki/src/be/dependency_analyzer/analyzers/c.py`

#### Constructor

```python
def __init__(self, file_path: str, content: str, repo_path: str = None)
```

**Parameters**:
- `file_path` (str): Absolute or relative path to the C source file
- `content` (str): Complete file content as a string
- `repo_path` (str, optional): Root path of the repository for relative path calculation

**Initialization Flow**:
1. Stores file metadata (path, content, repo context)
2. Initializes empty lists for nodes and relationships
3. Triggers `_analyze()` to process the file

#### Key Methods

##### `_analyze()`
Main orchestration method that:
1. Creates Tree-Sitter parser with C language configuration
2. Parses file content into AST
3. Calls `_extract_nodes()` for initial node discovery
4. Calls `_extract_relationships()` to establish dependencies

##### `_extract_nodes(node, top_level_nodes, lines)`

**Recursion-based AST traversal** that identifies top-level C constructs:

| Node Type | Extracted As | Example |
|-----------|--------------|---------|
| `function_definition` | "function" | `int parse_expr()` |
| `struct_specifier` | "struct" | `struct Point { ... }` |
| `type_definition` | "struct" (typedef) | `typedef struct { ... } Point;` |
| `declaration` (global scope) | "variable" | `int global_var = 0;` |

**Process**:
1. Recursively traverse AST from root
2. Match node type patterns
3. Extract name, line numbers, source code
4. Create `Node` objects for functions and structs
5. Maintain `top_level_nodes` dict for fast lookup
6. Store variables for relationship analysis

**Node Type Matching**:
```
function_definition
├─ function_declarator (contains function name)
│  └─ identifier (the function name)
└─ (function body)

struct_specifier
├─ type_identifier (struct name)
└─ (struct body)

type_definition (typedef struct)
├─ struct_specifier
└─ type_identifier (typedef name)

declaration (global variable)
└─ init_declarator or identifier
   └─ identifier (variable name)
```

**Filtering**:
- Only functions and structs added to `self.nodes`
- Variables tracked internally for relationship analysis

##### `_extract_relationships(node, top_level_nodes)`

**Recursive relationship discovery** that identifies:

1. **Function Calls** (unresolved, cross-file):
   - Pattern: `call_expression` nodes
   - Process: Extract function name → Filter system functions → Create CallRelationship
   - Example: `parse_statement()` call creates relationship

2. **Global Variable Access** (resolved, local file):
   - Pattern: `identifier` nodes referencing global variables
   - Process: Check if identifier is in `top_level_nodes` → Create resolved CallRelationship
   - Example: `global_config` access creates relationship

**System Functions Excluded**:
- I/O: `printf`, `scanf`, `fopen`, `fclose`, `fread`, `fwrite`
- Memory: `malloc`, `free`, `memcpy`, `memset`
- String: `strlen`, `strcpy`, `strcmp`
- Process: `exit`, `abort`
- Graphics (SDL): `SDL_Init`, `SDL_CreateWindow`, etc.

**Resolution Status**:
- **Resolved** (`is_resolved=True`): Local file relationships
- **Unresolved** (`is_resolved=False`): Cross-file functions (resolved later by CallGraphAnalyzer)

##### `_find_containing_function(node, top_level_nodes)`

Walks up the AST parent chain to find the enclosing `function_definition` node.

##### Helper Methods

**`_get_module_path()`**: 
- Converts absolute paths to repository-relative
- Removes file extensions (.c, .h)
- Converts path separators to dots
- Example: `src/utils/helpers.c` → `src.utils.helpers`

**`_get_relative_path()`**: 
- Gets repository-relative file path
- Handles ValueError for paths outside repo

**`_get_component_id(name)`**: 
- Generates unique component identifier
- Format: `relative/path/to/file.c::component_name`
- Example: `src/parser.c::parse_expression`

**`_is_global_variable(node)`**: 
- Checks if declaration is at file scope
- Walks parent chain up AST
- Returns false if inside function or struct
- Returns true if reaches file root

**`_is_system_function(func_name)`**: 
- Classifies function as system/library
- Uses hardcoded list of common C functions

---

## Data Models

### Node Class
**Source**: `codewiki/src/be/dependency_analyzer/models/core.py`

Represents a single code construct extracted from C source.

**Fields**:
- `id`: Unique identifier (e.g., `src/parser.c::parse_expression`)
- `name`: Simple component name (e.g., `parse_expression`)
- `component_type`: Type classification (`function`, `struct`, `variable`)
- `file_path`: Absolute file path
- `relative_path`: Repository-relative path
- `source_code`: Extracted source code snippet
- `start_line` / `end_line`: 1-indexed line numbers
- `has_docstring`: Always `False` for C (no docstrings)
- `docstring`: Empty for C
- `parameters`: `None` for C (not extracted)
- `node_type`: Same as `component_type`
- `base_classes`: `None` for C (no inheritance)
- `class_name`: `None` for C
- `display_name`: Human-readable name (e.g., `function parse_expression`)
- `component_id`: Duplicate of `id`

**Example Node for C function**:
```python
Node(
    id="src/parser.c::parse_expression",
    name="parse_expression",
    component_type="function",
    file_path="/home/user/project/src/parser.c",
    relative_path="src/parser.c",
    source_code="int parse_expression(...) {\n  ...\n}",
    start_line=42,
    end_line=156,
    has_docstring=False,
    docstring="",
    node_type="function",
    display_name="function parse_expression"
)
```

### CallRelationship Class
**Source**: `codewiki/src/be/dependency_analyzer/models/core.py`

Represents a dependency between two code constructs.

**Fields**:
- `caller`: Component ID of calling entity (fully qualified)
- `callee`: Component ID or simple name of called entity
- `call_line`: Line number where dependency occurs
- `is_resolved`: Whether callee is a fully qualified ID

**Examples**:

Unresolved function call:
```python
CallRelationship(
    caller="src/parser.c::parse_expression",
    callee="parse_statement",  # Simple name
    call_line=87,
    is_resolved=False  # Resolved later by CallGraphAnalyzer
)
```

Resolved global variable usage:
```python
CallRelationship(
    caller="src/parser.c::parse_expression",
    callee="src/parser.c::global_config",  # Fully qualified
    call_line=95,
    is_resolved=True  # Local file relationship
)
```

---

## Analysis Process

### Phase 1: Node Extraction

**Goal**: Identify all top-level C constructs

**Process**:
1. Recursively traverse AST from root node
2. For each node, check `node.type` against known patterns
3. Extract node name and metadata
4. Build `Node` object with complete information
5. Add to `self.nodes` if it's a function or struct
6. Store all types in `top_level_nodes` dict for relationship analysis

**Constructs Identified**:
- Functions: All `function_definition` nodes at file scope
- Structs: All `struct_specifier` and typedef'd structs
- Variables: Global `declaration` nodes (for relationship tracking)

### Phase 2: Relationship Extraction

**Goal**: Identify dependencies between extracted nodes

**Process**:
1. Recursively traverse AST again
2. Identify relationship patterns:
   - Function calls: `call_expression` nodes
   - Variable access: `identifier` nodes in function scope
3. For each relationship:
   - Find containing function
   - Check if target is system function (filter if yes)
   - Determine resolution status (local vs cross-file)
   - Create `CallRelationship` object
4. Add to `self.call_relationships`

**Resolution Determination**:
- **Resolved**: Target found in `top_level_nodes` (same file)
- **Unresolved**: Target is simple function name (need cross-file resolution)

---

## Integration Points

### With AnalysisService
**Module**: `dependency_analyzer/analysis/analysis_service.py`

The AnalysisService:
1. Detects C files (.c, .h extensions)
2. Instantiates TreeSitterCAnalyzer with file content
3. Collects `nodes` and `call_relationships` from analyzer
4. Aggregates results from all language analyzers

### With CallGraphAnalyzer
**Module**: `dependency_analyzer/analysis/call_graph_analyzer.py`

Processes extracted relationships:
1. Takes all unresolved CallRelationships
2. Matches callee names to actual Node IDs
3. Resolves cross-file and cross-module dependencies
4. Builds complete call graphs

### With RepoAnalyzer
**Module**: `dependency_analyzer/analysis/repo_analyzer.py`

Orchestrates file-level analysis:
1. Discovers all C files in repository
2. Reads file contents
3. Instantiates TreeSitterCAnalyzer for each file
4. Aggregates results into repository-wide analysis

---

## Limitations & Considerations

### C Language Features Not Supported

1. **Macro Analysis**: 
   - Preprocessor directives (#define, #include) not analyzed
   - No macro expansion or dependency tracking

2. **Type Inference**: 
   - Parameter and return types not extracted
   - Function signatures available via source code only

3. **Struct/Union Members**: 
   - Internal structure not decomposed
   - Members not extracted as separate nodes

4. **Pointer Resolution**: 
   - Function pointers not tracked
   - Indirect calls not identified

5. **Inline Assembly**: 
   - ASM blocks ignored
   - Low-level dependencies not visible

### Current Extraction Scope

**Extracted** ✅:
- Top-level function definitions
- Struct/union definitions
- Global variable declarations
- Function-to-function calls
- Global variable usage

**Not Extracted** ❌:
- Local variables
- Function parameters
- Return types
- Type information
- Macro definitions
- Typedef names (except for struct typedefs)
- Function pointers
- Nested functions

### Filtering & Accuracy Issues

1. **System Function List**:
   - Hardcoded list may be incomplete
   - New library functions not automatically filtered

2. **Global Variable Detection**:
   - Based on scope analysis
   - May miss function-local static variables

3. **Cross-File References**:
   - Depend on CallGraphAnalyzer resolution
   - Unmatched calls create incomplete graphs

---

## Example Walkthrough

### Input C File

**File**: `src/calculator.c`

```c
#include <stdio.h>

int result = 0;

int add(int a, int b) {
    result = a + b;
    return result;
}

void print_result() {
    printf("Result: %d\n", result);
}

int main() {
    int sum = add(5, 3);
    print_result();
    return 0;
}
```

### Analysis Output

**Nodes Extracted** (3 functions):

| Component ID | Name | Type | Line Range |
|--------------|------|------|------------|
| `src/calculator.c::add` | add | function | 5-8 |
| `src/calculator.c::print_result` | print_result | function | 10-12 |
| `src/calculator.c::main` | main | function | 14-18 |

**Relationships Extracted**:

| Caller | Callee | Line | Resolved |
|--------|--------|------|----------|
| `src/calculator.c::add` | `src/calculator.c::result` | 7 | ✓ Yes |
| `src/calculator.c::main` | `add` | 16 | ✗ No |
| `src/calculator.c::main` | `print_result` | 17 | ✗ No |
| `src/calculator.c::print_result` | `printf` | 11 | **Filtered** |

**Notes**:
- `printf` excluded (system function filter)
- `result` reference resolved immediately (same file)
- Function calls unresolved (will be resolved by CallGraphAnalyzer)

---

## Related Modules

- **[language_analyzers](language_analyzers.md)**: Parent module containing all language-specific analyzers
- **[cpp_analyzer](cpp_analyzer.md)**: Similar C++ analyzer following same patterns
- **[dependency_analysis_services](dependency_analysis_services.md)**: Services that coordinate analyzer usage
- **[call_graph_analyzer](call_graph_analyzer.md)**: Processes and resolves call relationships
- **[dependency_analyzer_models](dependency_analyzer_models.md)**: Data models (Node, CallRelationship, AnalysisResult)

---

## Usage Guide

### Basic File Analysis

```python
from codewiki.src.be.dependency_analyzer.analyzers.c import TreeSitterCAnalyzer

# Read C file
with open("src/parser.c", "r") as f:
    content = f.read()

# Create analyzer
analyzer = TreeSitterCAnalyzer(
    file_path="src/parser.c",
    content=content,
    repo_path="/home/user/project"
)

# Access results
print(f"Found {len(analyzer.nodes)} top-level constructs")
print(f"Found {len(analyzer.call_relationships)} relationships")

# Print nodes
for node in analyzer.nodes:
    print(f"  {node.display_name} at {node.relative_path}:{node.start_line}")

# Print relationships
for rel in analyzer.call_relationships:
    status = "resolved" if rel.is_resolved else "unresolved"
    print(f"  {rel.caller} → {rel.callee} ({status})")
```

### Using analyze_c_file() Function

```python
from codewiki.src.be.dependency_analyzer.analyzers.c import analyze_c_file

# Convenience function wrapper
nodes, relationships = analyze_c_file(
    file_path="src/parser.c",
    content=content,
    repo_path="/home/user/project"
)

print(f"Analyzed {len(nodes)} constructs")
print(f"Found {len(relationships)} dependencies")
```

---

## Testing & Validation

### Test Scenarios

1. **Simple Functions**: Single file with multiple functions
2. **Structs**: Struct definitions and usage
3. **Global Variables**: Declaration and usage across functions
4. **System Calls**: Verify filtering of printf, malloc, etc.
5. **Cross-File References**: Unresolved relationships
6. **Edge Cases**: Empty files, single-line functions, comments in code

### Verification Steps

1. Compare extracted nodes against source file
2. Verify component IDs are unique and properly formatted
3. Check line numbers match actual source
4. Validate that relationships reference existing nodes
5. Confirm system functions are filtered
6. Verify cross-file relationships are marked as unresolved

---

## Performance Considerations

- **Incremental Parsing**: Tree-Sitter supports incremental updates for faster re-analysis
- **Single-Pass Extraction**: Node and relationship extraction in one traversal
- **Memory Usage**: AST and source code stored in memory; suitable for files <1MB
- **Scalability**: Tested with files up to several MB; linear performance with file size

---

## Version Information

- **Analyzer Framework**: Tree-Sitter v0.20+
- **Language Binding**: `tree_sitter_c` Python binding
- **C Standard**: C99 and later
- **Last Updated**: 2024
