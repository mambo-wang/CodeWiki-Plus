# PHP Analyzer Module Documentation

## Overview

The **PHP Analyzer** module is a language-specific analyzer that extracts code structure and dependency information from PHP files using the tree-sitter-php parser. It is part of the [language_analyzers](language_analyzers.md) subsystem within the larger [dependency_analysis_services](dependency_analysis_services.md) framework.

### Purpose

The PHP Analyzer identifies and catalogues:
- **Structural elements**: Classes, interfaces, traits, enums, functions, and methods
- **Dependency relationships**: Use statements, class inheritance, interface implementation, object creation, and static method calls
- **Metadata**: Docstrings, parameters, return types, and base classes
- **Namespace resolution**: Fully qualified names through PHP's namespace and use mechanisms

### Key Characteristics

- **Tree-sitter based**: Uses tree-sitter-php for robust AST parsing (handles both pure PHP and PHP mixed with HTML)
- **Namespace-aware**: Resolves class names to fully qualified names accounting for use statements and namespaces
- **Recursion protected**: Includes safeguards against stack overflow with MAX_RECURSION_DEPTH
- **Template-aware**: Skips PHP template files (Blade, Twig, PHTML) that are not relevant for dependency analysis
- **Comprehensive relationships**: Extracts multiple dependency types including inheritance, implementation, instantiation, and static calls

---

## Core Components

### 1. NamespaceResolver

**Responsibility**: Resolves PHP class names to their fully qualified form considering namespace context and use statements.

**Key Methods**:
- `register_namespace(ns: str)`: Set the current namespace context
- `register_use(fqn: str, alias: str = None)`: Register a use statement with optional alias
- `resolve(name: str) -> str`: Resolve a name to its fully qualified form

**Behavior**:
- Maintains a mapping of aliases to fully qualified names (`use_map`)
- Handles both simple use statements (`use App\User;`) and group use statements (`use App\{User, Post};`)
- Resolves partial qualified names by checking the use map
- Prepends namespace context when resolving unqualified names
- Normalizes backslash escaping throughout resolution

**Example Flow**:
```
Input: namespace "App\Models", use "Illuminate\Database\Model as BaseModel"
resolve("BaseModel") → "Illuminate\Database\Model"
resolve("BaseModel\Factory") → "Illuminate\Database\Model\Factory"
resolve("\stdClass") → "stdClass"
```

### 2. TreeSitterPHPAnalyzer

**Responsibility**: Parses PHP files using tree-sitter and extracts nodes (classes, functions, methods) and their dependency relationships.

**Key Methods**:

#### Initialization & Analysis
- `__init__(file_path, content, repo_path)`: Initialize with file content
- `_analyze()`: Main entry point for parsing and analysis (three-pass approach)
- `_is_template_file()`: Determine if file should be skipped (Blade, Twig, PHTML patterns)

#### Namespace & Use Statement Processing
- `_extract_namespace_info(node)`: Extract namespace and use declarations (First Pass)
- `_extract_use_statement(node)`: Parse complex use statements including group syntax
- `_extract_nodes(node, lines, parent_class)`: Extract node definitions (Second Pass)

#### Relationship Extraction
- `_extract_relationships(node)`: Extract all dependency relationships (Third Pass)
- `_add_use_relationships(node)`: Add relationships for use statements
- Handles: extends, implements, new, static calls, property promotion

#### Supporting Methods
- `_get_component_id(name, parent_class)`: Generate unique component identifier
- `_get_relative_path()`: Calculate relative path from repository root
- `_find_containing_class_name(node)`: Traverse parent nodes to find enclosing class
- `_extract_parameters(node)`: Extract function/method parameter list
- `_extract_base_classes(node)`: Get parent classes and interfaces
- `_get_preceding_docstring(node, lines)`: Extract PHPDoc comments
- `_is_primitive(type_name)`: Check if type is built-in PHP type

**Data Structures**:
- `nodes: List[Node]` - Extracted structural elements
- `call_relationships: List[CallRelationship]` - Extracted dependency relationships
- `namespace_resolver: NamespaceResolver` - Instance for name resolution
- `_top_level_nodes: Dict[str, Node]` - Cache of extracted top-level definitions

---

## Architecture & Design

### Three-Pass Analysis Strategy

The analyzer uses a three-pass approach to ensure namespace and use statements are resolved before processing dependencies:

