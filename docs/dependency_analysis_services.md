# Dependency Analysis Services Module

## Overview

The **dependency_analysis_services** module is a comprehensive repository analysis system that orchestrates multi-language code parsing, call graph generation, and repository structure analysis. It serves as the core engine for understanding code dependencies and relationships across diverse programming languages.

**Primary Purpose**: Enable automated analysis of GitHub repositories to extract function definitions, call relationships, and visual representations of code structure across 9+ programming languages.

**Key Capabilities**:
- Multi-language AST parsing and call graph generation
- Repository structure analysis with intelligent filtering
- Cross-language function relationship resolution
- Visualization-ready graph data generation
- GitHub repository cloning and automated cleanup

---

## Architecture Overview

The module consists of three main components working together:

**AnalysisService** (Main Orchestrator)
- Coordinates the complete analysis workflow
- Manages repository cloning and cleanup
- Delegates structure analysis to RepoAnalyzer
- Delegates call graph analysis to CallGraphAnalyzer

**CallGraphAnalyzer** (Multi-Language Coordinator)
- Routes files to language-specific analyzers
- Consolidates results from all languages
- Resolves function call relationships
- Generates visualization data

**RepoAnalyzer** (Structure Analysis)
- Builds file tree with pattern-based filtering
- Validates file paths for security
- Provides file and size statistics

---

## Core Components

### 1. AnalysisService

**Responsibility**: Central orchestrator for the complete analysis workflow.

**Key Methods**:

#### `analyze_repository_full(github_url, include_patterns, exclude_patterns)`
Performs comprehensive repository analysis including call graph generation.

**Workflow**:
1. Clones GitHub repository to temporary directory
2. Parses repository information from URL
3. Analyzes repository structure with filtering
4. Performs multi-language call graph analysis
5. Consolidates results into AnalysisResult object
6. Cleans up temporary files

**Returns**: `AnalysisResult` with:
- Repository metadata
- Function definitions
- Call relationships
- File tree structure
- Visualization data
- README content (if available)

#### `analyze_repository_structure_only(github_url, include_patterns, exclude_patterns)`
Lightweight structure-only analysis without call graph generation.

**Use Cases**:
- Quick repository exploration
- Codebase size assessment
- File distribution analysis

**Returns**: Dictionary with repository info and file tree

#### `analyze_local_repository(repo_path, max_files, languages)`
Analyzes an already-cloned local repository.

**Features**:
- No network operations required
- Optional language filtering
- File count limiting for performance

**Data Flow**:

1. Client calls `analyze_repository_full(url)` on AnalysisService
2. AnalysisService clones repository to temporary directory
3. RepoAnalyzer analyzes file structure and returns file tree
4. CallGraphAnalyzer extracts code files from file tree
5. For each file, language-specific analyzer parses content
6. CallGraphAnalyzer consolidates all functions and relationships
7. CallGraphAnalyzer resolves function call relationships
8. CallGraphAnalyzer deduplicates call relationships
9. AnalysisService cleans up temporary directory
10. Client receives AnalysisResult with all analysis data

---

### 2. CallGraphAnalyzer

**Responsibility**: Multi-language call graph orchestration and function relationship analysis.

**Key Features**:

#### Code File Extraction
```python
extract_code_files(file_tree) → List[Dict]
```
- Filters files based on supported extensions
- Extracts language information
- Returns structured code file list

**Supported Extensions**: `.py`, `.js`, `.ts`, `.java`, `.kt`, `.cs`, `.c`, `.cpp`, `.php`, etc.

#### Multi-Language Analysis

Routes files to appropriate language-specific analyzers:

```
JavaScript/TypeScript → tree-sitter analyzer
Python → AST analyzer
Java/Kotlin → tree-sitter analyzer
C/C++/C# → tree-sitter analyzer
PHP → tree-sitter analyzer + namespace resolution
```

#### Function Relationship Resolution

**Resolution Strategy**:
1. Build lookup table with multiple keys per function:
   - Full ID (file path + function name)
   - Short name
   - Component ID
2. Match function calls to definitions using available keys
3. Mark resolved vs unresolved relationships

#### Visualization Generation

Produces **Cytoscape.js-compatible** graph data:

```json
{
  "cytoscape": {
    "elements": [
      {
        "data": {
          "id": "file.py:function_name",
          "label": "function_name",
          "file": "path/to/file.py",
          "type": "function",
          "language": "python"
        },
        "classes": ["node-function", "lang-python"]
      },
      {
        "data": {
          "id": "caller->callee",
          "source": "file.py:caller",
          "target": "file.py:callee",
          "line": 42
        },
        "classes": ["edge-call"]
      }
    ]
  },
  "summary": {
    "total_nodes": 150,
    "total_edges": 243,
    "unresolved_calls": 12
  }
}
```

