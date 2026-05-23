# Java Analyzer Module Documentation

## Overview

The **java_analyzer** module is a language-specific analyzer component within the dependency analysis system. It leverages Tree-Sitter Java parser to analyze Java source code files and extract Java components (classes, interfaces, enums, methods, etc.) along with their relationships (inheritance, implementation, field dependencies, method calls, and object creation patterns).

This module is part of the **language_analyzers** group, which provides specialized parsing for different programming languages. The java_analyzer specifically handles Java syntax parsing and semantic relationship detection.

## Module Purpose

The java_analyzer module serves three primary functions:

1. **Component Extraction**: Identifies and extracts all Java top-level components (classes, interfaces, enums, records, annotations) and methods
2. **Relationship Detection**: Identifies dependencies and interactions between components through inheritance, implementation, field types, method invocations, and object instantiation
3. **Semantic Analysis**: Analyzes Java code structure to understand class hierarchies, method dependencies, and type relationships

## Architecture

### System Context

The java_analyzer operates within a multi-layered architecture:

**System Layers**:
1. **Dependency Analysis System**: Core services including AnalysisService, CallGraphAnalyzer, and RepoAnalyzer
2. **Language Analyzers**: Nine language-specific analyzers (Python, JavaScript, TypeScript, Java, Kotlin, C#, C++, C, PHP)
3. **Parser Backend**: Tree-Sitter Java language library
4. **Data Models**: Node and CallRelationship representations

**Key Relationships**:
- RepoAnalyzer dispatches file analysis to appropriate language analyzers
- TreeSitterJavaAnalyzer uses Tree-Sitter Java for parsing
- Generated Nodes and CallRelationships are consumed by dependency graph builders

### Component Architecture

The `TreeSitterJavaAnalyzer` class has the following structure:

**Main Components**:
- `__init__`: Initializer accepting file path, content, and repository path
- `_analyze()`: Main analysis entry point
- `_extract_nodes()`: Identifies Java components (classes, interfaces, methods, etc.)
- `_extract_relationships()`: Detects dependencies between components
- Helper Methods: Type resolution, path utilities, and context tracking

**Extraction Categories**:
- Node Extraction: `class_declaration`, `interface_declaration`, `enum_declaration`, `record_declaration`, `annotation_type_declaration`, `method_declaration`
- Relationship Detection: Inheritance (extends), Implementation (implements), Field Type Use, Method Calls, Object Creation

## Component Details

### Core Component: TreeSitterJavaAnalyzer

The `TreeSitterJavaAnalyzer` class is the main analyzer responsible for parsing Java files and extracting structural information.

#### Class Structure

```python
class TreeSitterJavaAnalyzer:
    def __init__(self, file_path: str, content: str, repo_path: str = None)
    
    # Main Analysis Methods
    def _analyze() -> None
    
    # Node Extraction
    def _extract_nodes(node, top_level_nodes, lines) -> None
    
    # Relationship Extraction
    def _extract_relationships(node, top_level_nodes) -> None
    
    # Utility Methods
    def _get_module_path() -> str
    def _get_relative_path() -> str
    def _get_component_id(name: str, parent_class: str = None) -> str
    def _find_containing_class(node, top_level_nodes) -> Optional[str]
    def _find_containing_method(node) -> Optional[str]
    def _find_variable_type(node, variable_name, top_level_nodes) -> Optional[str]
    def _search_variable_declaration(block_node, variable_name) -> Optional[str]
    def _is_primitive_type(type_name: str) -> bool
    def _get_identifier_name(node) -> Optional[str]
    def _get_type_name(node) -> Optional[str]
```

#### Key Properties

| Property | Type | Purpose |
|----------|------|---------|
| `file_path` | `Path` | Absolute path to the Java file being analyzed |
| `content` | `str` | Source code content of the Java file |
| `repo_path` | `str` | Repository root path for relative path calculation |
| `nodes` | `List[Node]` | Extracted Java components (classes, methods, etc.) |
| `call_relationships` | `List[CallRelationship]` | Detected relationships between components |

## Data Flow

### Analysis Flow

The analysis process follows these sequential phases:

1. **Initialization**: Receive file path and content
2. **Parsing**: Parse Java code using Tree-Sitter library
3. **AST Construction**: Build Abstract Syntax Tree
4. **Node Extraction**: Identify Java components (classes, interfaces, enums, records, annotations, methods)
5. **Relationship Detection**: Identify five types of dependencies (inheritance, implementation, field types, method calls, object creation)
6. **Output Generation**: Return accumulated nodes and relationships

## Supported Java Components

The analyzer extracts the following Java language constructs:

### Type Declarations

```
┌─ class_declaration
│  └─ abstract class support
├─ interface_declaration
├─ enum_declaration
├─ record_declaration
├─ annotation_type_declaration
└─ method_declaration
   └─ Nested within classes/interfaces
```

### Extracted Node Types

| Component Type | Tree-Sitter Type | Description |
|---|---|---|
| `class` | `class_declaration` | Standard Java classes |
| `abstract class` | `class_declaration` (with abstract modifier) | Abstract class definitions |
| `interface` | `interface_declaration` | Interface definitions |
| `enum` | `enum_declaration` | Enum type definitions |
| `record` | `record_declaration` | Record type definitions (Java 14+) |
| `annotation` | `annotation_type_declaration` | Custom annotation definitions |
| `method` | `method_declaration` | Method definitions |

## Relationship Detection

The analyzer identifies five categories of dependencies:

### 1. Inheritance Relationships

**Detected Pattern**: `class ChildClass extends ParentClass`

**Detection Logic**:
- Searches for `superclass` node in `class_declaration`
- Extracts parent class name from `type_identifier`
- Excludes primitive types
- Creates `CallRelationship` with caller as child, callee as parent

### 2. Interface Implementation

**Detected Pattern**: `class MyClass implements Interface1, Interface2`

**Detection Logic**:
- Looks for `super_interfaces` in class/enum/record declarations
- Iterates through `type_list` to find all implemented interfaces
- Filters out primitive types
- Creates relationship for each interface

### 3. Field Type Dependencies

**Detected Pattern**: `private MyType fieldName;`

**Detection Logic**:
- Scans `field_declaration` nodes
- Identifies containing class for each field
- Extracts field type using `type_identifier` or `generic_type`
- Creates dependency from class to field type

### 4. Method Call Dependencies

**Detected Pattern**: `objectName.methodName()`

**Resolution Steps**:
1. Extract Method Invocation node from AST
2. Extract Object ID (object being called)
3. Extract Method ID (method being invoked)
4. Lookup Variable Type (resolve object type from context)
5. Create Relationship (if type resolved successfully)

**Detection Logic**:
- Identifies `method_invocation` nodes
- Extracts object name and method name from invocation structure
- Attempts to resolve object type:
  - First checks if object is a known top-level class
  - Falls back to local variable type lookup
- Creates relationship if target type is identified

### 5. Object Creation Dependencies

**Detected Pattern**: `new MyType()`

**Detection Logic**:
- Identifies `object_creation_expression` nodes
- Extracts created type from type node
- Links creating class to created type
- Supports generic types

## Helper Methods

### Type Resolution

#### `_get_type_name(node) -> Optional[str]`
Extracts type name from various type node structures:
- `type_identifier`: Direct type reference
- `generic_type`: Generic type with type parameters
- `superclass`: Parent class type

#### `_find_variable_type(node, variable_name, top_level_nodes) -> Optional[str]`
Resolves variable type through:
1. Local variable declaration search in containing method
2. Field declaration search in containing class
3. Tree traversal for nested scopes

#### `_search_variable_declaration(block_node, variable_name) -> Optional[str]`
Recursively searches code blocks for variable declarations:
- `local_variable_declaration`: Local variable scope
- Supports nested block structures
- Returns first matching type

### Path Resolution

#### `_get_module_path() -> str`
Converts file path to module path:
```
/src/main/java/com/example/MyClass.java → com/example/MyClass
```

#### `_get_relative_path() -> str`
Computes relative path from repository root for consistent component IDs

#### `_get_component_id(name: str, parent_class: str = None) -> str`
Generates unique component identifiers:
```
Format: {relative_path}::{component_name}
Example: src/main/java/Example.java::MyClass
         src/main/java/Example.java::MyClass.myMethod
```

### Context Tracking

#### `_find_containing_class(node, top_level_nodes) -> Optional[str]`
Traverses AST upward to find enclosing class, supports:
- `class_declaration`
- `interface_declaration`
- `enum_declaration`
- `record_declaration`
- `annotation_type_declaration`

#### `_find_containing_method(node) -> Optional[str]`
Locates enclosing method and builds full method identifier

### Type Filtering

#### `_is_primitive_type(type_name: str) -> bool`
Filters out Java primitives and common built-in types:
```
Primitives: boolean, byte, char, double, float, int, long, short
Boxed Types: Boolean, Byte, Character, Double, Float, Integer, Long, Short
Built-ins: String, Object, List, Set, Map, Collection, Optional, void, Void
```

## Public Interface

### Main Entry Point

```python
def analyze_java_file(
    file_path: str, 
    content: str, 
    repo_path: str = None
) -> Tuple[List[Node], List[CallRelationship]]:
    """
    Analyze a Java source file and extract components and relationships.
    
    Args:
        file_path: Absolute path to the Java file
        content: Source code content
        repo_path: Repository root path for relative paths
    
    Returns:
        Tuple of:
        - List[Node]: Extracted Java components
        - List[CallRelationship]: Detected relationships
    """
```

## Data Models

### Node Structure
See [dependency_analyzer_models.md](dependency_analyzer_models.md) for complete `Node` model definition.

**Key Node Fields**:
- `id`: Unique component identifier
- `name`: Component name
- `component_type`: Type of component (class, method, interface, etc.)
- `file_path`: Absolute file path
- `relative_path`: Path relative to repository root
- `start_line`, `end_line`: Location in source file
- `source_code`: Source code snippet
- `display_name`: Human-readable component name

### CallRelationship Structure
See [dependency_analyzer_models.md](dependency_analyzer_models.md) for complete `CallRelationship` model definition.

**Key Relationship Fields**:
- `caller`: Source component ID
- `callee`: Target component ID
- `call_line`: Line number where dependency occurs
- `is_resolved`: Boolean indicating if relationship is fully resolved

## Integration Points

### With Dependency Analysis System

The java_analyzer integrates with the broader dependency analysis system:

**Integration Flow**:
1. **RepoAnalyzer** dispatches each Java file to TreeSitterJavaAnalyzer
2. **TreeSitterJavaAnalyzer** produces two outputs:
   - Extracted Nodes (components found in the file)
   - Relationships (dependencies between components)
3. **DependencyGraphBuilder** consumes both outputs to construct dependency graphs
4. **Analysis Pipeline** orchestrates the complete workflow

### With Other Language Analyzers

The java_analyzer is one of nine language-specific analyzers:
- [python_analyzer.md](python_analyzer.md) - Python code analysis
- [javascript_analyzer.md](javascript_analyzer.md) - JavaScript/Node.js analysis
- [typescript_analyzer.md](typescript_analyzer.md) - TypeScript analysis
- [kotlin_analyzer.md](kotlin_analyzer.md) - Kotlin analysis
- [csharp_analyzer.md](csharp_analyzer.md) - C# analysis
- [cpp_analyzer.md](cpp_analyzer.md) - C++ analysis
- [c_analyzer.md](c_analyzer.md) - C analysis
- [php_analyzer.md](php_analyzer.md) - PHP analysis

## Tree-Sitter Integration

### Parser Configuration

```python
# Language setup
language_capsule = tree_sitter_java.language()
java_language = Language(language_capsule)
parser = Parser(java_language)

# Parsing
tree = parser.parse(bytes(self.content, "utf8"))
root = tree.root_node
```

### Tree-Sitter Java Grammar Support

The analyzer leverages the Tree-Sitter Java grammar for:
- Complete Java syntax support (Java 8 through latest versions)
- Accurate AST construction
- Robust error recovery
- Performance optimized parsing

**Supported Java Features**:
- Classes, interfaces, enums, records, annotations
- Method and field declarations
- Generics and type parameters
- Inner/nested classes
- Method invocations with various patterns
- Object creation expressions
- Inheritance and interface implementation
- Package declarations and imports (parsed but not extracted)

## Processing Workflow

### Node Extraction Workflow

**Process Steps**:
1. Parse Java file and get root AST node
2. Split content into lines for source mapping
3. Walk through entire AST tree recursively
4. For each node, check its type:
   - If class/interface/enum/record/annotation: extract component info
   - If method: extract method with containing class
   - Otherwise: skip to next sibling
5. For extracted components:
   - Generate unique component ID (file path + component name)
   - Create Node object with metadata
   - Add to accumulating nodes list
6. Recursively process children and continue traversal

### Relationship Extraction Workflow

**Process Steps**:
1. Walk through AST tree for relationship nodes
2. Check node type and dispatch to appropriate handler:
   - **Class nodes**: Check for inheritance (extends superclass)
   - **Class/Enum/Record nodes**: Check for interface implementation
   - **Field declarations**: Extract field type dependencies
   - **Method invocations**: Analyze method calls on objects
   - **Object creation**: Analyze new object instantiations
   - **Other nodes**: Skip relationship analysis
3. For identified relationships:
   - Resolve the target type (class, interface, etc.)
   - Filter out primitive and built-in types
   - Create CallRelationship with source and target
   - Add to accumulating relationships list
4. Continue traversal to process all nodes

## Performance Characteristics

### Time Complexity
- **Node Extraction**: O(n) where n = number of AST nodes
- **Relationship Detection**: O(n) with additional lookups for variable type resolution
- **Variable Type Resolution**: O(m) where m = nodes in containing scope (optimized through block-level search)

### Space Complexity
- **Nodes Storage**: O(k) where k = number of components extracted
- **Relationships Storage**: O(r) where r = number of relationships found
- **Tree-Sitter AST**: O(n) automatically managed by parser

### Optimization Strategies
1. Single-pass AST traversal for both node and relationship extraction
2. Early filtering of primitive types to reduce relationship count
3. Localized variable type search within method/class scope
4. Recursive descent prevents unbounded traversal

## Error Handling

### Handled Scenarios
- Missing or malformed Java files
- Invalid Tree-Sitter parse results (gracefully degraded)
- Missing type information (defaults to unresolved relationships)
- Primitive type filtering prevents spurious dependencies

### Logging
The analyzer uses Python's `logging` module with configurable log levels:
```python
logger = logging.getLogger(__name__)
```

Debug logs include:
- Missing superclass information
- Node extraction details
- Type resolution steps

## Limitations & Edge Cases

### Known Limitations

1. **Type Resolution**: Cannot fully resolve types without import information
   - Only handles local variables and fields
   - Cross-module types marked as unresolved
   - Type parameters and generic resolution is basic

2. **Visibility Scope**: Cannot determine method visibility or access modifiers impact
   - All detected calls treated equally regardless of public/private scope

3. **Dynamic Types**: Cannot resolve dynamic dispatch or reflection-based calls
   - Static analysis limitations inherent to the approach

4. **Complex Generics**: Generic type parameter resolution is simplified
   - Nested generics may not be fully resolved

### Edge Cases Handled

- **Abstract classes**: Detected and labeled with "abstract class" type
- **Inner/nested classes**: Component IDs include parent class references
- **Method overloading**: Methods distinguished only by name (signature not fully captured)
- **Generic types**: Basic extraction of base type from generic_type nodes
- **Multi-interface implementation**: Correctly handles comma-separated interface list

## Examples

### Example 1: Class Inheritance Analysis

**Input Java Code**:
```java
public abstract class Animal {
    public abstract void makeSound();
}

public class Dog extends Animal {
    @Override
    public void makeSound() {
        System.out.println("Woof");
    }
}
```

**Extracted Components**:
```
Node(id="file.java::Animal", name="Animal", type="abstract class")
Node(id="file.java::Dog", name="Dog", type="class")
Node(id="file.java::Animal.makeSound", name="Animal.makeSound", type="method")
Node(id="file.java::Dog.makeSound", name="Dog.makeSound", type="method")
```

**Extracted Relationships**:
```
CallRelationship(caller="file.java::Dog", callee="file.java::Animal")
```

### Example 2: Interface Implementation with Field Dependencies

**Input Java Code**:
```java
public interface Logger {
    void log(String message);
}

public class ConsoleLogger implements Logger {
    private PrintWriter writer;
    
    @Override
    public void log(String message) {
        writer.println(message);
    }
}
```

**Extracted Relationships**:
```
CallRelationship(caller="file.java::ConsoleLogger", callee="file.java::Logger")
CallRelationship(caller="file.java::ConsoleLogger", callee="PrintWriter")
```

### Example 3: Method Call Analysis

**Input Java Code**:
```java
public class Service {
    private Repository repository;
    
    public void process() {
        List<Data> data = repository.findAll();
    }
}

public class Repository {
    public List<Data> findAll() { ... }
}
```

**Extracted Relationships**:
```
CallRelationship(caller="file.java::Service", callee="Repository")
CallRelationship(caller="file.java::Service.process", callee="Repository")
```

## Testing Recommendations

### Unit Test Coverage Areas

1. **Node Extraction**
   - Class, interface, enum, record, annotation detection
   - Method extraction with containing class identification
   - Abstract class modifier detection

2. **Relationship Detection**
   - Single and multiple inheritance chains
   - Interface implementation (single and multiple)
   - Field type dependencies
   - Method invocation patterns
   - Object creation expressions

3. **Type Resolution**
   - Local variable type inference
   - Field type resolution
   - Generic type handling
   - Primitive type filtering

4. **Path Generation**
   - Relative path calculation
   - Component ID generation
   - Module path conversion

### Integration Test Scenarios

- Multi-file Java projects with cross-file dependencies
- Complex inheritance hierarchies
- Generics and parameterized types
- Nested and inner classes

## Related Components

- **[dependency_analyzer_models.md](dependency_analyzer_models.md)**: Data models used by analyzer
- **[dependency_analysis_services.md](dependency_analysis_services.md)**: Higher-level analysis orchestration
- **[language_analyzers.md](language_analyzers.md)**: Overview of all language analyzers
- **[c_analyzer.md](c_analyzer.md)**: C analyzer implementation reference
- **[cpp_analyzer.md](cpp_analyzer.md)**: C++ analyzer implementation reference
- **[csharp_analyzer.md](csharp_analyzer.md)**: C# analyzer implementation reference
- **[kotlin_analyzer.md](kotlin_analyzer.md)**: Kotlin analyzer implementation reference
- **[python_analyzer.md](python_analyzer.md)**: Python analyzer implementation reference
- **[javascript_analyzer.md](javascript_analyzer.md)**: JavaScript analyzer implementation reference
- **[typescript_analyzer.md](typescript_analyzer.md)**: TypeScript analyzer implementation reference
- **[php_analyzer.md](php_analyzer.md)**: PHP analyzer implementation reference

## Summary

The java_analyzer module provides robust Java code analysis through Tree-Sitter integration, extracting both Java language components and their interdependencies. It serves as a key component in the dependency analysis pipeline, enabling developers and tools to understand Java codebase structure and relationships.

By combining AST-based analysis with smart type resolution and relationship detection, the analyzer bridges the gap between low-level syntax and high-level semantic understanding of Java code.
