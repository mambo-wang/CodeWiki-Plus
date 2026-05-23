# Python Analyzer Module Documentation

## Overview

The **Python Analyzer** module is a language-specific analyzer component responsible for parsing and extracting code structure information from Python files. It leverages Python's built-in AST (Abstract Syntax Tree) module to analyze Python source code, identify classes and functions, and extract relationships between code components.

**Key Purpose**: Convert raw Python source code into a structured representation of code components (classes, functions) with their dependencies and call relationships, enabling downstream documentation generation and code analysis.

---

## Module Architecture

### System Position

The Python Analyzer is one of multiple language analyzers in the CodeWiki documentation system:

```
[Repository] 
    ↓
[RepoAnalyzer] → [Language-Specific Analyzers]
                    ├── Python Analyzer ← You are here
                    ├── JavaScript Analyzer
                    ├── TypeScript Analyzer
                    ├── Java Analyzer
                    ├── C/C++/C# Analyzers
                    └── PHP/Kotlin Analyzers
    ↓
[CallGraphAnalyzer] (builds call graphs from extracted nodes)
    ↓
[DocumentationGenerator] (generates markdown/HTML documentation)
```

### Core Architecture Diagram

The Python Analyzer follows this component flow:

1. **Input**: Python source file with repository context
2. **Parsing**: Convert source code to AST using `ast.parse()`
3. **Visitor Pattern**: Traverse AST with specialized handlers
4. **Output**: Node objects for classes/functions and Relationship objects for dependencies

```
Input File → AST Parser → Tree Visitor → [ClassDef, FunctionDef, Call handlers]
                                              ↓                ↓
                                        Node Objects    Relationships
```

---

## Core Components

### 1. PythonASTAnalyzer

**Type**: AST Visitor Pattern Implementation  
**Inherits from**: `ast.NodeVisitor`  
**Responsibility**: Extract code structure and relationships from Python AST

#### Key Attributes

| Attribute | Type | Purpose |
|-----------|------|---------|
| `file_path` | `str` | Path to the Python file being analyzed |
| `content` | `str` | Raw source code content |
| `repo_path` | `Optional[str]` | Repository root for relative path calculation |
| `nodes` | `List[Node]` | Extracted classes and functions |
| `call_relationships` | `List[CallRelationship]` | Function call dependencies |
| `current_class_name` | `Optional[str]` | Tracks nested class context |
| `current_function_name` | `Optional[str]` | Tracks nested function context |
| `top_level_nodes` | `dict` | Map of top-level components by name |

#### Key Methods

##### `__init__(file_path, content, repo_path)`
Initializes the analyzer with Python file context.

**Parameters**:
- `file_path`: Path to Python file
- `content`: Raw file content
- `repo_path`: Optional repository root path

**Side Effects**: Initializes all tracking structures

---

##### `analyze()`
Main analysis entry point - parses Python code and visits AST nodes.

**Process**:
1. Parses content using `ast.parse()`
2. Traverses AST using visitor pattern
3. Collects nodes and relationships
4. Handles syntax errors gracefully

**Error Handling**:
- SyntaxWarnings suppressed (regex patterns in analyzed code)
- SyntaxErrors logged with warnings
- General exceptions logged with traceback

```python
# Usage
analyzer = PythonASTAnalyzer(file_path, content, repo_path)
analyzer.analyze()
nodes = analyzer.nodes
relationships = analyzer.call_relationships
```

---

##### `visit_ClassDef(node: ast.ClassDef)`
Processes class definitions.

**Extracts**:
- Class name and inheritance (base classes)
- Docstring
- Source code range
- Component ID in format: `relative_path::ClassName`

**Creates**:
- `Node` object with type `"class"`
- `CallRelationship` for each inherited base class

**Special Behavior**:
- Tracks `current_class_name` for nested context
- Continues traversal into class body for methods

---

##### `visit_FunctionDef(node: ast.FunctionDef)` / `visit_AsyncFunctionDef(node: ast.AsyncFunctionDef)`
Processes function definitions.

