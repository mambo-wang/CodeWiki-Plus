# CLI Models Module Documentation

## Overview

The `cli_models` module defines the data models and configuration structures for the CodeWiki CLI. It serves as the bridge between user-facing CLI commands and the backend documentation generation system, providing:

- **Persistent Configuration Management**: User settings stored in `~/.codewiki/config.json`
- **Job Lifecycle Tracking**: Complete representation of documentation generation jobs
- **Configuration Bridge**: Conversion from CLI settings to backend configuration
- **Type-Safe Data Handling**: Dataclass-based models for type safety and serialization

This module is essential for maintaining separation of concerns between the CLI layer and the backend documentation generation system.

---

## Core Components

### 1. Configuration Models

#### `AgentInstructions`
Custom instructions for the documentation agent that allow fine-grained control over documentation generation.

**Key Responsibilities:**
- Define file filtering patterns (include/exclude)
- Specify module focus areas
- Set documentation type preferences
- Provide custom LLM instructions

**Key Methods:**
- `to_dict()` / `from_dict()`: Serialization for persistent storage
- `is_empty()`: Check if any instructions are defined
- `get_prompt_addition()`: Generate LLM prompt additions

**Configuration Options:**
```python
- include_patterns: List[str]          # e.g., ["*.cs", "*.py"]
- exclude_patterns: List[str]          # e.g., ["*Tests*", "*Specs*"]
- focus_modules: List[str]             # e.g., ["src/core", "src/api"]
- doc_type: str                        # api, architecture, user-guide, developer
- custom_instructions: str             # Free-form instructions
```

#### `Configuration`
Persistent CodeWiki CLI configuration stored in `~/.codewiki/config.json`.

**Key Responsibilities:**
- Store LLM provider settings (base URL, models, API keys)
- Manage token limits and generation parameters
- Maintain default output directory
- Validate all configuration fields
- Convert to backend `Config` for documentation generation

**Key Attributes:**
- **LLM Settings**: `base_url`, `main_model`, `cluster_model`, `fallback_model`, `provider`
- **Provider Specifics**: `aws_region`, `api_version`, `azure_deployment`
- **Token Limits**: `max_tokens`, `max_token_per_module`, `max_token_per_leaf_module`
- **Generation Parameters**: `max_depth`, `default_output`
- **Custom Instructions**: `agent_instructions` (AgentInstructions)

**Key Methods:**
- `validate()`: Validates all fields based on provider type
- `is_complete()`: Checks if required fields are set
- `to_backend_config()`: Converts CLI config to backend Config for a specific job

**Provider Support:**
- OpenAI-compatible (default)
- Azure OpenAI
- AWS Bedrock
- Anthropic (claude-code, codex - subscription mode)

---

### 2. Job Models

#### `JobStatus`
Enumeration tracking the lifecycle of a documentation generation job.

**States:**
- `PENDING`: Job created, awaiting execution
- `RUNNING`: Job actively generating documentation
- `COMPLETED`: Job finished successfully
- `FAILED`: Job encountered an error

#### `GenerationOptions`
Options controlling how documentation is generated for a specific job.

**Options:**
- `create_branch`: Create a git branch for generated docs
- `github_pages`: Generate GitHub Pages compatible documentation
- `no_cache`: Skip caching, force regeneration
- `custom_output`: Override default output directory

#### `JobStatistics`
Metrics collected during documentation generation.

**Metrics:**
- `total_files_analyzed`: Number of source files processed
- `leaf_nodes`: Number of leaf modules identified
- `max_depth`: Maximum depth of module hierarchy
- `total_tokens_used`: Total tokens consumed by LLM

#### `LLMConfig`
Snapshot of LLM configuration used for a specific job.

**Captured Settings:**
- `main_model`: Primary model used
- `cluster_model`: Model used for module clustering
- `base_url`: LLM API endpoint

#### `DocumentationJob`
Complete representation of a documentation generation job from creation to completion.

**Core Attributes:**
- **Identification**: `job_id` (UUID), `repository_name`, `repository_path`
- **Git Context**: `commit_hash`, `branch_name`
- **Output**: `output_directory`, `files_generated`
- **Execution**: `status`, `timestamp_start`, `timestamp_end`
- **Error Handling**: `error_message`
- **Configuration**: `generation_options`, `llm_config`
- **Results**: `module_count`, `statistics`

