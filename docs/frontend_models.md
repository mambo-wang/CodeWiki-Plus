# Frontend Models Module Documentation

## Overview

The `frontend_models` module provides data models and classes for the CodeWiki web application. It defines the core data structures used for repository submissions, job status tracking, and API responses. These models serve as the bridge between the frontend interface and backend processing logic.

**Location**: `codewiki/src/fe/models.py`

**Purpose**: Define Pydantic and dataclass models for type-safe data handling in the web application

**Key Responsibility**: 
- Validate incoming repository submission data
- Represent job status information throughout the documentation generation lifecycle
- Cache documentation results with metadata
- Provide structured API responses to frontend clients

---

## Architecture & Data Models

### Data Model Hierarchy

The module defines four core models that work together in a pipeline:

1. **RepositorySubmission** (Input) → validates incoming repository URLs
2. **JobStatus** (Processing) → tracks job lifecycle throughout execution
3. **JobStatusResponse** (API Output) → serializes job status for API clients
4. **CacheEntry** (Storage) → persists completed documentation results

**Data Flow**: RepositorySubmission triggers creation of JobStatus, which generates both JobStatusResponse for API clients and CacheEntry for caching completed results.

### Component Relationships

The components follow a layered architecture:

- **Input Layer**: `RepositorySubmission` validates and accepts user submissions
- **Processing Layer**: `JobStatus` maintains mutable state throughout the job lifecycle
- **Output Layers**:
  - `JobStatusResponse` provides JSON-serializable API responses
  - `CacheEntry` stores results for fast retrieval on future requests

---

## Component Details

### 1. RepositorySubmission

**Type**: Pydantic BaseModel  
**Purpose**: Validate and represent incoming repository submission requests

#### Definition
```python
class RepositorySubmission(BaseModel):
    """Pydantic model for repository submission form."""
    repo_url: HttpUrl
```

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `repo_url` | `HttpUrl` | The URL of the GitHub repository to document. Validated as a proper HTTP URL by Pydantic |

#### Usage Context
- **Entry Point**: Web form submission for initiating documentation generation
- **Validation**: Pydantic automatically validates that the input is a valid HTTP URL
- **Conversion**: Converted to `JobStatus` for internal processing
- **Related Component**: Used by `frontend_web_app` routes

#### Example
```python
submission = RepositorySubmission(repo_url="https://github.com/user/repo")
repo_url_str = str(submission.repo_url)  # Returns: "https://github.com/user/repo"
```

---

### 2. JobStatus

**Type**: Dataclass  
**Purpose**: Track the complete lifecycle of a documentation generation job

#### Definition
```python
@dataclass
class JobStatus:
    """Tracks the status of a documentation generation job."""
    job_id: str
    repo_url: str
    status: str  # 'queued', 'processing', 'completed', 'failed'
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    progress: str = ""
    docs_path: Optional[str] = None
    main_model: Optional[str] = None
    commit_id: Optional[str] = None
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_id` | `str` | ✓ | Unique identifier for the documentation job |
| `repo_url` | `str` | ✓ | The repository URL being processed |
| `status` | `str` | ✓ | Current job state: `'queued'`, `'processing'`, `'completed'`, or `'failed'` |
| `created_at` | `datetime` | ✓ | Timestamp when job was created |
| `started_at` | `datetime` | - | Timestamp when job processing started |
| `completed_at` | `datetime` | - | Timestamp when job completed |
| `error_message` | `str` | - | Error description if job failed |
| `progress` | `str` | ✓ | Current progress status message (default: `""`) |
| `docs_path` | `str` | - | Path to generated documentation on successful completion |
| `main_model` | `str` | - | LLM model used for generation |
| `commit_id` | `str` | - | Repository commit ID at time of documentation generation |

#### Status Lifecycle

The `JobStatus` object transitions through the following states:

1. **queued** - Initial state when job is created (`created_at` set, `started_at = None`)
2. **processing** - When processing starts (`started_at` set, progress messages updated)
3. **completed** - On successful completion (`completed_at` set, `docs_path` and `commit_id` set)
4. **failed** - On error during processing (`completed_at` set, `error_message` set)

Transitions:
- `queued` → `processing` when worker picks up the job
- `processing` → `completed` on successful documentation generation
- `processing` → `failed` when an error occurs

#### Usage Context
- **Lifecycle**: Created when job submitted, updated throughout processing
- **Storage**: Persisted in job queue and cache
- **Conversion**: Serialized to `JobStatusResponse` for API responses
- **Integration**: Referenced by `backend_worker`, `cache_manager`, and API routes

#### Key Methods / Properties
- **Mutable**: All fields can be updated as job progresses
- **Serialization**: Can be converted to `JobStatusResponse` for API output
- **Caching**: Used as basis for `CacheEntry` creation upon completion

---

### 3. JobStatusResponse

**Type**: Pydantic BaseModel  
**Purpose**: Provide structured API response for job status queries

#### Definition
```python
class JobStatusResponse(BaseModel):
    """Pydantic model for job status API response."""
    job_id: str
    repo_url: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    progress: str = ""
    docs_path: Optional[str] = None
    main_model: Optional[str] = None
    commit_id: Optional[str] = None
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_id` | `str` | ✓ | Unique job identifier |
| `repo_url` | `str` | ✓ | Repository URL |
| `status` | `str` | ✓ | Current job status |
| `created_at` | `datetime` | ✓ | Job creation timestamp |
| `started_at` | `datetime` | - | Processing start timestamp |
| `completed_at` | `datetime` | - | Processing completion timestamp |
| `error_message` | `str` | - | Error description if applicable |
| `progress` | `str` | ✓ | Progress message (default: `""`) |
| `docs_path` | `str` | - | Path to generated documentation |
| `main_model` | `str` | - | LLM model used |
| `commit_id` | `str` | - | Repository commit ID |

#### Relationship to JobStatus

The `JobStatusResponse` is derived directly from `JobStatus` fields:

- **JobStatus** (Internal): Used internally for tracking, mutable state, in-memory representation
- **JobStatusResponse** (API Output): Returned to client, JSON serializable, represents immutable API contract

All fields are copied directly from `JobStatus` when generating API responses, ensuring consistency between internal and external representations.

#### Usage Context
- **API Endpoint**: Returned when clients request job status
- **Serialization**: Automatically serialized to JSON by Pydantic
- **Validation**: Pydantic ensures all fields conform to expected types
- **Integration**: Used by `routes.py` in API responses

#### API Response Example
```json
{
    "job_id": "abc123",
    "repo_url": "https://github.com/user/repo",
    "status": "completed",
    "created_at": "2024-01-15T10:30:00Z",
    "started_at": "2024-01-15T10:31:00Z",
    "completed_at": "2024-01-15T10:45:00Z",
    "error_message": null,
    "progress": "Documentation generation completed",
    "docs_path": "/docs/user_repo_abc123.md",
    "main_model": "claude-3-opus",
    "commit_id": "abc123def456"
}
```

---

### 4. CacheEntry

**Type**: Dataclass  
**Purpose**: Represent a cached documentation result with metadata

#### Definition
```python
@dataclass
class CacheEntry:
    """Represents a cached documentation result."""
    repo_url: str
    repo_url_hash: str
    docs_path: str
    created_at: datetime
    last_accessed: datetime
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo_url` | `str` | ✓ | Original repository URL |
| `repo_url_hash` | `str` | ✓ | Hash of the URL for quick lookups (key for cache index) |
| `docs_path` | `str` | ✓ | File path to the cached documentation |
| `created_at` | `datetime` | ✓ | When documentation was generated |
| `last_accessed` | `datetime` | ✓ | Timestamp of most recent access (updated on cache hits) |