**Extracts**:
- Function name and parameters
- Docstring
- Source code range
- Component ID in format: `relative_path::function_name` (only top-level)

**Filtering**:
- Skips test functions (starting with `_test_`)
- Only captures top-level functions (not methods)

**Special Behavior**:
- Tracks `current_function_name` for nested context
- Continues traversal into function body

---

##### `visit_Call(node: ast.Call)`
Processes function call nodes.

**Relationship Extraction**:
- Identifies caller (current class or function)
- Identifies callee (called function name)
- Records call line number
- Marks relationship as resolved/unresolved

**Scope Tracking**:
- Only records calls within class definitions or top-level functions
- Ignores calls within nested structures

**Example**:
```python
# If analyzing:
class MyClass:
    def method(self):
        helper_func()  # Creates CallRelationship
        print("test")   # Ignored (builtin)
```

---

### 2. Output Data Models

#### Node

**Source**: [dependency_analyzer_models](dependency_analyzer_models.md#node)

Represents a code component (class or function).

**Key Fields for Python**:
```python
Node(
    id="relative_path::ComponentName",           # Unique identifier
    name="ComponentName",                         # Component name
    component_type="class" | "function",         # Type discriminator
    file_path="/absolute/path/file.py",          # Absolute path
    relative_path="src/module/file.py",          # Repo-relative path
    source_code="...",                           # Full source text
    start_line=10,                               # 1-indexed line number
    end_line=25,                                 # Inclusive end line
    has_docstring=True,                          # Docstring presence
    docstring="Documentation text",              # Extracted docstring
    parameters=["arg1", "arg2"],                 # For functions
    base_classes=["BaseClass", "Mixin"],         # For classes
    display_name="class MyClass"                 # Human-readable name
)
```

#### CallRelationship

**Source**: [dependency_analyzer_models](dependency_analyzer_models.md#callrelationship)

Represents a dependency between two code components.

**Structure**:
```python
CallRelationship(
    caller="relative_path::ClassName",       # Caller ID
    callee="relative_path::function_name",   # Callee ID
    call_line=45,                            # Where call occurs
    is_resolved=True                         # Whether callee exists in repo
)
```

**Resolution States**:
- `is_resolved=True`: Callee found in same file (top-level)
- `is_resolved=False`: External call (different file/module)

---

## Processing Pipeline

### Detailed Data Flow

**Phase 1: Input & Parsing**
- Read Python file content
- Parse to AST using `ast.parse()`
- Validate syntax

**Phase 2: Tree Traversal**
- Visit AST nodes using visitor pattern
- For each node type:
  - **ClassDef**: Extract class name, bases, docstring → Create `Node` object
  - **FunctionDef/AsyncFunctionDef**: Extract function details → Create `Node` object
  - **Call**: Extract call relationships → Create `CallRelationship` object

**Phase 3: Output**
- Collect all `Node` objects (classes and functions)
- Collect all `CallRelationship` objects
- Return tuple of (nodes, relationships)

### Analysis Steps

1. **Initialization**
   - Store file context (path, content, repo root)
   - Initialize empty collections for nodes and relationships

2. **Parsing**
   - Parse Python content using `ast.parse()`
   - Handle SyntaxErrors gracefully with logging

3. **Tree Traversal**
   - Visit AST root node
   - Recursively visit all child nodes using visitor pattern
   - Dispatch to specialized visit methods based on node type

4. **Class Processing**
   - Extract class name, base classes, docstring
   - Create `Node` object with type="class"
   - Create `CallRelationship` for inheritance (if base exists)
   - Set context for nested method analysis

5. **Function Processing**
   - Extract function name, parameters, docstring
   - Create `Node` object only if top-level (not nested in class)
   - Apply filtering rules (skip test functions)
   - Set context for analyzing function body

6. **Call Tracking**
   - Identify function calls within current scope
   - Filter out Python built-ins
   - Create `CallRelationship` with resolved/unresolved status
   - Continue traversal to nested calls

7. **Result Compilation**
   - Return collected `nodes` and `call_relationships`
   - Ready for downstream analysis

---

## Special Features

### 1. Built-in Function Filtering

Python analyzer maintains a comprehensive list of Python built-in functions and classes to avoid creating spurious dependencies:

```python
PYTHON_BUILTINS = {
    "print", "len", "str", "int", "float", "bool", 
    "list", "dict", "tuple", "set", "range", "enumerate",
    "zip", "isinstance", "hasattr", "getattr", "setattr",
    "open", "super", "__import__", "type", "object",
    # ... (40+ built-ins)
    "max", "min", "sum", "abs", "round", "sorted"
}
```

**Impact**: Only user-defined function calls create relationships

### 2. Relative Path Normalization

Converts absolute paths to repository-relative paths for consistent component IDs:

```python
def _get_relative_path() -> str:
    if self.repo_path:
        return os.path.relpath(self.file_path, self.repo_path)
    return str(self.file_path)
```

**Example**:
- Input: `/home/user/project/src/main/app.py`
- Repo root: `/home/user/project`
- Output: `src/main/app.py`

### 3. Component ID Format

Standardized format for unique identification:

```
relative_path::ComponentName
relative_path::ClassName.MethodName  # For class methods (future)
```

**Examples**:
- `src/api/handlers.py::process_request`
- `src/models/user.py::User`
- `src/models/user.py::User.validate`

### 4. Scope-Based Analysis

Tracks nested scope to distinguish between:

```python
class MyClass:           # Top-level class → Node created
    def method(self):    # Class method → NOT a node
        def helper():    # Nested function → NOT a node
            pass

def top_level_func():    # Top-level function → Node created
    def inner():         # Nested function → NOT a node
        pass
```

### 5. Error Handling Strategy

| Error Type | Handler | Result |
|-----------|---------|--------|
| SyntaxWarning (escape sequences) | Suppressed | Silent ignore |
| SyntaxError | Logged warning | Return empty results |
| Exception | Logged error + traceback | Return empty results |

---

## Integration Points

### Upstream Dependencies

**Components that feed into PythonASTAnalyzer**:
- **RepoAnalyzer**: Reads Python files and invokes the analyzer
- **FileManager**: Provides file content and path utilities
- **Logger**: Logs analysis events for debugging

**External Dependencies**:
- `codewiki.src.be.dependency_analyzer.models.core`: Node, CallRelationship
- Standard library: `ast`, `logging`, `pathlib`, `os`, `sys`

### Downstream Consumers

**Analysis Pipeline Flow**:

```
PythonASTAnalyzer
    ↓ (nodes, relationships)
CallGraphAnalyzer
    ↓ (call graph)
DependencyGraphBuilder
    ↓ (dependency structure)
DocumentationGenerator
    ↓ (analysis results)
Output: Markdown/HTML
```

**Key Consumers**:
- [dependency_analysis_services](dependency_analysis_services.md): RepoAnalyzer, CallGraphAnalyzer
- [dependency_graph_construction](dependency_graph_construction.md): DependencyGraphBuilder
- [documentation_generation](documentation_generation.md): DocumentationGenerator

---

## Usage Examples

### Basic Analysis

```python
from codewiki.src.be.dependency_analyzer.analyzers.python import (
    PythonASTAnalyzer,
    analyze_python_file
)

# Method 1: Using utility function
file_path = "src/models/user.py"
with open(file_path, 'r') as f:
    content = f.read()

nodes, relationships = analyze_python_file(
    file_path=file_path,
    content=content,
    repo_path="/home/user/project"
)

# nodes: List[Node] - extracted classes and functions
# relationships: List[CallRelationship] - function calls
```

### Direct Analyzer Usage

```python
# Method 2: Using analyzer class directly
analyzer = PythonASTAnalyzer(
    file_path="src/api/handlers.py",
    content=file_content,
    repo_path="/home/user/project"
)

# Analyze the file
analyzer.analyze()

# Access results
for node in analyzer.nodes:
    print(f"Found {node.component_type}: {node.name}")
    print(f"  Location: {node.file_path}:{node.start_line}")
    if node.docstring:
        print(f"  Docs: {node.docstring[:50]}...")

for rel in analyzer.call_relationships:
    status = "✓" if rel.is_resolved else "?"
    print(f"{status} {rel.caller} → {rel.callee} (line {rel.call_line})")
```

### Processing Multiple Files

```python
from pathlib import Path

repo_path = Path("/home/user/project")
all_nodes = []
all_relationships = []

for py_file in repo_path.rglob("*.py"):
    if "venv" in py_file.parts or "__pycache__" in py_file.parts:
        continue
    
    content = py_file.read_text()
    nodes, rels = analyze_python_file(
        str(py_file),
        content,
        str(repo_path)
    )
    
    all_nodes.extend(nodes)
    all_relationships.extend(rels)

print(f"Total: {len(all_nodes)} components, {len(all_relationships)} relationships")
```

---

## Key Design Patterns

### 1. Visitor Pattern

The analyzer implements the classic Visitor pattern for AST traversal:

```
NodeVisitor (base class)
    ↓
PythonASTAnalyzer (concrete visitor)
    ├── visit_ClassDef()
    ├── visit_FunctionDef()
    ├── visit_AsyncFunctionDef()
    ├── visit_Call()
    └── generic_visit() (default handler)
```

**Benefit**: Separates AST structure from processing logic

### 2. Context Tracking

Maintains stack-like context for nested structures:

```python
self.current_class_name = None      # Track class scope
self.current_function_name = None   # Track function scope

# When entering:
self.current_class_name = "MyClass"  # Set context
self.generic_visit(node)             # Visit children
self.current_class_name = None       # Restore context
```

**Benefit**: Distinguishes between methods and functions

### 3. Two-Phase Relationship Resolution

```
Phase 1: Extract relationships with is_resolved=?
    ↓
Phase 2: Match against top_level_nodes dictionary
    ↓
Result: is_resolved=True/False flags set
```

**Benefit**: Handles forward references gracefully

---

## Python Language Support

### Supported Features

| Feature | Support | Notes |
|---------|---------|-------|
| **Classes** | ✅ | Including inheritance |
| **Functions** | ✅ | Top-level only |
| **Async Functions** | ✅ | Same as regular functions |
| **Methods** | ⚠️ | Extracted but not indexed as separate nodes |
| **Decorators** | ⏳ | Not currently extracted |
| **Type Hints** | ⏳ | Not currently used |
| **Imports** | ⏳ | Not analyzed for dependency extraction |
| **Docstrings** | ✅ | Extracted and stored |
| **Parameters** | ✅ | Extracted for functions |

### Limitations

1. **No Import Analysis**: Cross-module dependencies not tracked
2. **Limited Method Analysis**: Methods attached to classes but not independent nodes
3. **No Decorator Extraction**: Decorator information lost
4. **No Type Hint Parsing**: Type annotations ignored
5. **Syntax-Only**: No semantic analysis or type checking

---

## Configuration and Logging

### Logging

Uses standard Python logging:

```python
logger = logging.getLogger(__name__)

# Log levels:
logger.debug()    # Analysis completion info
logger.warning()  # SyntaxErrors during parsing
logger.error()    # Unexpected exceptions
```

**Configure logging** via [dependency_analyzer_utils](dependency_analyzer_utils.md):

```python
from codewiki.src.be.dependency_analyzer.utils.logging_config import ColoredFormatter
```

### Performance Characteristics

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| File parsing | O(n) | n = lines of code |
| AST traversal | O(n) | Linear tree walk |
| Call resolution | O(k) | k = number of calls |
| **Total** | **O(n)** | Single pass analysis |

**Typical Performance**:
- Small file (100 LOC): < 10ms
- Medium file (1000 LOC): 10-50ms
- Large file (10000 LOC): 50-200ms

---

## Error Scenarios and Recovery

### Scenario 1: Invalid Python Syntax

```python
# File content has syntax error
file_content = """
def broken_function(
    # Missing closing paren
"""

analyzer = PythonASTAnalyzer(path, file_content)
analyzer.analyze()

# Result:
# ⚠️ Warning logged: "Could not parse file.py: invalid syntax"
# nodes = [] (empty)
# call_relationships = [] (empty)
```

### Scenario 2: Escape Sequence Warnings

```python
# File being analyzed contains regex patterns
file_content = r"""
regex_pattern = "^\d+"  # Warning without suppression
"""

analyzer = PythonASTAnalyzer(path, file_content)
analyzer.analyze()

# Result:
# ✅ Analyzed successfully (warnings suppressed)
# nodes = [any found classes/functions]
```

### Scenario 3: Missing Repository Path

```python
analyzer = PythonASTAnalyzer(
    file_path="/absolute/path/file.py",
    content=file_content,
    repo_path=None  # No repo context
)

# Fallback behavior:
# - Uses absolute path for component IDs
# - Still extracts structure normally
# - Less useful for cross-repo linking
```

---

## Testing Considerations

### Unit Test Areas

1. **ClassDef Handling**
   - Simple classes
   - Inherited classes
   - Multiple inheritance

2. **Function Extraction**
   - Top-level functions
   - Async functions
   - Test function filtering

3. **Call Detection**
   - Simple function calls
   - Method calls
   - Built-in filtering
   - Unresolved calls

4. **Error Resilience**
   - Invalid syntax
   - Missing files
   - Encoding issues

### Mock Objects

```python
# Minimal mock for testing
mock_node = Node(
    id="test.py::TestFunc",
    name="TestFunc",
    component_type="function",
    file_path="test.py",
    relative_path="test.py",
    source_code="def TestFunc(): pass",
    start_line=1,
    end_line=1,
    has_docstring=False,
    docstring="",
    parameters=[],
    node_type="function",
    base_classes=None,
    class_name=None,
    display_name="function TestFunc",
    component_id="test.py::TestFunc"
)
```

---

## Related Components

- **[dependency_analyzer_models](dependency_analyzer_models.md)**: Core data structures (Node, CallRelationship)
- **[language_analyzers](language_analyzers.md)**: Other language analyzers (JS, TypeScript, Java, etc.)
- **[dependency_analysis_services](dependency_analysis_services.md)**: RepoAnalyzer that orchestrates language-specific analyzers
- **[dependency_graph_construction](dependency_graph_construction.md)**: Builds dependency graphs from analysis results
- **[documentation_generation](documentation_generation.md)**: Generates documentation from analyzed code

---

## Future Enhancements

### Planned Features

1. **Import Tracking**
   - Extract `import` and `from...import` statements
   - Build cross-module dependency graph
   - Track external library usage

2. **Type Hint Extraction**
   - Parse type annotations
   - Track parameter and return types
   - Enable type-based documentation

3. **Decorator Support**
   - Extract decorator information
   - Track framework-specific markers (Flask routes, FastAPI endpoints, etc.)
   - Integrate with LLM analysis

4. **Advanced Scope Analysis**
   - Independent method nodes
   - Nested function support
   - Lambda expression tracking

5. **Semantic Analysis**
   - Basic type inference
   - Unused code detection
   - Complexity metrics

---

## Summary

The **Python Analyzer** module provides robust, AST-based parsing of Python source files, extracting class and function definitions along with their call relationships. Its integration with the broader CodeWiki analysis pipeline enables:

- **Accurate Code Mapping**: Complete extraction of Python code structure
- **Dependency Tracking**: Identification of function call relationships
- **Foundation for Documentation**: Structured data ready for LLM analysis and documentation generation
- **Language Agnostic Integration**: Plugs seamlessly into multi-language analysis system

By combining Python's native AST module with the visitor pattern and careful context tracking, the analyzer achieves high precision while maintaining simplicity and maintainability.