```
Pass 1: Extract Namespace Info
├─ Walk AST and find namespace_definition nodes
├─ Register current namespace with NamespaceResolver
├─ Find and register all use statements
└─ Build use_map for later name resolution

Pass 2: Extract Nodes
├─ Walk AST and identify structural elements
├─ For each: class, interface, trait, enum, function, method
├─ Create Node objects with metadata (docstring, parameters, base_classes)
└─ Cache top-level nodes in _top_level_nodes

Pass 3: Extract Relationships
├─ Walk AST and identify dependency patterns:
│  ├─ Use statements (imports)
│  ├─ Class inheritance (extends)
│  ├─ Interface implementation (implements)
│  ├─ Object creation (new)
│  ├─ Static method calls (::)
│  └─ Property promotion (PHP 8+)
├─ For each relationship, resolve names using namespace_resolver
└─ Create CallRelationship objects
```

### Component Integration

**Components and their roles**:

1. **tree-sitter-php Parser**: Parses PHP source code into AST
2. **NamespaceResolver**: Maintains namespace context and use statement mappings
3. **TreeSitterPHPAnalyzer**: Main orchestrator that:
   - Uses tree-sitter-php to parse files
   - Uses NamespaceResolver to resolve qualified names
   - Extracts Node objects from AST
   - Extracts CallRelationship objects from AST

**Output**: Tuple of (List[Node], List[CallRelationship])

### Data Flow

The analyzer follows a three-pass approach:

1. **Parsing Phase**: Content → tree-sitter-php Parser → AST Tree
2. **Namespace Resolution Phase**: AST → Extract namespace and use statements → NamespaceResolver setup
3. **Node Extraction Phase**: AST → Extract classes, methods, functions → List[Node]
4. **Relationship Extraction Phase**: AST + NamespaceResolver → Extract dependencies → List[CallRelationship]
5. **Return**: Tuple[List[Node], List[CallRelationship]] to caller

### Entity Relationships

**Core Components**:

- **Node**: Represents extracted structural elements (classes, methods, functions)
  - Fields: id, name, component_type, file_path, docstring, parameters, base_classes
  
- **CallRelationship**: Represents dependency relationships between components
  - Fields: caller, callee, call_line, is_resolved
  
- **NamespaceResolver**: Resolves class names to fully qualified names
  - Fields: current_namespace, use_map

**Relationships**:
- TreeSitterPHPAnalyzer uses NamespaceResolver for name resolution
- TreeSitterPHPAnalyzer extracts and creates Node objects
- TreeSitterPHPAnalyzer extracts and creates CallRelationship objects
- Nodes and CallRelationships work together to represent the code dependency graph

---

## Relationship Types Extracted

The PHP Analyzer identifies and extracts the following dependency relationships:

### 1. **Use Statements (Imports)**
- **Pattern**: `use Namespace\ClassName;`
- **Detected**: At file/namespace level
- **Relationship**: File imports external class
- **Example**: `use Illuminate\Database\Model;` → File depends on Model class

### 2. **Class Inheritance (Extends)**
- **Pattern**: `class Child extends Parent { }`
- **Detected**: In class declarations
- **Relationship**: Child class depends on Parent class
- **Example**: `class User extends Model` → User depends on Model

### 3. **Interface Implementation (Implements)**
- **Pattern**: `class MyClass implements MyInterface { }`
- **Detected**: In class/enum declarations
- **Relationship**: Implementing class depends on interface
- **Example**: `class Repository implements CacheableInterface` → Repository depends on CacheableInterface

### 4. **Object Creation (New)**
- **Pattern**: `$obj = new ClassName();`
- **Detected**: In object_creation_expression nodes
- **Relationship**: Caller depends on instantiated class
- **Example**: Within User class: `new Repository()` → User depends on Repository

### 5. **Static Method Calls (Scope Resolution)**
- **Pattern**: `ClassName::staticMethod();`
- **Detected**: In scoped_call_expression nodes
- **Relationship**: Caller depends on target class
- **Example**: Within Service: `Logger::log()` → Service depends on Logger

### 6. **Constructor Property Promotion (PHP 8+)**
- **Pattern**: `public function __construct(private UserRepository $repo) {}`
- **Detected**: In property_promotion_parameter nodes
- **Relationship**: Class depends on injected class type
- **Example**: Service with promoted property of type UserRepository → Service depends on UserRepository

---

## Primitive and Built-in Types

The analyzer maintains a comprehensive set of PHP primitives and built-in types to exclude from dependency relationships:

**Scalar Types**: `string`, `int`, `float`, `bool`, `array`, `object`, `callable`, `iterable`, `mixed`, `void`, `null`, `false`, `true`, `never`