#### Usage Context
- **Purpose**: Enable fast retrieval of previously generated documentation
- **Storage**: Maintained by `CacheManager` in the cache layer
- **Access Pattern**: Looked up by `repo_url_hash` for O(1) retrieval
- **Lifecycle**: Created from completed `JobStatus`, stored indefinitely (or with TTL)
- **Integration**: Managed by `cache_manager.py` in `frontend_web_app`

#### Cache Flow

The caching lifecycle follows these steps:

1. **Job Completes**: When documentation generation succeeds, `docs_path` is set in `JobStatus`
2. **CacheEntry Created**: A new `CacheEntry` is created with the repo URL and generated docs path
3. **Cache Index**: Entry is indexed by `repo_url_hash` for O(1) lookups
4. **Fast Lookup**: Next request for the same repository finds the entry immediately
5. **Cache Hit**: Cached documentation is returned, `last_accessed` timestamp is updated

---

## Data Flow & Integration

### Complete Processing Pipeline

The documentation generation pipeline follows these steps:

1. **User Submits** → Repository URL submitted via web form
2. **Validation** → Pydantic validates URL format (RepositorySubmission)
3. **Job Creation** → Valid requests create JobStatus with status='queued'
4. **Job Queuing** → JobStatus stored in queue for asynchronous processing
5. **Backend Processing** → Worker retrieves job and starts documentation generation
6. **Status Update** → JobStatus updated to status='processing'
7. **Success Path**:
   - Documentation generation completes
   - JobStatus updated to status='completed' with docs_path set
   - JobStatusResponse created and sent to client
   - CacheEntry created and stored in cache
8. **Error Path**:
   - If error occurs, JobStatus updated to status='failed' with error_message
   - JobStatusResponse sent to client with error details
9. **API Response** → Final response converted to JSON and returned to client



### State Transitions & Data Updates

The system interactions follow this sequence:

**Initial Submission:**
1. Client sends POST /submit with RepositorySubmission
2. API routes validate repo_url field
3. API creates JobStatus with status='queued'
4. API returns JobStatus to client

**Background Processing:**
1. Worker retrieves next job from queue
2. Worker starts processing and updates JobStatus to status='processing'
3. Worker analyzes code structure and generates documentation
4. On completion, worker updates JobStatus to status='completed' with docs_path
5. Worker creates CacheEntry and stores it indexed by repo_url_hash

**Status Queries:**
1. Client can GET /status/{job_id} to check progress
2. API fetches current JobStatus from queue
3. API converts JobStatus to JobStatusResponse
4. Returns JSON response to client

**Cache Hits:**
1. When client resubmits same repository
2. API checks cache by repo_url_hash
3. If found, returns cached documentation immediately (no reprocessing needed)
4. Cache manager updates last_accessed timestamp

---

## Integration with Other Modules

### Dependencies

**Module Dependencies:**

- **Used By**: `frontend_web_app` - Web application layer that depends on these models
  - `routes.py` - Uses `RepositorySubmission` for input validation, `JobStatusResponse` for API responses
  - `cache_manager.py` - Uses `CacheEntry` to manage cached documentation results
  - `background_worker.py` - Updates `JobStatus` instances throughout job lifecycle

- **Uses**: External dependencies
  - `Pydantic` - For input validation (RepositorySubmission, JobStatusResponse)
  - Standard library: `datetime` (for timestamps), `typing` (for type hints), `dataclasses` (for JobStatus, CacheEntry)

### Related Modules

#### [frontend_web_app.md](frontend_web_app.md)
- **routes.py**: Uses `RepositorySubmission` for input validation and `JobStatusResponse` for API responses
- **cache_manager.py**: Creates and manages `CacheEntry` instances
- **background_worker.py**: Creates and updates `JobStatus` instances throughout job lifecycle

#### [cli_models.md](cli_models.md)
- Similar pattern with `DocumentationJob` and `JobStatus` for CLI operations
- Demonstrates parallel data model structures for different interfaces (web vs CLI)

#### [dependency_analyzer_models.md](dependency_analyzer_models.md)
- Lower-level data models for code analysis results
- Referenced indirectly through backend processing