**Key Methods:**
- `start()`: Mark job as running, record start time
- `complete()`: Mark job as completed, record end time
- `fail()`: Mark job as failed, record error message
- `to_dict()` / `from_dict()`: Serialization for storage/retrieval
- `to_json()`: Generate JSON representation

**Lifecycle:**
```
Created (PENDING) → Start → Running → Complete/Fail → COMPLETED/FAILED
```

---

## Architecture & Data Flow

### Configuration Conversion Flow

The module provides a critical bridge between CLI configuration and backend execution:

```
Persistent Configuration (~/.codewiki/config.json)
    ↓
Configuration
    ├── base_url, models, provider settings
    ├── token limits, generation parameters
    └── agent_instructions (AgentInstructions)
    ↓
to_backend_config() [with runtime parameters]
    ↓
Backend Config (from shared_config_and_utils)
    ├── repo_path, output_dir
    ├── api_key, llm_base_url
    ├── model selections, token limits
    └── merged agent_instructions
    ↓
Documentation Generation Backend
    └── llm_backends, documentation_generation
```

### Job Execution Flow

```
Job Creation
    ↓ (status = PENDING)
Job Start
    ↓ (status = RUNNING, timestamp_start set)
Documentation Generation
    ├── LLM generates documentation
    └── Metrics accumulated
    ↓
Success or Failure
    ├── complete()  → COMPLETED
    └── fail()      → FAILED
```

### Component Relationships

```
Configuration Model
    ├── AgentInstructions
    │   ├── include_patterns, exclude_patterns
    │   ├── focus_modules, doc_type
    │   └── custom_instructions
    └── Conversion Method: to_backend_config()
        └── Creates Backend Config with
            ├── Merged instructions
            ├── Repository context
            └── LLM credentials

DocumentationJob
    ├── JobStatus (enum)
    ├── GenerationOptions
    ├── LLMConfig (snapshot)
    ├── JobStatistics
    └── Serialization Methods
        ├── to_dict(), from_dict()
        └── to_json()
```

### Architecture Diagrams

#### 1. Configuration Models Composition

```
Configuration
├── AgentInstructions (custom filters and instructions)
├── LLM Settings (base_url, models, provider)
├── Token Limits (max_tokens, max_token_per_module)
├── Generation Parameters (max_depth, default_output)
└── Serialization Methods
    ├── to_dict() → JSON for ~/.codewiki/config.json
    ├── from_dict() → Load from config file
    └── to_backend_config() → Convert to Backend Config
```

#### 2. Job Lifecycle States

```
PENDING (created)
    ↓ job.start()
RUNNING (executing)
    ├─ job.complete() → COMPLETED (success)
    └─ job.fail(message) → FAILED (error)

DocumentationJob contains:
- JobStatus (state enum)
- LLMConfig (model snapshot)
- GenerationOptions (job settings)
- JobStatistics (execution metrics)
```

#### 3. Integration Architecture

```
cli_models Module
    ├── Configuration ──→ cli_core/ConfigManager
    │                     (reads/writes ~/.codewiki/config.json)
    │
    ├── DocumentationJob ──→ cli_core/CLIDocumentationGenerator
    │                       cli_utils/CLILogger, ProgressTracker
    │
    └── to_backend_config() ──→ Backend System
                                (documentation generation)
```

#### 4. Configuration Conversion Pipeline

```
Input:
  - Persistent Configuration (from ~/.codewiki/config.json)
  - Runtime Parameters (repo path, output directory)
  - API Key (from keyring/environment)

Processing:
  1. Load Configuration
  2. Validate fields (provider-specific)
  3. Merge agent instructions (runtime overrides persistent)
  4. Inject credentials
  5. Create Backend Config

Output:
  - Backend Config (ready for documentation generation)
  - Preserves API key securely
  - Maintains audit trail
```

---

## Key Design Patterns

### 1. **Configuration Persistence & Conversion**
- CLI `Configuration` persists user settings independently
- `to_backend_config()` creates a runtime configuration with:
  - Job-specific parameters (repo path, output directory)
  - Merged agent instructions (runtime + persistent)
  - Validated credentials and settings

### 2. **Job Lifecycle Tracking**
- Complete state machine representation
- Immutable fields at creation time
- Mutable fields during execution
- Comprehensive serialization for audit trails