**Special Keywords**: `self`, `static`, `parent`

**Common Built-in Classes**: `Exception`, `Error`, `Throwable`, `Closure`, `Generator`, `Iterator`, `stdClass`, `DateTime`, `ArrayObject`, etc.

These are excluded because they don't represent meaningful external dependencies.

---

## Template File Handling

The analyzer automatically skips template files that contain mostly markup:

**Extension Patterns**:
- `.blade.php` (Laravel Blade)
- `.phtml` (PHP with HTML)
- `.twig.php` (Twig template)

**Directory Patterns**:
- `views/`
- `templates/`
- `resources/views/`

This prevents spurious analysis of view files that contain primarily HTML with embedded PHP.

---

## Integration with Dependency Analysis System

### Upstream Dependencies

The PHP Analyzer is used by higher-level systems:

```
RepoAnalyzer (orchestrates all language analyzers)
    ├─ Delegates to: PHP Analyzer, Python Analyzer, JS Analyzer, ...
    └─ Collects results from all analyzers

PHP Analyzer produces:
    ├─ Node objects (classes, methods, functions)
    └─ CallRelationship objects (dependencies)

DependencyGraphBuilder (consumes analyzer output)
    ├─ Reads: Node and CallRelationship objects
    └─ Creates: Repository with complete dependency graph

AnalysisService returns:
    └─ AnalysisResult with full codebase dependency map
```

### Data Flow in System Context

```
User Request (via CLI/Web)
    ↓
RepoAnalyzer (dependency_analysis_services)
    ├─ For each PHP file:
    │  ├─ Read file content
    │  ├─ Call: analyze_php_file(path, content, repo_path)
    │  ├─ PHP Analyzer processes it
    │  │  ├─ Extracts nodes (classes, functions, methods)
    │  │  ├─ Extracts relationships (dependencies)
    │  │  └─ Returns: (List[Node], List[CallRelationship])
    │  └─ Store results
    │
    ├─ Aggregate all language results
    └─ Return to:
        DependencyGraphBuilder
            ↓
        Creates dependency graph structure
            ↓
        AnalysisService (dependency_analysis_services)
            ↓
        Returns AnalysisResult with full dependency map
```

### Public Interface

```python
# Main entry point for the PHP Analyzer
def analyze_php_file(
    file_path: str,           # Path to PHP file
    content: str,             # File contents
    repo_path: str = None     # Repository root for relative paths
) -> Tuple[List[Node], List[CallRelationship]]:
    """
    Analyze a PHP file and extract nodes and call relationships.
    
    Returns:
        Tuple of (extracted_nodes, dependency_relationships)
    """
    analyzer = TreeSitterPHPAnalyzer(file_path, content, repo_path)
    return analyzer.nodes, analyzer.call_relationships
```

---

## PHP-Specific Features

### Namespace Resolution

The analyzer handles PHP's namespace system:

```php
// File: app/Models/User.php
namespace App\Models;

use Illuminate\Database\Model;
use App\Services\UserService as UserSvc;

class User extends Model {
    // ...
}
```

**Resolution Process**:
1. Registers namespace: `App\Models`
2. Registers use: `Model` → `Illuminate\Database\Model`
3. Registers use: `UserSvc` → `App\Services\UserService`
4. When encountering `extends Model`:
   - Resolves `Model` to `Illuminate\Database\Model`
   - Creates relationship to `Illuminate.Database.Model`

### Qualified Names Handling

```php
// Fully qualified
new \Some\Namespace\Class();      // Resolved as-is

// Alias
use Some\Namespace\Class as Alias;
new Alias();                        // Resolved via use_map

// Partial qualified (first component aliased)
use Some\Namespace;
new Namespace\SubClass();           // Resolved by expanding alias

// Unqualified (namespace prepended)
namespace My\App;
new LocalClass();                   // Resolved as My\App\LocalClass
```

### Modern PHP Features

The analyzer supports PHP 8+ features:

**Constructor Property Promotion**:
```php
class Service {
    public function __construct(
        private UserRepository $repo,  // Type hint creates dependency
        private Logger $logger
    ) {}
}
```

**Named Types** (PHP 7.4+):
```php
public function getUserById(int $id): User {
    // Extracts User type as dependency
}
```

**Union and Intersection Types** (PHP 8.0+):
```php
public function process(User|Admin $entity): void {}
```

---

## Error Handling & Robustness

### RecursionError Protection

