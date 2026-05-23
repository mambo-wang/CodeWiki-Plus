# CLI Core Module Documentation

## Overview

The **CLI Core** module (`cli_core`) is the command-line interface backbone of CodeWiki, orchestrating the entire documentation generation workflow. It bridges user-facing CLI operations with backend services, managing configuration, Git integration, progress reporting, and documentation output generation.

### Module Purpose

CLI Core provides:
- **Configuration Management**: Secure credential storage with keyring integration and fallback mechanisms
- **Documentation Orchestration**: Coordinates dependency analysis, module clustering, and documentation generation
- **Git Integration**: Manages branch creation, commits, and remote operations for documentation
- **Progress Tracking**: Real-time CLI feedback on long-running operations
- **Output Generation**: Creates both Markdown documentation and interactive HTML viewers

### Key Responsibilities

1. **User Configuration** → Accept and validate user settings
2. **Dependency Analysis** → Coordinate source code parsing and dependency graph building
3. **Documentation Generation** → Orchestrate backend doc generation with progress reporting
4. **HTML Output** → Generate static GitHub Pages viewers
5. **Git Automation** → Optionally commit documentation to feature branches

---

## Architecture Overview

### Component Relationships

**CLI Core Module Structure:**

```
┌─────────────────────────────────────────────────────┐
│              User / CLI Command                      │
└────────────────────┬────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
   ┌─────────────┐         ┌─────────────┐
   │ ConfigMgr   │         │  DocGen     │
   │ (Config &   │         │ (Orchestr.) │
   │ Credentials)│         └────────┬────┘
   └─────────────┘                  │
        │                    ┌──────┼──────┐
        │          ┌─────────┘      │      └──────┐
        │          │                │             │
        ▼          ▼                ▼             ▼
    ┌────────┐  ┌────────┐    ┌────────┐   ┌─────────┐
    │ Models │  │Backend │    │GitMgr  │   │HTMLGen  │
    │ & Utils│  │Services│    │(Git Op)│   │(Output) │
    └────────┘  └────────┘    └────────┘   └─────────┘
        │          │                               │
        └──────────┴───────────────────────────────┘
                   │
                   ▼
            ┌──────────────┐
            │ Output Files │
            │ (.md, .json, │
            │  .html)      │
            └──────────────┘
```

### Module Dependencies

**Core Components:**
- **ConfigManager**: Configuration & credential management
- **CLIDocumentationGenerator**: Main orchestrator (5-stage pipeline)
- **GitManager**: Git operations (branch creation, commits)
- **HTMLGenerator**: Static HTML viewer generation

**Depends On:**
- `cli_models` - Configuration, Job, LLM models
- `cli_utils` - Logging, progress tracking, error handling
- `llm_backends` - LLM provider integration
- `documentation_generation` - Doc generation logic
- `dependency_analysis_services` - Code analysis

---

## Component Details

### 1. ConfigManager

**Purpose**: Secure credential and configuration management with intelligent fallback mechanisms.

**Key Features**:
- **Keyring Integration**: Uses system keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)
- **File Fallback**: Graceful degradation to `~/.codewiki/credentials.json` when keyring unavailable
- **Force File Mode**: `CODEWIKI_NO_KEYRING=1` environment variable for headless containers
- **Validation**: Automatic config validation when sufficient fields are provided
- **Provider-Aware**: Different validation rules for CAW vs API-based providers

**Storage Structure**:
```
~/.codewiki/
├── config.json           # Main config (base_url, models, etc.)
└── credentials.json      # Fallback for API key (plaintext, mode 0600)
```

**Data Flow**:

```
User loads config:
  1. Read ~/.codewiki/config.json (settings)
  2. Load API key from system keyring
     ├─ Success: Use keyring value
     └─ Fail: Try ~/.codewiki/credentials.json
  3. Return Configuration object
```

**Configuration Model**:
- `base_url`: LLM API endpoint
- `main_model`: Primary LLM for documentation
- `cluster_model`: Model for module clustering
- `fallback_model`: Backup model
- `provider`: "openai-compatible", "anthropic", "bedrock", "azure-openai"
- `agent_instructions`: Custom instructions for agents
- Token limits, depth limits, output directory

