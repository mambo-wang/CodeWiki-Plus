# C# Analyzer Module Documentation

## Overview

The **csharp_analyzer** module is a language-specific analyzer responsible for parsing and extracting code components and their relationships from C# source files. It is part of the larger CodeWiki dependency analysis system and enables automated documentation generation by understanding C# code structure, class hierarchies, and component dependencies.

### Module Purpose

- **Parse C# syntax trees** using Tree-sitter parser to identify code components
- **Extract type definitions** including classes, interfaces, structs, enums, records, and delegates
- **Analyze dependencies** between components based on inheritance, field types, property types, and method parameters
- **Generate component metadata** for documentation and visualization
- **Support repository-wide analysis** by processing multiple C# files consistently

---

## Architecture

### System Context

The C# Analyzer is one of multiple language-specific analyzers in the CodeWiki system:

**Input**: C# source files (`.cs`)

**Processing**:
1. Uses Tree-sitter library with C# grammar to parse files
2. Extracts type definitions (classes, interfaces, structs, enums, records, delegates)
3. Identifies dependencies between components
4. Generates Node and CallRelationship data objects

**Output**: 
- List of Node objects (components with metadata)
- List of CallRelationship objects (dependencies between components)

**Integration Points**:
- DependencyParser: Orchestrates analysis across multiple files
- AnalysisService: Manages multi-language analysis
- DocumentationGenerator: Consumes analysis results to generate documentation

### TreeSitterCSharpAnalyzer Class Structure

```
TreeSitterCSharpAnalyzer
├── __init__(file_path, content, repo_path)
│   └── Initializes analyzer and triggers _analyze()
│
├── _analyze()
│   ├── Creates Tree-sitter parser
│   ├── Parses file to AST
│   ├── Calls _extract_nodes()
│   └── Calls _extract_relationships()
│
├── _extract_nodes(node, top_level_nodes, lines)
│   ├── Identifies type declarations
│   ├── Creates Node objects
│   └── Recursively processes child nodes
│
├── _extract_relationships(node, top_level_nodes)
│   ├── Analyzes dependencies
│   ├── Creates CallRelationship objects
│   └── Recursively processes child nodes
│
└── Helper Methods
    ├── _is_primitive_type(type_name)
    ├── _find_containing_class(node, top_level_nodes)
    ├── _get_component_id(name)
    ├── _get_module_path()
    ├── _get_relative_path()
    ├── _get_identifier_name(node)
    ├── _get_identifier_name_cs(node)
    └── _get_type_name(node)
```

---

## Core Components

### 1. TreeSitterCSharpAnalyzer

**Purpose**: Main analyzer class that parses C# files and extracts code components and relationships.

**Key Attributes**:
- `file_path` (Path): Path to the C# file being analyzed
- `content` (str): Raw content of the C# file
- `repo_path` (str): Repository root path for relative path calculation
- `nodes` (List[Node]): Extracted code components
- `call_relationships` (List[CallRelationship]): Dependencies between components

**Key Methods**:

#### `__init__(file_path, content, repo_path=None)`
Initializes the analyzer and triggers analysis by calling `_analyze()`.

#### `_analyze()`
Main orchestrator method that:
1. Creates a Tree-sitter parser with C# language support
2. Parses the file content into an Abstract Syntax Tree (AST)
3. Extracts top-level nodes (type definitions)
4. Extracts relationships between nodes

#### `_extract_nodes(node, top_level_nodes, lines)`
Recursively traverses the AST and extracts type definitions.