---

### 3. RepoAnalyzer

**Responsibility**: Repository structure analysis with intelligent file filtering.

**Key Features**:

#### Security Measures
- ✓ Rejects symlinks to prevent traversal attacks
- ✓ Validates paths don't escape repository root
- ✓ Permission error handling

#### File Tree Building

```python
_build_file_tree(repo_dir) → Dict
```

**Structure**:
```json
{
  "type": "directory",
  "name": "repo_root",
  "path": ".",
  "children": [
    {
      "type": "file",
      "name": "main.py",
      "path": "src/main.py",
      "extension": ".py",
      "_size_bytes": 1024
    }
  ]
}
```

#### Pattern-Based Filtering

**Include Patterns** (DEFAULT):
```python
["*.py", "*.js", "*.ts", "*.java", "*.kt", "*.cs", "*.c", "*.cpp", "*.php", "*.go", "*.rs"]
```
- Customizable per instance
- If specified, replaces defaults entirely

**Exclude Patterns** (DEFAULT):
```python
[".*", "*/.*", "node_modules/*", "__pycache__/*", ".git/*", "*.egg-info/*", "dist/*", "build/*", "venv/*"]
```
- Customizable per instance
- Merges with defaults

**Filter Logic**:
1. Check relative path against exclude patterns
2. Check filename against exclude patterns
3. Validate directory escaping
4. For files: verify against include patterns

---

## Multi-Language Support

### Supported Languages

| Language | Analyzer Type | Status |
|----------|---------------|--------|
| Python | AST (ast module) | ✓ Stable |
| JavaScript | tree-sitter | ✓ Stable |
| TypeScript | tree-sitter | ✓ Stable |
| Java | tree-sitter | ✓ Stable |
| Kotlin | tree-sitter | ✓ Stable |
| C# | tree-sitter | ✓ Stable |
| C | tree-sitter | ✓ Stable |
| C++ | tree-sitter | ✓ Stable |
| PHP | tree-sitter + namespace resolver | ✓ Stable |

### Language Analyzer Architecture

**CallGraphAnalyzer** routes files to language-specific analyzers:

- **Python files** → PythonASTAnalyzer (using Python AST module)
- **JavaScript/TypeScript files** → TreeSitterJSAnalyzer (tree-sitter)
- **Java files** → TreeSitterJavaAnalyzer (tree-sitter)
- **Kotlin files** → TreeSitterKotlinAnalyzer (tree-sitter)
- **C# files** → TreeSitterCSharpAnalyzer (tree-sitter)
- **C files** → TreeSitterCAnalyzer (tree-sitter)
- **C++ files** → TreeSitterCppAnalyzer (tree-sitter)
- **PHP files** → TreeSitterPHPAnalyzer (tree-sitter + NamespaceResolver)

Each analyzer extracts function definitions and call relationships, which are consolidated into a unified set of Function Nodes and CallRelationships.

### Function Extraction Data Model

All analyzers return:
```python
Tuple[List[Node], List[CallRelationship]]

# Node represents a function/method
Node:
  - id: str              # Unique identifier
  - name: str            # Function name
  - file_path: str       # Source file path
  - node_type: str       # 'function', 'method', 'class_method'
  - parameters: List[str]    # Parameter names
  - docstring: Optional[str] # Documentation
  - component_id: str    # Path::ClassName::methodName

# CallRelationship represents a function call
CallRelationship:
  - caller: str          # Calling function ID
  - callee: str          # Called function name (may be unresolved)
  - call_line: int       # Line number of call
  - is_resolved: bool    # Whether callee matched to definition
```

---

## Processing Pipeline

The analysis workflow follows these sequential steps:

1. **Repository Cloning** - Clone GitHub repository to temporary directory
2. **URL Parsing** - Extract owner, repository name, and URL from GitHub URL
3. **Structure Analysis** - Analyze file tree with include/exclude filtering
4. **File Extraction** - Extract code files organized by language
5. **Language Analysis** - Route files to language-specific analyzers in parallel
   - Python files → AST analysis
   - JS/TS files → tree-sitter analysis
   - Java files → tree-sitter analysis
   - PHP files → tree-sitter + namespace resolver
   - C/C++/C# files → tree-sitter analysis
6. **Result Consolidation** - Merge functions and relationships from all languages
7. **Relationship Resolution** - Match function calls to definitions
8. **Deduplication** - Remove duplicate call relationships
9. **Visualization** - Generate Cytoscape.js-compatible graph data
10. **Cleanup** - Remove temporary directory
11. **Return Results** - Package into AnalysisResult object

---

## Error Handling & Resilience

### Timeout Protection

Individual file analysis is protected with 30-second timeout:
- Prevents hangs on very large or problematic files
- Platform-aware (Unix signal-based, Windows-compatible)
- Logs warning and continues to next file