---

## Type Safety & Validation

### Pydantic Validation Benefits

The use of Pydantic models (`RepositorySubmission`, `JobStatusResponse`) provides automatic validation:

**Validation Pipeline:**
1. **Raw HTTP Data** (String Input) → Received from client
2. **Pydantic Parsing** → Automatically parses input data
3. **Type Validation** → Validates field types
   - **URL Validation**: `HttpUrl` type ensures valid HTTP(S) URLs
   - **Type Conversion**: Converts JSON strings to Python datetime objects
   - **Error Handling**: Raises `ValidationError` on invalid data
4. **Output**:
   - ✓ **Valid**: Returns type-safe model instance
   - ✗ **Invalid**: Returns HTTP 422 (Unprocessable Entity) with validation errors

**Validation Benefits:**
- No manual URL format checking needed
- Automatic datetime parsing and conversion
- Type hints enable IDE autocompletion and mypy checking
- Descriptive error messages for invalid input
- Single source of truth for API contracts

### Type Hierarchy

```
BaseModel (Pydantic)
├── RepositorySubmission
│   └── repo_url: HttpUrl (Pydantic validated)
└── JobStatusResponse
    ├── job_id: str
    ├── repo_url: str
    ├── status: str
    ├── created_at: datetime
    ├── started_at: Optional[datetime]
    └── ... (other fields)

dataclass
├── JobStatus
│   ├── job_id: str
│   ├── status: str
│   ├── created_at: datetime
│   └── ... (other fields)
└── CacheEntry
    ├── repo_url: str
    ├── repo_url_hash: str
    ├── docs_path: str
    └── ... (timestamps)
```

---

## Use Cases & Examples

### Use Case 1: Initial Repository Submission

```python
from frontend_models import RepositorySubmission

# User submits form with repository URL
submission_data = {
    "repo_url": "https://github.com/python/cpython"
}

# Pydantic validates the URL format
submission = RepositorySubmission(**submission_data)  
# ✓ Valid, continues to job creation

# Invalid URL would raise ValidationError
invalid_data = {"repo_url": "not a url"}
submission = RepositorySubmission(**invalid_data)  
# ✗ Raises: ValidationError
```

### Use Case 2: Job Status Tracking

```python
from frontend_models import JobStatus
from datetime import datetime

# Create job when processing starts
job = JobStatus(
    job_id="job_abc123",
    repo_url="https://github.com/python/cpython",
    status="queued",
    created_at=datetime.now()
)

# Update as processing progresses
job.status = "processing"
job.started_at = datetime.now()
job.progress = "Analyzing code structure..."

# Mark completion
job.status = "completed"
job.completed_at = datetime.now()
job.docs_path = "/docs/python_cpython_abc123.md"
job.commit_id = "1a2b3c4d5e6f"
```

### Use Case 3: API Response Generation

```python
from frontend_models import JobStatus, JobStatusResponse

# Internal job tracking
job = JobStatus(...)

# Convert to API response (zero-copy field mapping)
response = JobStatusResponse(
    job_id=job.job_id,
    repo_url=job.repo_url,
    status=job.status,
    created_at=job.created_at,
    started_at=job.started_at,
    completed_at=job.completed_at,
    error_message=job.error_message,
    progress=job.progress,
    docs_path=job.docs_path,
    main_model=job.main_model,
    commit_id=job.commit_id
)

# Or via direct field mapping in routes.py
response_dict = {
    "job_id": job.job_id,
    "repo_url": job.repo_url,
    # ... all fields
}
response = JobStatusResponse(**response_dict)

# Automatically serialized to JSON
import json
json_output = response.model_dump_json()
```

### Use Case 4: Documentation Caching