### 2. CLIDocumentationGenerator

**Purpose**: Main orchestrator coordinating documentation generation with real-time progress feedback.

**Generation Pipeline (5 Stages)**:

```
Stage 1: Dependency Analysis
  ├─ Parse source files
  ├─ Build dependency graph
  └─ Identify leaf nodes

Stage 2: Module Clustering
  ├─ Cluster related components (LLM)
  ├─ Create module hierarchy
  └─ Save module tree (cached)

Stage 3: Documentation Generation
  ├─ Generate per-module documentation
  ├─ Create overview files
  └─ Generate metadata.json

Stage 4: HTML Generation (optional)
  ├─ Load module tree
  ├─ Load metadata
  └─ Generate index.html

Stage 5: Finalization
  ├─ Verify metadata
  └─ Mark job as complete
```

**Key Responsibilities**:

1. **Configuration Translation**
   - Converts CLI config to backend config
   - Sets up logging and context

2. **Progress Orchestration**
   - Manages 5-stage progress tracking
   - Provides real-time feedback to user

3. **Backend Coordination**
   ```python
   # Stage 1: Dependency Analysis
   components, leaf_nodes = graph_builder.build_dependency_graph()
   
   # Stage 2: Module Clustering
   module_tree = cluster_modules(leaf_nodes, components, config)
   
   # Stage 3: Documentation Generation
   await doc_generator.generate_module_documentation(...)
   
   # Stage 4: HTML Generation (optional)
   html_generator.generate(output_path, ...)
   
   # Stage 5: Finalization
   verify_metadata()
   ```

4. **Error Handling**
   - Catches API errors and re-raises as CLI-friendly messages
   - Updates job status on failure

**Job Lifecycle**:

```
Created → Pending
   ↓
Pending → Running (on generate())
   ├─ Success → Completed → Done
   ├─ Error → Failed → Done
   └─ Progress updates (loop back to Running)
```

### 3. GitManager

**Purpose**: Seamless Git integration for optional documentation commits and branch management.

**Capabilities**:

- **Repository Detection**: Validates that working directory is a Git repo
- **Branch Creation**: Creates timestamped documentation branches (`docs/codewiki-YYYYMMDD-HHMMSS`)
- **Status Checking**: Ensures clean working directory before operations
- **Documentation Commits**: Commits generated documentation with proper messages
- **Remote Detection**: Identifies GitHub URLs and generates PR links

**Branch Strategy**:

```
Main Branch (main)
  ├─ Initial commits
  └─ Feature development
     
Documentation Branch (docs/codewiki-YYYYMMDD-HHMMSS)
  ├─ Add generated documentation
  ├─ Add module_tree.json
  └─ Add metadata.json
  
Then optionally merge back to main via PR
```

**Working Directory Check**:

```
User calls: create_documentation_branch()
  ↓
GitManager checks: is_dirty(untracked_files=True)
  ├─ Clean (no changes)
  │  └─ Create branch, return success
  └─ Dirty (uncommitted changes)
     └─ Error: Clean working directory first
        (User must commit or stash changes)
```

### 4. HTMLGenerator

**Purpose**: Creates self-contained, static HTML documentation viewers for GitHub Pages deployment.

**Features**:

- **Template-Based**: Uses template system for HTML generation
- **Auto-Loading**: Automatically loads `module_tree.json` and `metadata.json` from docs directory
- **Embedded Assets**: Includes styles, scripts, and configuration inline
- **Repository Detection**: Extracts GitHub repo info and generates Pages URL
- **Metadata Rendering**: Displays generation info in viewer UI

**Template Variables**:
```
{{TITLE}}              → Documentation title
{{REPO_LINK}}          → Repository link
{{SHOW_INFO}}          → Show/hide info section
{{INFO_CONTENT}}       → Repository/generation info
{{CONFIG_JSON}}        → Embedded config
{{MODULE_TREE_JSON}}   → Embedded module structure
{{METADATA_JSON}}      → Embedded metadata
{{DOCS_BASE_PATH}}     → Relative path to docs folder
```

**Output Generation Flow**:

```
Documentation Directory
  ├─ module_tree.json ──┐
  └─ metadata.json ────┐
                       ↓
HTML Template ──→ Combine ──→ index.html
                       ↑        (Complete Viewer)
  Config ─────────────┘
```

---

## Data Flow Diagrams

### Complete Generation Workflow

**Execution Flow:**

```
User Input: codewiki generate --repo /path
  ↓
1. Load Configuration
   ConfigManager.load() → Configuration object
  ↓
2. Initialize Documentation Generator
   DocGen.__init__(repo_path, config)
  ↓
3. Run Backend Generation
   ├─ Stage 1: Dependency Analysis
   │  └─ build_dependency_graph() → components, leaf_nodes
   │
   ├─ Stage 2: Module Clustering
   │  └─ cluster_modules() → module_tree
   │
   └─ Stage 3: Documentation Generation
      └─ generate_module_documentation() → .md files, metadata.json
  ↓
4. Optional: HTML Generation (if --generate-html)
   └─ HTMLGenerator.generate() → index.html
  ↓
5. Optional: Git Integration (if --create-branch)
   ├─ create_documentation_branch() → branch_name
   └─ commit_documentation() → commit_hash
  ↓
Output: DocumentationJob(completed)
Message: ✅ Documentation generated
```

### Configuration Loading Flow

```
User requests: config.load()
  ↓
Check: ~/.codewiki/config.json exists?
  ├─ No  → Return empty configuration
  └─ Yes → Load JSON file
     ↓
     Check: Keyring available?
       ├─ No  → Load from file
       └─ Yes → Try get API key from keyring
                ├─ Success → Use keyring value
                └─ Fail    → Try ~/. codewiki/credentials.json
                            ├─ Success → Use file value
                            └─ Fail    → Return (without API key)
```

### Module Tree Generation and Caching

**Optimization: Smart Caching**

```
Stage 2: Module Clustering (Input: leaf_nodes, components)
  ↓
Check: first_module_tree.json exists in cache?
  ├─ Yes (Cache Hit)
  │  └─ Load cached module tree (skip LLM call)
  │
  └─ No (Cache Miss)
     ├─ Call clustering LLM on leaf nodes
     ├─ Create module tree structure
     └─ Save as first_module_tree.json (cache)
        └─ Also save as module_tree.json (working)
  ↓
Output: Ready for Stage 3
```

---

## Component Interaction Matrix

| Component | ConfigManager | CLIDocGen | GitManager | HTMLGenerator |
|-----------|---------------|-----------|-----------|----------------|
| **ConfigManager** | — | Provides config | N/A | N/A |
| **CLIDocGen** | Reads config | — | Calls for Git ops | Calls to generate HTML |
| **GitManager** | N/A | Called by | — | N/A |
| **HTMLGenerator** | N/A | Calls to generate HTML | N/A | — |

---

## Key Design Patterns

### 1. **Adapter Pattern**
`CLIDocumentationGenerator` adapts the backend `DocumentationGenerator`, adding CLI-specific features like progress tracking and error handling without modifying the backend.

```python
# Backend provides pure documentation logic
doc_generator = DocumentationGenerator(config)
components, leaf_nodes = doc_generator.graph_builder.build_dependency_graph()

# CLI adapter wraps it with progress feedback
self.progress_tracker.update_stage(0.5, "Parsed source files")
```

### 2. **Configuration as Code**
Configuration is loaded from persistent storage and can be overridden per-command, allowing both global defaults and command-specific customization.

```python
# Load global config
config_mgr.load()

# Apply CLI overrides
config_mgr.save(base_url=args.base_url, main_model=args.model)
```

### 3. **Progress Callback Pattern**
Real-time feedback is provided through a progress tracker that can be consumed by CLI, logging, or monitoring systems.

```python
progress_tracker.start_stage(1, "Dependency Analysis")
progress_tracker.update_stage(0.5, "Analyzing dependencies...")
progress_tracker.complete_stage()
```

### 4. **Fallback/Degradation**
Critical functionality has fallback mechanisms to prevent single points of failure:

```
Primary: System Keyring
└─ Fallback: File-based storage (~/.codewiki/credentials.json)
   └─ Fallback: Environment variable (CODEWIKI_API_KEY)
```

### 5. **Lazy Loading**
Assets are loaded only when needed:

```python
# HTML generator auto-loads module_tree and metadata from docs_dir
html_generator.generate(docs_dir=output_dir)
# Internally loads module_tree.json and metadata.json
```

---

## Integration with Other Modules

### CLI Models (`cli_models`)
CLI Core uses data models for:
- **Configuration**: `Configuration`, `AgentInstructions`
- **Jobs**: `DocumentationJob`, `JobStatus`, `JobStatistics`
- **LLM Config**: `LLMConfig` with model and endpoint details

**See**: [cli_models.md](cli_models.md) for model structures

### CLI Utils (`cli_utils`)
CLI Core depends on utilities:
- **Logging**: `CLILogger` for structured logging
- **Progress**: `ProgressTracker`, `ModuleProgressBar` for real-time feedback
- **Errors**: `ConfigurationError`, `APIError`, `RepositoryError`

**See**: [cli_utils.md](cli_utils.md) for utility details

### LLM Backends (`llm_backends`)
CLI Core delegates to:
- **Backend Selection**: `LLMBackend` abstract interface
- **Implementations**: `CawBackend`, `PydanticAIBackend` for different providers
- **Model Compatibility**: `CompatibleOpenAIModel` for provider compatibility

**See**: [llm_backends.md](llm_backends.md) for backend architecture

### Documentation Generation (`documentation_generation`)
Backend module providing:
- **Core Logic**: `DocumentationGenerator` handles module doc generation
- **Dependency Analysis**: Parses code, builds graphs
- **Module Clustering**: Groups related files
- **Metadata Creation**: Generates documentation metadata

**See**: [documentation_generation.md](documentation_generation.md) for generation pipeline

### Dependency Analysis Services (`dependency_analysis_services`)
Provides code analysis capabilities:
- **Repo Analysis**: `RepoAnalyzer` for repository structure
- **Call Graph Analysis**: `CallGraphAnalyzer` for function/method dependencies
- **Language Analyzers**: Tree-sitter based parsers for multiple languages

**See**: [dependency_analysis_services.md](dependency_analysis_services.md) for analysis details

---

## Error Handling

### Error Hierarchy

```
Exception (Base)
  └─ CLIError (Custom Base for CodeWiki)
     ├─ ConfigurationError (config loading/validation issues)
     ├─ APIError (LLM API failures, timeouts)
     ├─ RepositoryError (Git repository issues)
     └─ FileSystemError (I/O, permissions, file not found)
```

**Error Hierarchy Flow:**
- All CLI errors inherit from base `CLIError`
- Allows specific error handling per error type
- User-friendly error messages with actionable suggestions

### Error Scenarios

| Scenario | Error Type | Handling |
|----------|-----------|----------|
| Missing config file | `ConfigurationError` | Prompt user to run `codewiki config` |
| Invalid API credentials | `APIError` | Display error, suggest checking API key |
| Not a Git repository | `RepositoryError` | Suggest running `git init` |
| Write permission denied | `FileSystemError` | Check output directory permissions |
| LLM API timeout | `APIError` | Retry or use fallback model |

---

## Configuration Scenarios

### Scenario 1: First Time Setup

```bash
# User runs configuration wizard
$ codewiki config set --api-key sk-... --base-url https://api.openai.com

# ConfigManager:
# 1. Creates ~/.codewiki/ directory
# 2. Stores API key in system keyring
# 3. Saves other config to ~/.codewiki/config.json

$ codewiki generate --repo /path/to/repo
# ConfigManager loads existing config → no re-entry needed
```

### Scenario 2: Headless Container

```bash
# Container without X11/system keyring
$ CODEWIKI_NO_KEYRING=1 \
  CODEWIKI_API_KEY=sk-... \
  codewiki generate --repo /repo --output /docs

# ConfigManager:
# 1. Skips keyring (disabled via env)
# 2. Reads API key from CODEWIKI_API_KEY
# 3. Falls back to file storage if needed
```

### Scenario 3: Customized LLM Models