### Per-File Error Handling

```python
# Each file analysis wrapped in try-catch
try:
    self._analyze_code_file(repo_dir, file_info)
    files_analyzed += 1
except Exception as e:
    files_failed += 1
    logger.warning(f"Failed to analyze {file_path}: {str(e)}")
    # Continue with next file
```

### Repository Cleanup

- Tracks all temporary directories
- Automatic cleanup on AnalysisService destruction
- Explicit `cleanup_all()` method available
- Defensive error handling during cleanup

### Language Filtering Safety

- Silently skips unsupported languages
- Reports unsupported file counts in summary
- Continues analysis with supported languages

---

## Integration with System

### Dependent Modules

**Input Dependencies**:
- `language_analyzers` - Provides language-specific AST parsing functions
- `dependency_analyzer_models` - Provides Node and CallRelationship data models
- `dependency_analyzer_utils` - Provides utility functions and patterns

**Output Dependencies**:
- `documentation_generation` - Consumes AnalysisResult to generate documentation
- `dependency_graph_construction` - Uses analysis data for graph operations

### Output Integration

AnalysisResult feeds into:
1. **documentation_generation**: Uses functions, relationships, and file tree to generate documentation
2. **Frontend**: Visualization data rendered in web UI via Cytoscape.js
3. **API Responses**: Serialized for JSON response to clients

---

## Usage Patterns

### Pattern 1: Full Repository Analysis

```python
from codewiki.src.be.dependency_analyzer.analysis.analysis_service import AnalysisService

service = AnalysisService()
result = service.analyze_repository_full(
    github_url="https://github.com/user/repo",
    include_patterns=["*.py", "*.js"],
    exclude_patterns=["*test*", "*spec*"]
)

# Access results
print(f"Functions: {len(result.functions)}")
print(f"Relationships: {len(result.relationships)}")
print(f"Visualization ready: {result.visualization is not None}")
```

### Pattern 2: Structure-Only Analysis

```python
result = service.analyze_repository_structure_only(
    github_url="https://github.com/user/repo"
)

# Quick overview without call graph
print(f"Total files: {result['file_summary']['total_files']}")
print(f"File tree: {result['file_tree']}")
```

### Pattern 3: Local Repository Analysis

```python
result = service.analyze_local_repository(
    repo_path="/path/to/local/repo",
    max_files=50,
    languages=["python", "javascript"]
)

# Fast analysis of pre-cloned repository
print(f"Nodes: {len(result['nodes'])}")
print(f"Relationships: {len(result['relationships'])}")
```

---

## Configuration & Customization

### Include/Exclude Patterns

**RepoAnalyzer** constructor:
```python
analyzer = RepoAnalyzer(
    include_patterns=["*.py", "src/**/*.py"],  # Only these files
    exclude_patterns=["*test*", "__pycache__"]  # Additionally ignore these
)
```

**Pattern Matching**:
- Uses `fnmatch` for glob pattern matching
- Supports `*`, `?`, `[seq]`, `[!seq]`
- Directory patterns can use `/` separator

### Language Filtering

```python
# Analyze only specific languages
result = service.analyze_local_repository(
    repo_path="/path/to/repo",
    languages=["python", "javascript"]  # Skip other languages
)
```

---

## Performance Characteristics

### Analysis Time Complexity

- **Repository Cloning**: O(repository_size)
- **Structure Analysis**: O(file_count)
- **Call Graph Analysis**: O(file_count + function_count)
- **Visualization Generation**: O(node_count + edge_count)

### Optimization Strategies

1. **Per-File Timeout**: 30 seconds per file prevents pathological cases
2. **Selective Language Analysis**: Only analyze supported languages
3. **File Count Limiting**: `max_files` parameter for large repositories
4. **Lazy Loading**: Visualization generated only when needed
5. **Deduplication**: Reduces relationship graph size

### Typical Metrics

For a medium repository (1000 files, 500 functions):
- Structure analysis: ~2-5 seconds
- Call graph analysis: ~10-20 seconds
- Visualization generation: <1 second
- Cleanup: <1 second
- **Total**: ~15-30 seconds

---

## Data Models

### AnalysisResult

```python
@dataclass
class AnalysisResult:
    repository: Repository           # Repository metadata
    functions: List[Node]            # All extracted functions
    relationships: List[CallRelationship]  # Function calls
    file_tree: Dict[str, Any]        # Nested file structure
    summary: Dict[str, Any]          # Statistics
    visualization: Dict[str, Any]    # Cytoscape data
    readme_content: Optional[str]    # README from repo
```

### Node (Function Definition)

```python
@dataclass
class Node:
    id: str                          # Unique identifier
    name: str                        # Function/method name
    file_path: str                   # Source file path
    node_type: str                   # 'function' | 'method'
    line_number: int                 # Definition line
    parameters: List[str]            # Parameter names
    docstring: Optional[str]         # Documentation
    component_id: Optional[str]      # Qualified name
```