```python
MAX_RECURSION_DEPTH = 100

# Used in all recursive methods:
def _extract_nodes(self, node, lines, depth=0, parent_class=None):
    if depth > MAX_RECURSION_DEPTH:
        logger.warning(f"Max recursion depth reached in {self.file_path}")
        return
    # ... process node ...
    for child in node.children:
        self._extract_nodes(child, lines, depth + 1, parent_class)
```

### Exception Handling

```python
def _analyze(self):
    try:
        # Parse and analyze
        ...
    except RecursionError:
        logger.warning(f"Max recursion depth exceeded in {self.file_path}")
    except Exception as e:
        logger.error(f"Error parsing PHP file {self.file_path}: {e}")
```

### Validation

- **Primitive type checking**: Excludes analysis of built-in types
- **Template file detection**: Skips non-code files
- **Node validation**: Only creates nodes when both type and name are present
- **Relationship validation**: Filters out self-references and primitives

---

## Performance Considerations

### Optimizations

1. **Early template file detection**: Skip analysis before parsing for non-code files
2. **Single tree-sitter parse**: One parse per file (not multiple)
3. **Lazy docstring extraction**: Only when specifically needed
4. **Caching of top-level nodes**: `_top_level_nodes` dict for quick lookup
5. **String normalization**: Backslash normalization once at resolution time

### Complexity

- **Time Complexity**: O(n) where n = AST node count (linear traversal with bounded depth)
- **Space Complexity**: O(m) where m = number of extracted nodes and relationships

### Scalability

- Handles PHP files efficiently via tree-sitter (C/C++ based)
- Bounded recursion depth prevents stack issues
- No external API calls or I/O during analysis
- Suitable for analyzing large codebases with thousands of PHP files

---

## Configuration & Customization

### PHP Primitives Extension

Modify `PHP_PRIMITIVES` set to extend built-in types:

```python
PHP_PRIMITIVES: Set[str] = {
    "string", "int", "float", "bool", "array", "object",
    # ... add custom framework-specific types to exclude
}
```

### Template Directory Patterns

Modify `TEMPLATE_DIRECTORIES` to skip additional directories:

```python
TEMPLATE_DIRECTORIES: Set[str] = {
    "views", "templates", "resources/views",
    # Add custom pattern: "admin/templates"
}
```

### Recursion Depth

Adjust `MAX_RECURSION_DEPTH` for deeply nested structures:

```python
MAX_RECURSION_DEPTH = 100  # Increase if needed (default: 100)
```

---

## Related Modules

- **[dependency_analysis_services](dependency_analysis_services.md)**: Orchestrates all language-specific analyzers
- **[language_analyzers](language_analyzers.md)**: Overview of all language-specific analyzers (Python, JavaScript, TypeScript, Java, C, C++, C#, Kotlin)
- **[dependency_analyzer_models](dependency_analyzer_models.md)**: Core data models (Node, CallRelationship, Repository)
- **[dependency_graph_construction](dependency_graph_construction.md)**: Constructs dependency graphs from extracted nodes
- **[dependency_analyzer_utils](dependency_analyzer_utils.md)**: Shared logging and utilities

---

## Usage Example

### Direct Analysis

```python
from codewiki.src.be.dependency_analyzer.analyzers.php import analyze_php_file

php_code = """
<?php
namespace App\Models;

use Illuminate\Database\Model;
use App\Services\UserService;

class User extends Model {
    public function __construct(
        private UserService $service
    ) {}
}
"""

file_path = "app/Models/User.php"
repo_path = "/home/project"

nodes, relationships = analyze_php_file(php_code, file_path, repo_path)

# nodes contains:
# - Node(name="User", component_type="class", ...)

# relationships contains:
# - CallRelationship(caller="app/Models/User::User", 
#                   callee="Illuminate.Database.Model", ...)
# - CallRelationship(caller="app/Models/User", 
#                   callee="App.Services.UserService", ...)
```

### Integration with Analysis Service

```python
from codewiki.src.be.dependency_analyzer.analysis.analysis_service import AnalysisService

service = AnalysisService()
result = service.analyze("/path/to/project", language="php")

# result.nodes: all PHP nodes found
# result.relationships: all PHP dependencies
# result.call_graph: complete dependency graph
```

---

## Summary

The **PHP Analyzer** is a robust, language-specific component that extracts structural and dependency information from PHP codebases. Through a three-pass analysis strategy and comprehensive namespace resolution, it accurately identifies classes, functions, methods, and their dependency relationships while handling PHP-specific features and filtering out non-relevant elements. It integrates seamlessly with the broader dependency analysis system to enable complete codebase understanding.