```bash
# Use different model for clustering
$ codewiki config set --main-model gpt-4 --cluster-model gpt-4-turbo

# ConfigManager validates:
# - Both models specified
# - Base URL configured
# - API key available
```

---

## Performance Characteristics

### Memory Usage

| Component | Typical Size |
|-----------|-------------|
| Configuration | < 1 KB |
| Module tree (1000 modules) | 50-100 KB |
| Dependency graph (10K files) | 50-200 MB |
| Documentation cache | 100+ MB (depends on codebase) |

### Time Complexity

| Operation | Time |
|-----------|------|
| Load config | O(1) |
| Validate config | O(1) |
| Dependency analysis | O(n) where n = files |
| Module clustering | O(k) where k = leaf nodes (LLM calls) |
| HTML generation | O(m) where m = modules |

### Optimization Strategies

1. **Caching**: Module tree cached to skip LLM calls on re-runs
2. **Lazy Loading**: Assets loaded only when needed
3. **Progress Batching**: Progress updates batched to reduce I/O
4. **File Streaming**: Large files processed incrementally

---

## Testing Strategy

### Unit Tests

```python
# Test ConfigManager
def test_config_manager_loads_existing():
    mgr = ConfigManager()
    assert mgr.load() == True

def test_config_manager_saves_securely():
    mgr = ConfigManager()
    mgr.save(api_key="test-key")
    # Verify API key in keyring, not on disk

# Test GitManager
def test_git_manager_validates_repo():
    mgr = GitManager("/path/to/repo")
    assert mgr.repo is not None

# Test HTMLGenerator
def test_html_generator_loads_module_tree():
    gen = HTMLGenerator()
    tree = gen.load_module_tree("/docs")
    assert isinstance(tree, dict)
```

### Integration Tests

```python
# Test full workflow
def test_documentation_generation_workflow():
    # Setup
    config = ConfigManager()
    config.save(api_key="test", base_url="...", models=...)
    
    # Execute
    doc_gen = CLIDocumentationGenerator(repo_path, output_dir, config)
    job = doc_gen.generate()
    
    # Verify
    assert job.status == JobStatus.COMPLETED
    assert (output_dir / "module_tree.json").exists()
    assert (output_dir / "metadata.json").exists()
```

---

## Future Enhancements

### Planned Features

1. **Incremental Generation**: Only re-document changed modules
2. **Parallel Processing**: Process modules in parallel for speed
3. **Custom Templates**: User-defined HTML templates
4. **Export Formats**: Support for Markdown variants, PDF, etc.
5. **CI/CD Integration**: GitHub Actions, GitLab CI workflows
6. **Multi-Language Support**: Documentation in multiple languages

### Architecture Improvements

1. **Plugin System**: Allow third-party adapters
2. **Async/Await**: Full async support for I/O operations
3. **Monitoring**: Metrics and telemetry integration
4. **Config Profiles**: Multiple saved configurations
5. **Dry-Run Mode**: Preview without generating files

---

## Summary

The **CLI Core** module is the orchestration hub of CodeWiki, providing:

✅ **Secure Configuration**: Keyring integration with intelligent fallbacks
✅ **Progress Tracking**: Real-time feedback during long operations
✅ **Workflow Orchestration**: Coordinates all documentation generation stages
✅ **Git Integration**: Seamless documentation commits to feature branches
✅ **Output Generation**: Creates both Markdown docs and interactive HTML viewers

**Key Design Principles**:
- **Separation of Concerns**: Adapter pattern keeps CLI separate from backend logic
- **Secure by Default**: Credential storage uses system keyring with fallbacks
- **Progressive Feedback**: Users see real-time progress on long operations
- **Fail Gracefully**: Fallback mechanisms prevent single points of failure
- **Modular Components**: Each component has a single, well-defined responsibility

**Integration Points**:
- ← Receives configuration from `cli_models`
- ← Uses logging/progress from `cli_utils`
- → Calls backend `documentation_generation` for core logic
- → Uses `llm_backends` for LLM interactions
- → Optional Git integration with `GitManager`
- → Optionally generates HTML with `HTMLGenerator`