### 3. **Type Safety & Validation**
- Dataclass-based models for type hints
- Field validation in `Configuration.validate()`
- Provider-specific validation logic
- Safe enum-based status representation

### 4. **Separation of Concerns**
- CLI models independent of backend implementation
- Job metadata separate from documentation content
- Configuration separate from execution context
- Statistics separate from core job tracking

---

## Integration Points

### With `cli_core`
- **ConfigManager**: Reads/writes `Configuration` from/to `~/.codewiki/config.json`
- **CLIDocumentationGenerator**: Uses `Configuration` to create `DocumentationJob`
- **GitManager**: Updates `DocumentationJob` with git context

### With `shared_config_and_utils`
- **Config**: Receives converted `Configuration` via `to_backend_config()`
- **Backend System**: Uses converted `Config` for actual generation

### With `llm_backends`
- **LLMBackend**: Receives `LLMConfig` snapshot for initialization
- **Provider Initialization**: Uses provider-specific fields from `Configuration`

### With `cli_utils`
- **CLILogger**: Logs job status transitions
- **ProgressTracker**: Tracks job execution progress

---

## Usage Examples

### Loading Persistent Configuration

```python
from codewiki.cli.config_manager import ConfigManager
from codewiki.cli.models.config import Configuration

# Load from ~/.codewiki/config.json
config_mgr = ConfigManager()
config: Configuration = config_mgr.load()

# Validate before use
config.validate()
```

### Converting to Backend Configuration

```python
# Create job with runtime overrides
job = DocumentationJob(
    repository_path="/path/to/repo",
    repository_name="my-repo",
    output_directory="docs"
)

# Convert CLI config to backend config
backend_config = config.to_backend_config(
    repo_path=job.repository_path,
    output_dir=job.output_directory,
    api_key=api_key_from_keyring,
    runtime_instructions=None  # or custom AgentInstructions
)

# backend_config now ready for documentation generation
```

### Job Lifecycle Management

```python
# Create and start job
job = DocumentationJob(
    repository_path="/path/to/repo",
    repository_name="my-repo",
    output_directory="docs"
)
job.start()  # Sets status to RUNNING, timestamp_start

# During generation
job.files_generated.append("README.md")
job.statistics.total_files_analyzed = 42

# On completion
job.complete()  # Sets status to COMPLETED, timestamp_end

# Or on failure
job.fail("Insufficient tokens for module clustering")

# Serialize for storage
job_json = job.to_json()
```

### Custom Agent Instructions

```python
from codewiki.cli.models.config import AgentInstructions

instructions = AgentInstructions(
    doc_type="api",
    focus_modules=["src/api", "src/models"],
    exclude_patterns=["*_test.py", "*Tests*"],
    custom_instructions="Emphasize error handling patterns"
)

# Generate prompt addition for LLM
prompt_addition = instructions.get_prompt_addition()
# → "Focus on API documentation: endpoints, parameters...\n
#    Pay special attention to: src/api, src/models\n
#    ..."
```

---

## Data Storage Format

### Configuration File Format (~/.codewiki/config.json)

```json
{
  "base_url": "https://api.example.com/v1",
  "main_model": "gpt-4-turbo",
  "cluster_model": "gpt-4",
  "fallback_model": "glm-4p5",
  "default_output": "docs",
  "provider": "openai-compatible",
  "aws_region": "us-east-1",
  "api_version": "2024-12-01-preview",
  "azure_deployment": "",
  "max_tokens": 32768,
  "max_token_per_module": 36369,
  "max_token_per_leaf_module": 16000,
  "max_depth": 2,
  "agent_instructions": {
    "include_patterns": ["*.py", "*.ts"],
    "exclude_patterns": ["*test*", "*__pycache__*"],
    "focus_modules": ["src/core"],
    "doc_type": "architecture",
    "custom_instructions": "Focus on system design"
  }
}
```