### CallRelationship

```python
@dataclass
class CallRelationship:
    caller: str                      # Calling function ID
    callee: str                      # Called function name
    call_line: int                   # Line of call
    is_resolved: bool                # Matched to definition?
```

---

## Common Workflows

### Workflow 1: Extract and Document Repository

```python
service = AnalysisService()

# 1. Analyze repository
result = service.analyze_repository_full("https://github.com/example/project")

# 2. Use with documentation generator (from documentation_generation module)
from codewiki.src.be.documentation_generator import DocumentationGenerator

gen = DocumentationGenerator()
doc = gen.generate_documentation(
    analysis_result=result,
    module_name="example.project"
)

# 3. Clean up
service.cleanup_all()
```

### Workflow 2: Analyze Repository Structure and Filter

```python
service = AnalysisService()

# 1. Get structure only
structure = service.analyze_repository_structure_only(
    github_url="https://github.com/example/project",
    exclude_patterns=["**/test/**", "**/*_test.py"]
)

# 2. Inspect file distribution
files_by_language = {}
for file_info in structure['file_tree']['children']:
    lang = file_info.get('extension')
    files_by_language[lang] = files_by_language.get(lang, 0) + 1

print(f"File distribution: {files_by_language}")
```

### Workflow 3: Multi-Language Analysis

```python
service = AnalysisService()

# Analyze repository with mixed languages
result = service.analyze_repository_full("https://github.com/example/monorepo")

# Access language-specific metrics
summary = result.summary
print(f"Languages found: {summary['languages_analyzed']}")
print(f"Unsupported files: {summary.get('unsupported_files', 0)}")
print(f"Functions extracted: {summary['total_functions']}")

# Visualization includes language information
for element in result.visualization['cytoscape']['elements']:
    if 'language' in element['data']:
        print(f"{element['data']['label']} ({element['data']['language']})")
```

---

## Testing Considerations

### Unit Test Strategy

1. **AnalysisService Tests**:
   - Repository cloning simulation
   - Temporary directory cleanup
   - Error handling on invalid URLs

2. **CallGraphAnalyzer Tests**:
   - File extraction filtering
   - Language routing
   - Relationship resolution logic
   - Deduplication correctness

3. **RepoAnalyzer Tests**:
   - Pattern matching accuracy
   - Security validation (symlink rejection)
   - File tree structure correctness
   - Size calculations

### Integration Test Strategy

1. Small test repositories with known structures
2. Multi-language test repositories
3. Repositories with various edge cases:
   - Very large files
   - Symlinks
   - Permission errors
   - Complex module relationships

---

## Troubleshooting

### Issue: Timeout on Large Files

**Symptom**: "File parsing exceeded 30s timeout"

**Solution**:
- Increase timeout in `timeout()` context manager
- Use `max_files` parameter to limit scope
- Exclude problematic files with `exclude_patterns`

### Issue: Unresolved Call Relationships

**Symptom**: High `unresolved_calls` count in visualization

**Causes**:
- Cross-language calls (Python calling JS library)
- Dynamically resolved calls (`getattr`, `eval`)
- External library calls

**Mitigation**:
- Ensure include/exclude patterns capture all source files
- Check for namespace resolution issues in PHP analyzer
- Review function ID generation in language analyzers

### Issue: Missing Functions

**Symptom**: Expected functions not in results

**Verification**:
1. Check language is supported
2. Verify file matches include patterns
3. Check file wasn't excluded by exclude patterns
4. Review language analyzer logs for parse errors
5. Ensure proper file encoding (UTF-8)

---

## Related Documentation

- [language_analyzers](language_analyzers.md) - Language-specific parsing implementations
- [dependency_analyzer_models](dependency_analyzer_models.md) - Data models and structures
- [dependency_graph_construction](dependency_graph_construction.md) - Graph building utilities
- [documentation_generation](documentation_generation.md) - Doc generation from analysis results
- [dependency_analyzer_utils](dependency_analyzer_utils.md) - Utility functions and helpers

---

## Summary

The **dependency_analysis_services** module provides a robust, multi-language repository analysis platform that:

✓ **Orchestrates** complex multi-step analysis workflows  
✓ **Supports** 9+ programming languages with extensible architecture  
✓ **Generates** visualization-ready call graphs  
✓ **Handles** errors gracefully with per-file resilience  
✓ **Manages** resources with automatic cleanup  
✓ **Filters** intelligently with pattern-based inclusion/exclusion  
✓ **Integrates** seamlessly with documentation generation pipeline  

It serves as the analytical backbone of the CodeWiki system, transforming raw source code into structured, queryable function dependency information.