```python
from frontend_models import CacheEntry, JobStatus
from datetime import datetime
import hashlib

# When job completes successfully
completed_job = JobStatus(
    job_id="job_abc123",
    repo_url="https://github.com/python/cpython",
    status="completed",
    created_at=datetime.now(),
    docs_path="/docs/python_cpython_abc123.md"
)

# Create cache entry
url_hash = hashlib.sha256(completed_job.repo_url.encode()).hexdigest()[:16]
cache_entry = CacheEntry(
    repo_url=completed_job.repo_url,
    repo_url_hash=url_hash,
    docs_path=completed_job.docs_path,
    created_at=completed_job.created_at,
    last_accessed=datetime.now()
)

# Store in cache (CacheManager)
cache[url_hash] = cache_entry

# Next time same repo is submitted
url_hash = hashlib.sha256("https://github.com/python/cpython".encode()).hexdigest()[:16]
if url_hash in cache:
    cached = cache[url_hash]
    # Return cached docs immediately (O(1) lookup)
```

---

## Error Handling

### Validation Errors

```python
from pydantic import ValidationError
from frontend_models import RepositorySubmission

# Invalid URL format
try:
    bad_submission = RepositorySubmission(repo_url="invalid")
except ValidationError as e:
    # Returns structured error details
    error_details = e.errors()
    # [{'loc': ('repo_url',), 'msg': 'invalid url format', 'type': 'url_scheme', ...}]
```

### Status Error Tracking

```python
from frontend_models import JobStatus
from datetime import datetime

# When error occurs during processing
job.status = "failed"
job.completed_at = datetime.now()
job.error_message = "Failed to clone repository: Connection timeout"

# Client receives error details via JobStatusResponse
```

---

## Performance Considerations

### Field Access
- **Dataclass fields**: O(1) direct attribute access
- **Pydantic fields**: O(1) with caching validation
- **Cache lookups**: O(1) via `repo_url_hash` in `CacheEntry`

### Memory Usage
- **JobStatus**: ~500 bytes per instance (small footprint)
- **CacheEntry**: ~300 bytes per instance
- Minimal overhead from Pydantic validation layer

### Serialization
- **JSON serialization**: Pydantic's `model_dump_json()` is optimized
- **Datetime handling**: ISO 8601 format for API compatibility

---

## Best Practices

### 1. Always Validate Input
```python
# ✓ Good: Use Pydantic validation
submission = RepositorySubmission(repo_url=user_input)

# ✗ Bad: Skip validation
repo_url = user_input  # Could contain invalid data
```

### 2. Use Dataclass for Internal State
```python
# ✓ Good: Use mutable dataclass for job tracking
job = JobStatus(...)
job.status = "processing"  # Easy to update

# ✗ Bad: Use immutable Pydantic for mutable state
job = JobStatusResponse(...)
job.status = "processing"  # Would require reconstruction
```

### 3. Convert for API Responses
```python
# ✓ Good: Explicit conversion to API model
job = JobStatus(...)
response = JobStatusResponse(**asdict(job))

# ✗ Bad: Return internal dataclass
return job  # Type contract unclear, serialization issues
```

### 4. Hash URLs for Cache Keys
```python
# ✓ Good: Use consistent hashing
hash = hashlib.sha256(repo_url.encode()).hexdigest()[:16]

# ✗ Bad: Use full URL as key
cache[repo_url] = entry  # Long keys, performance impact
```

---

## Summary

The `frontend_models` module provides essential data structures for the CodeWiki web application's repository submission and documentation generation workflow. The module offers:

- **Type Safety**: Pydantic models ensure input validation; dataclasses provide internal state management
- **Clear Contracts**: Distinct models for input (`RepositorySubmission`), processing (`JobStatus`), output (`JobStatusResponse`), and storage (`CacheEntry`)
- **Performance**: Simple field structures with O(1) access patterns and efficient hashing for cache lookups
- **Integration**: Seamless integration with `frontend_web_app` modules for routing, caching, and background processing

The separation of concerns—validation (Pydantic), state tracking (dataclass), and API contracts (Pydantic)—ensures a clean, maintainable architecture for the web application layer.