### Job Status File Format

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "repository_path": "/home/user/my-repo",
  "repository_name": "my-repo",
  "output_directory": "/home/user/my-repo/docs",
  "commit_hash": "abc123def456",
  "branch_name": "main",
  "timestamp_start": "2024-05-23T10:30:00.000000",
  "timestamp_end": "2024-05-23T11:45:30.000000",
  "status": "completed",
  "error_message": null,
  "files_generated": ["README.md", "ARCHITECTURE.md", "API.md"],
  "module_count": 8,
  "generation_options": {
    "create_branch": false,
    "github_pages": true,
    "no_cache": false,
    "custom_output": null
  },
  "llm_config": {
    "main_model": "gpt-4-turbo",
    "cluster_model": "gpt-4",
    "base_url": "https://api.example.com/v1"
  },
  "statistics": {
    "total_files_analyzed": 156,
    "leaf_nodes": 12,
    "max_depth": 3,
    "total_tokens_used": 125000
  }
}
```

---

## Provider-Specific Configuration

### OpenAI-Compatible
```python
Configuration(
    base_url="https://api.openai.com/v1",
    main_model="gpt-4-turbo",
    cluster_model="gpt-4",
    fallback_model="gpt-3.5-turbo",
    provider="openai-compatible"
)
```

### Azure OpenAI
```python
Configuration(
    base_url="https://{resource}.openai.azure.com/",
    main_model="gpt-4-deployment",
    cluster_model="gpt-4-deployment",
    provider="azure-openai",
    api_version="2024-12-01-preview",
    azure_deployment="my-deployment"
)
```

### AWS Bedrock
```python
Configuration(
    main_model="anthropic.claude-3-sonnet-20240229-v1:0",
    cluster_model="anthropic.claude-3-haiku-20240307-v1:0",
    provider="bedrock",
    aws_region="us-east-1"
)
```

### Anthropic (Subscription Mode)
```python
Configuration(
    main_model="claude-code",  # or "codex"
    provider="anthropic"
    # No base_url, cluster_model, or fallback_model required
)
```

---

## Error Handling

The module handles several validation scenarios:

### Configuration Validation
- Provider-specific field requirements
- Model name format validation
- URL format validation for API endpoints
- Required field presence checks

### Job State Transitions
- State machine enforcement (PENDING → RUNNING → COMPLETED/FAILED)
- Error recording with descriptive messages
- Timestamp consistency validation

### Provider-Specific Logic
- Subscription-mode providers (claude-code, codex) require only `main_model`
- Traditional API providers require `base_url`, `cluster_model`, `fallback_model`
- Validation adapts based on `provider` field value

---

## Performance Considerations

### Configuration Merging
- Runtime instructions override persistent settings
- Merging only occurs when explicitly requested
- Efficient to_dict() conversion for serialization

### Job Serialization
- JSON format optimized for storage and transmission
- UUID generation is lazy (on-demand)
- Statistics accumulated incrementally during execution

### Memory Usage
- Dataclass instances are lightweight
- No persistent connections or resources held
- Serialization creates copies only when needed

---

## Security Considerations

1. **API Key Management**
   - Configuration stores `base_url` but NOT the API key
   - API key retrieved from secure keyring at runtime
   - Passed to `to_backend_config()` only when needed

2. **Credential Handling**
   - Job serialization never includes credentials
   - LLMConfig stores only configuration, not keys
   - Backend `Config` handles credential injection

3. **File Patterns**
   - Include/exclude patterns in AgentInstructions for filtering sensitive paths
   - Patterns processed before repository analysis

---

## Testing Considerations

### Mock Configuration
```python
@pytest.fixture
def mock_config():
    return Configuration(
        base_url="http://localhost:8000",
        main_model="mock-model",
        cluster_model="mock-cluster",
        fallback_model="mock-fallback"
    )
```

### Job State Testing
```python
def test_job_lifecycle():
    job = DocumentationJob(
        repository_path="/test/repo",
        repository_name="test-repo"
    )
    assert job.status == JobStatus.PENDING
    
    job.start()
    assert job.status == JobStatus.RUNNING
    
    job.complete()
    assert job.status == JobStatus.COMPLETED
```

### Serialization Testing
```python
def test_job_serialization():
    job = DocumentationJob(...)
    json_str = job.to_json()
    restored = DocumentationJob.from_dict(json.loads(json_str))
    assert job.job_id == restored.job_id
```

---

## Related Documentation

- [cli_core.md](cli_core.md) - CLI command execution and orchestration
- [shared_config_and_utils.md](shared_config_and_utils.md) - Backend configuration system
- [llm_backends.md](llm_backends.md) - LLM provider implementation
- [documentation_generation.md](documentation_generation.md) - Core generation engine