**Supported type definitions**:
- Class declarations (including abstract and static variants)
- Interface declarations
- Struct declarations
- Enum declarations
- Record declarations (C# 9+)
- Delegate declarations

**For each extracted component, captures**:
- Component ID (format: `relative_path::component_name`)
- Component name and type
- Source code snippet
- Line number range (start_line, end_line)
- Docstring information (if available)

#### `_extract_relationships(node, top_level_nodes)`
Recursively analyzes AST nodes to identify dependencies.

**Relationship types extracted**:

1. **Inheritance relationships**: From `base_list` nodes in class declarations
   - Creates CallRelationship with `is_resolved=True`
   - Links child classes to parent classes/interfaces

2. **Property type dependencies**: From property declarations
   - Extracts type from property definition
   - Creates relationship if type is not primitive

3. **Field type dependencies**: From field declarations
   - Extracts type from field definition
   - Creates relationship if type is not primitive

4. **Method parameter type dependencies**: From method declarations
   - Iterates through parameters in parameter_list
   - Extracts type from each parameter
   - Creates relationships for non-primitive types

**Resolution status**:
- `is_resolved=True`: Type is a known top-level component in the same file
- `is_resolved=False`: Type is external dependency or unresolved reference

#### `_is_primitive_type(type_name)`
Filters out C# primitive and common built-in types.

**Primitive types**:
- Basic: bool, byte, sbyte, char, decimal, double, float, int, uint, long, ulong, short, ushort, string, object, void

**Common framework types**:
- Collections: List, Dictionary, IList, IDictionary, IEnumerable, ICollection
- Async: Task, CancellationToken
- Utilities: DateTime, TimeSpan, Guid

Prevents unnecessary dependency tracking for system types.

#### `_find_containing_class(node, top_level_nodes)`
Traverses parent nodes to find the enclosing class/struct/interface/enum/record/delegate.

Enables proper attribution of relationships to their containing component.

#### `_get_component_id(name)`
Generates unique component identifiers in format: `relative_path::component_name`

#### Helper Path Methods

- `_get_module_path()`: Converts file path to module path (removes extension, replaces separators with dots)
- `_get_relative_path()`: Converts absolute path to relative path from repo root
- `_get_identifier_name()`: Extracts identifier from AST node
- `_get_identifier_name_cs()`: C#-specific identifier extraction (handles keyword-based lookup)
- `_get_type_name()`: Extracts type name from type nodes (handles identifiers, generics, predefined types)

---

## Data Flow

### Step 1: Initialization and Parsing

**Input**: C# file path, content, repository path

**Process**:
1. TreeSitterCSharpAnalyzer.__init__() receives file information
2. Calls _analyze() method
3. Creates Tree-sitter parser with C# language support
4. Parses file content into Abstract Syntax Tree
5. Gets root node and file lines

### Step 2: Type Definition Extraction

**Process**: _extract_nodes() recursively traverses AST

**For each node**:
1. Check node type (class_declaration, interface_declaration, etc.)
2. If type definition found:
   - Extract component name (find keyword, then identifier)
   - Determine modifiers (abstract, static, etc.)
   - Build Node object with:
     - id: unique component identifier
     - name: component name
     - component_type: derived from node type and modifiers
     - source_code: extracted source lines
     - line numbers: start and end
     - other metadata
   - Add to nodes list
   - Store in top_level_nodes dictionary

3. Recursively process child nodes

**Output**: List of Node objects representing all type definitions

### Step 3: Relationship Extraction

**Process**: _extract_relationships() recursively analyzes AST

**For each node**:
1. Determine containing class (for proper relationship attribution)
2. Analyze based on node type:
   - **class_declaration**: Extract base_list for inheritance
   - **property_declaration**: Extract property type
   - **field_declaration**: Extract field type
   - **method_declaration**: Extract parameter types

3. For each extracted type:
   - Check if it's a primitive type (skip if yes)
   - Check if it's a known top-level type (set is_resolved flag)
   - Create CallRelationship object

4. Recursively process child nodes

**Output**: List of CallRelationship objects representing dependencies

### Step 4: Results Return

**Output**:
- `nodes`: List[Node] - all extracted components
- `call_relationships`: List[CallRelationship] - all dependencies

---

## Key Features

### 1. Tree-Sitter Based Parsing

**Advantages**:
- Robust parsing of complex C# syntax
- Handles malformed code gracefully
- Efficient incremental parsing
- Well-maintained C# grammar

### 2. Multi-Type Support

Comprehensive coverage of C# type system:
- Classes (with abstract and static variants)
- Interfaces
- Structs (value types)
- Enums
- Records (modern C# feature)
- Delegates (function types)

### 3. Comprehensive Dependency Tracking

Captures dependencies from multiple sources:
- Class inheritance chains (extends/implements)
- Property type declarations
- Field type declarations
- Method parameter type declarations

Provides complete picture of component interdependencies.

### 4. Type Filtering

Intelligent filtering distinguishes domain types from system types:
- Filters all C# primitives
- Filters common framework types
- Focuses analysis on domain-specific types
- Improves documentation clarity by reducing noise

### 5. Path Management

Handles cross-platform path variations:
- Converts absolute to relative paths
- Normalizes path separators (forward/backward slashes)
- Generates module paths for import-like identification
- Enables consistent component IDs across systems

### 6. Metadata Extraction

Captures comprehensive component information:
- Unique component identifier
- Component name and type
- Full source code
- Precise line number range
- Documentation/docstring information
- Display-friendly names

---

## Integration Points

### With DependencyParser

The DependencyParser orchestrates analysis of complete repositories:

1. **Discovery**: Scans repository for all `.cs` files
2. **Per-file analysis**: Creates TreeSitterCSharpAnalyzer for each file
3. **Results aggregation**: Collects nodes and relationships
4. **Graph construction**: Builds complete dependency graph
5. **Cross-language**: Merges results with other language analyzers

### With AnalysisService

The AnalysisService coordinates the overall analysis pipeline:
1. Repository structure analysis (directory scanning)
2. Multi-language file discovery
3. Parallel component analysis
4. Call graph construction
5. Service orchestration

See [dependency_analysis_services.md](dependency_analysis_services.md) for details.

### With Node & CallRelationship Models

**Node Model**: Represents code components

```python
Node(
    id="MyFile.cs::MyClass",              # Unique identifier
    name="MyClass",                        # Component name
    component_type="class",                # Type of component
    file_path="/abs/path/MyFile.cs",      # Absolute path
    relative_path="src/MyFile.cs",        # Relative to repo
    source_code="public class MyClass...", # Source code
    start_line=5,                          # Where it starts
    end_line=25,                           # Where it ends
    display_name="class MyClass",          # For UI display
    base_classes=["BaseClass"],            # Inheritance
    component_id="MyFile.cs::MyClass"      # Same as id
)
```

**CallRelationship Model**: Represents dependencies

```python
CallRelationship(
    caller="MyFile.cs::MyClass",           # Component with dependency
    callee="MyFile.cs::IDependency",       # Dependency target
    call_line=10,                          # Where relationship occurs
    is_resolved=True                       # Known type vs external
)
```

See [dependency_analyzer_models.md](dependency_analyzer_models.md) for detailed model documentation.

### With DocumentationGenerator

Analysis results feed into documentation pipeline:

1. **Node processing**: DocumentationGenerator iterates over extracted nodes
2. **Relationship analysis**: Builds dependency graphs from relationships
3. **Content generation**: Uses nodes + relationships to generate documentation
4. **Agent execution**: Leverages analysis for AI-generated content
5. **Output formatting**: Converts to Markdown and HTML

See [documentation_generation.md](documentation_generation.md) for details.

---

## Usage Examples

### Direct Usage: Analyze Single File

```python
from codewiki.src.be.dependency_analyzer.analyzers.csharp import analyze_csharp_file

# Read C# file
with open("src/UserService.cs", "r") as f:
    content = f.read()

# Analyze
nodes, relationships = analyze_csharp_file(
    file_path="src/UserService.cs",
    content=content,
    repo_path="/path/to/repo"
)

# Process results
print(f"Found {len(nodes)} components")
for node in nodes:
    print(f"  - {node.display_name} (lines {node.start_line}-{node.end_line})")

print(f"\nFound {len(relationships)} dependencies")
for rel in relationships:
    if rel.is_resolved:
        print(f"  - {rel.caller} -> {rel.callee} (line {rel.call_line})")
```

### Integration: Full Repository Analysis

```python
from codewiki.src.be.dependency_analyzer.ast_parser import DependencyParser

# Create parser for repository
parser = DependencyParser(repo_path="/path/to/csharp-project")

# Parse entire repository (auto-detects and uses C# analyzer for .cs files)
components = parser.parse_repository()

# Query results
print(f"Total components: {len(components)}")

# Find all classes with their inheritance
for component_id, node in components.items():
    if "class" in node.component_type:
        bases = f" inherits from {node.base_classes}" if node.base_classes else ""
        print(f"{node.name}{bases}")

# Find all dependencies
for component_id, node in components.items():
    if node.depends_on:
        print(f"\n{node.name} depends on:")
        for dep in node.depends_on:
            print(f"  - {dep}")
```

---

## Design Patterns

### 1. Recursive Tree Traversal

Both extraction phases use recursive AST traversal:

```python
def _extract_nodes(self, node, top_level_nodes, lines):
    # Process current node
    if node.type == "class_declaration":
        # Extract and create Node object
        ...
    
    # Recursively process all children
    for child in node.children:
        self._extract_nodes(child, top_level_nodes, lines)
```

**Advantages**:
- Automatically discovers components at any nesting level
- Clear, intuitive code flow
- Leverages natural AST structure

### 2. Type Filtering Strategy

Centralized primitive type filtering:

```python
def _is_primitive_type(self, type_name: str) -> bool:
    primitives = {"bool", "int", "string", ..., "Task", "List", ...}
    return type_name in primitives
```

**Advantages**:
- Single source of truth for type classification
- Easy to extend or customize
- Consistent behavior across all extraction methods

### 3. Path Management Separation

Distinct methods for different path operations:

- `_get_relative_path()`: Absolute → relative
- `_get_module_path()`: File path → module notation
- `_get_component_id()`: Name → unique identifier

**Advantages**:
- Clear separation of concerns
- Reusable helper methods
- Easier to test and maintain

### 4. Keyword-Based Node Identification

For C# declarations, locate keyword then identifier:

```python
def _get_identifier_name_cs(self, node):
    if node.type == "class_declaration":
        found_class_keyword = False
        for child in node.children:
            if child.type == "class":
                found_class_keyword = True
            elif found_class_keyword and child.type == "identifier":
                return child.text.decode()
```

**Advantages**:
- Handles AST structure variations
- Robust to keyword position changes
- Works consistently across declaration types

---

## Error Handling & Robustness

### Parser Resilience

The analyzer gracefully handles:
- **Incomplete/malformed C# code**: Tree-sitter continues parsing despite syntax errors
- **Missing components**: Optional node lookups return None instead of raising exceptions
- **Path issues**: Cross-platform path separator normalization
- **Encoding**: UTF-8 content handling

### Logging

Diagnostic logging via Python's logging module:

```python
import logging
logger = logging.getLogger(__name__)

logger.debug(f"Found node: {node_name}")
logger.warning(f"Unexpected node type: {node_type}")
```

Enables troubleshooting without code changes.

### Dependency Validation

Relationships validated through `is_resolved` flag:

- `True`: Callee is a known top-level component in the same file
- `False`: Callee is external dependency, external assembly reference, or unresolved type

Allows downstream processing to handle resolved vs. unresolved differently.

---

## Performance Characteristics

### Time Complexity per File

- **Parsing**: O(n) where n = file size
- **Node extraction**: O(m) where m = number of AST nodes  
- **Relationship extraction**: O(m × k) where k = average node children
- **Overall**: O(n) - linear in file size

### Space Complexity

- **AST storage**: O(n) to hold parsed tree
- **Results**: O(c + r) where c = components, r = relationships
- **Working memory**: O(m) during traversal

### Scalability

- **Small files**: Negligible overhead
- **Medium files (10K LOC)**: Milliseconds
- **Large files (100K+ LOC)**: Depends on code structure

For repository-wide analysis, parallelization across files is recommended.

---

## Comparison with Other Language Analyzers

| Feature | C# | Python | JavaScript | TypeScript |
|---------|-----|--------|------------|-----------|
| **Parser Technology** | Tree-sitter | Python AST | Tree-sitter | Tree-sitter |
| **Type Support** | Classes, Interfaces, Structs, Enums, Records, Delegates | Classes, Functions | Classes, Functions | Classes, Interfaces, Functions |
| **Inheritance Analysis** | ✓ (base_list) | ✓ (bases) | ✓ (class_name) | ✓ (extends/implements) |
| **Field/Property Analysis** | ✓ | - | ✓ | ✓ |
| **Method Parameter Analysis** | ✓ | - | ✓ | ✓ |
| **Function Call Tracking** | - | ✓ | ✓ | ✓ |
| **Focus** | Type structure | Function calls | Object structure | Object structure |

**Key Distinction**: C# analyzer emphasizes **type hierarchy and data structure** relationships, while Python analyzer focuses on **function invocation** patterns.

---

## Dependencies

### External Libraries

- **tree-sitter** (>= 0.20.0): Core parsing framework
- **tree-sitter-c-sharp** (appropriate version): C# language grammar

### Internal Dependencies

- **codewiki.src.be.dependency_analyzer.models.core**: Node, CallRelationship classes
- **codewiki.src.be.dependency_analyzer**: Parent package
- **logging**: Python standard library

---

## Future Enhancements

### Analysis Improvements

1. **Generic Type Support**: Better handling of `List<T>`, `Dictionary<K,V>`, `IEnumerable<T>`
2. **Method Call Tracking**: Analyze method invocations within class bodies
3. **Namespace Resolution**: Track cross-namespace dependencies
4. **Attribute/Annotation Extraction**: Capture C# attributes and their usage
5. **Interface Implementation**: Explicitly track which interfaces each class implements
6. **Extension Methods**: Recognize and track extension method dependencies
7. **Async/Await Relationships**: Track Task-based async dependencies

### Infrastructure Improvements

8. **Parallel Processing**: Process multiple files in parallel for large repositories
10. **Incremental Analysis**: Cache and reuse results for unchanged files
11. **Custom Type Lists**: User-configurable primitive/framework type filters

### Output Enhancements

12. **Type Annotations**: Include detailed type information in nodes
13. **Visibility Metadata**: Track public/private/protected modifiers
14. **Summary Comments**: Extract and include XML documentation
15. **Generic Type Parameters**: Properly handle and display type constraints

---

## Related Documentation

- [language_analyzers.md](language_analyzers.md) - Overview of all language analyzers
- [dependency_analysis_services.md](dependency_analysis_services.md) - Service orchestration layer
- [dependency_analyzer_models.md](dependency_analyzer_models.md) - Node and CallRelationship models
- [documentation_generation.md](documentation_generation.md) - How analysis results are used
- [dependency_analyzer.md](dependency_analyzer.md) - High-level dependency analysis module

---

## File Reference

**Location**: `codewiki/src/be/dependency_analyzer/analyzers/csharp.py`

**Primary Export**: `TreeSitterCSharpAnalyzer` class

**Helper Function**: 
```python
analyze_csharp_file(
    file_path: str, 
    content: str, 
    repo_path: str = None
) -> Tuple[List[Node], List[CallRelationship]]
```

**Public API Usage**: Both class and helper function are part of public API for analyzer orchestration.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| **v1.0** | Initial | Support for classes, interfaces, structs, enums, records, delegates |
| **v1.1** | Later | Added property and field type dependency tracking |
| **v1.2** | Later | Improved method parameter dependency extraction |
| **v1.3** | Current | Enhanced primitive type filtering with expanded built-in types list |

---

## Troubleshooting

### Issue: No nodes extracted from file

**Possible causes**:
- File has syntax errors (check Tree-sitter tolerance)
- Components defined in unexpected locations
- File encoding issues (ensure UTF-8)

**Solution**: Check file content directly, verify C# syntax validity

### Issue: Missing relationships

**Possible causes**:
- Types filtered as primitives (check _is_primitive_type list)
- External/unresolved types not tracked (by design)
- Incomplete AST traversal (rare - check for exceptions in logs)

**Solution**: Review primitive type filtering, verify cross-file relationships expected

### Issue: Incorrect component IDs

**Possible causes**:
- Repository path configuration error
- Path separator issues (Windows vs Unix)
- Symlink handling

**Solution**: Verify repo_path parameter, check path normalization

