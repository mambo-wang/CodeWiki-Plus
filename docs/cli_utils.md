# CLI Utils Module Documentation

## Module Overview

The `cli_utils` module provides essential utilities for the CLI layer, offering **user-friendly progress tracking** and **colored logging** capabilities. This module enhances the user experience during long-running documentation generation operations by providing real-time feedback on progress, time estimation, and status updates.

### Module Purpose
- **Logging**: Provide formatted, colored CLI output with multiple log levels (debug, info, success, warning, error)
- **Progress Tracking**: Monitor and visualize multi-stage documentation generation processes
- **Time Management**: Track elapsed time and estimate remaining time for operations
- **User Feedback**: Display step-by-step progress with visual indicators and status updates

### Key Characteristics
- **Dependency-light**: Uses only `click` library and Python standard library modules
- **Verbose Support**: Conditional detailed output for debugging
- **Color-coded Output**: Visual differentiation of log levels using ANSI colors
- **Stage-based Progress**: Structured progress tracking with weighted stages
- **ETA Estimation**: Intelligent estimation of remaining time based on current progress

---

## Component Architecture

### Core Components

#### 1. CLILogger
**File**: `codewiki/cli/utils/logging.py`

Provides formatted logging with colored output and multiple severity levels.

**Responsibilities**:
- Display debug messages (only in verbose mode)
- Show informational messages
- Highlight successes with green color and checkmark (✓)
- Display warnings with yellow color and warning symbol (⚠️)
- Show errors in red with cross symbol (✗)
- Track and display processing steps with progress indicators
- Calculate and report elapsed time

**Key Features**:
```
Log Levels:
├── debug()      → Cyan, dimmed (verbose only)
├── info()       → Default color
├── success()    → Green with ✓ prefix
├── warning()    → Yellow with ⚠️ prefix
├── error()      → Red with ✗ prefix (stderr)
├── step()       → Blue bold with step counter
└── elapsed_time()→ Formatted duration string
```

**Time Tracking**:
- Records initialization timestamp
- Calculates elapsed duration in human-readable format (e.g., "1m 30s")
- Supports queries for elapsed time at any point

---

#### 2. ProgressTracker
**File**: `codewiki/cli/utils/progress.py`

Manages multi-stage progress tracking with ETA estimation.

**Responsibilities**:
- Coordinate progress through 5 documentation generation stages
- Track progress within each stage (0.0 to 1.0)
- Calculate overall progress percentage
- Estimate time remaining (ETA)
- Display stage-specific information

**Stage Structure** (weighted time allocation):
```
Stage 1: Dependency Analysis       (40% of total time)
Stage 2: Module Clustering         (20% of total time)
Stage 3: Documentation Generation  (30% of total time)
Stage 4: HTML Generation           (5% of total time, optional)
Stage 5: Finalization              (5% of total time)
```

**Key Methods**:
- `start_stage(stage, description)`: Begin a new stage with optional custom description
- `update_stage(progress, message)`: Update progress (0.0-1.0) within current stage
- `complete_stage(message)`: Mark stage as complete
- `get_overall_progress()`: Calculate overall progress (0.0-1.0)
- `get_eta()`: Estimate remaining time
- `_format_elapsed()`: Format elapsed time as MM:SS

**Progress Calculation**:
- Combines completed stage weights with current stage progress
- Uses time-based estimation for ETA calculation
- Accounts for different stage durations

---

#### 3. ModuleProgressBar
**File**: `codewiki/cli/utils/progress.py`

Displays per-module progress for batch documentation generation.

**Responsibilities**:
- Track progress across multiple modules
- Distinguish between newly generated and cached modules
- Display module-level status updates
- Manage clickable progress bar in normal mode

**Key Methods**:
- `__init__(total_modules, verbose)`: Initialize with module count
- `update(module_name, cached)`: Update progress for a module
- `finish()`: Close progress bar and cleanup

**Display Modes**:
- **Verbose Mode**: Line-by-line output showing each module with status
- **Normal Mode**: Interactive click progress bar with ETA

---

## Architecture Diagram

```
CLI Utils Module Architecture:

┌─────────────────────────────────────────────────────────────────┐
│                    CLI UTILS MODULE                             │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │   CLILogger      │  │ ProgressTracker  │  │ModuleProgress │ │
│  │                  │  │                  │  │     Bar       │ │
│  │ • debug()        │  │ • start_stage()  │  │               │ │
│  │ • info()         │  │ • update_stage() │  │ • update()    │ │
│  │ • success()      │  │ • complete_stage │  │ • finish()    │ │
│  │ • warning()      │  │ • get_progress() │  │               │ │
│  │ • error()        │  │ • get_eta()      │  │               │ │
│  │ • step()         │  │                  │  │               │ │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬───────┘ │
│           │                     │                    │          │
│           └─────────────────────┼────────────────────┘          │
│                                 │                               │
└─────────────────────────────────┼───────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
            ┌───────▼────────┐        ┌────────▼──────────┐
            │  click Library  │        │ Python StdLib    │
            │ - Colored text  │        │ - datetime       │
            │ - Progress bars │        │ - time           │
            └─────────────────┘        └──────────────────┘

CONSUMERS (CLI Core):
  • CLIDocumentationGenerator → Uses all three components
  • ConfigManager → Uses CLILogger
  • GitManager → Uses CLILogger
  • HTMLGenerator → Uses CLILogger
```

---

## Component Interaction Flow

### Logging Flow

```
CLI Operation Flow:
  debug(msg) ─→ CLILogger ─→ [if verbose] ─→ Click (cyan) ─→ [HH:MM:SS] message
  
  info(msg) ─→ CLILogger ─→ Click ─→ message
  
  success(msg) ─→ CLILogger ─→ Click (green) ─→ ✓ message
  
  warning(msg) ─→ CLILogger ─→ Click (yellow) ─→ ⚠️ message
  
  error(msg) ─→ CLILogger ─→ Click (red) ─→ stderr: ✗ message
```

### Progress Tracking Flow

```
Documentation Job Lifecycle:
  
  1. Initialize ProgressTracker(total_stages=5)
     ↓
  2. Stage 1: Dependency Analysis (40% weight)
     ├─ start_stage(1)
     ├─ update_stage(progress, message) [repeatedly]
     └─ complete_stage()
     ↓
  3. Stage 2: Module Clustering (20% weight)
     ├─ start_stage(2)
     ├─ update_stage(progress, message) [repeatedly]
     └─ complete_stage()
     ↓
  4. Stage 3: Documentation Generation (30% weight)
     ├─ start_stage(3)
     ├─ update_stage(progress, message) [repeatedly]
     └─ complete_stage()
     ↓
  5. Queries:
     ├─ get_overall_progress() → calculated from stage weights
     └─ get_eta() → estimated from elapsed time
```

### Module Progress Flow

```
Batch Job Processing:
  
  Initialize: ModuleProgressBar(total_modules=50, verbose=False)
  
  Setup:
    ├─ Normal Mode: Enter click progress bar context
    └─ Verbose Mode: Use echo for each module
  
  Processing Loop:
    For each module:
      ├─ If cached: update(name, cached=True)
      ├─ If new: generate → update(name, cached=False)
      └─ Progress bar increments
  
  Finish:
    └─ Exit progress bar context / cleanup
```

---

## Data Flow Diagram

```
Input Sources:
  ├─ Configuration (verbose flag)
  └─ CLI Events (progress updates)
  
Processing:
  ├─ CLILogger
  │  ├─ State: verbose, start_time
  │  └─ Methods: debug, info, success, warning, error, step
  │
  ├─ ProgressTracker
  │  ├─ State: current_stage, stage_progress, start_time
  │  └─ Methods: start_stage, update_stage, complete_stage, get_overall_progress, get_eta
  │
  └─ ModuleProgressBar
     ├─ State: current_module, total_modules, bar
     └─ Methods: update, finish

Output:
  ├─ Colored Log Messages → stdout/stderr
  ├─ Progress Display → stage info + ETA
  └─ Module Status → per-item feedback
```

---

## State Management

### CLILogger State Lifecycle

```
INITIALIZATION
    ↓
  verbose: bool (set once, never changes)
  start_time: datetime (set once, used for elapsed calculation)
    ↓
OPERATION
    ├─→ debug/info/success/warning/error calls
    │   (stateless - each call is independent)
    ├─→ step() calls
    │   (stateless with optional progress counter)
    └─→ elapsed_time() queries
        (reads start_time for calculation)
```

### ProgressTracker State Lifecycle

```
INITIALIZATION
    ↓
  total_stages: int (5)
  current_stage: int (0)
  stage_progress: float (0.0)
  start_time: time.time()
  verbose: bool
    ↓
STAGE PROGRESSION
    ├─→ start_stage(n)
    │   updates: current_stage, stage_progress (→0.0), current_stage_start
    │
    ├─→ update_stage(progress, message)
    │   updates: stage_progress (→ [0.0-1.0])
    │
    └─→ complete_stage(message)
        updates: stage_progress (→ 1.0)
        
PROGRESS QUERIES
    ├─→ get_overall_progress()
    │   reads: current_stage, stage_progress, STAGE_WEIGHTS
    │
    └─→ get_eta()
        reads: start_time, current_time, get_overall_progress()
```

### ModuleProgressBar State Lifecycle

```
INITIALIZATION
    ↓
  total_modules: int
  current_module: int (0)
  verbose: bool
  bar: click.progressbar or None
    ↓
CONDITIONAL SETUP
    ├─→ if verbose:
    │   bar = None (use echo)
    │
    └─→ if not verbose:
        bar = click.progressbar (enter context)
        
MODULE PROCESSING
    ├─→ update(module_name, cached)
    │   updates: current_module += 1
    │   output: to bar or echo
    │
    └─→ finish()
        exit: bar context if exists
        updates: bar = None
```

---

## Integration Points

### With CLI Core Module
The `cli_utils` module is consumed by all CLI core components:

```
cli_core
├── CLIDocumentationGenerator
│   ├── Uses: CLILogger for operation logging
│   ├── Uses: ProgressTracker for multi-stage progress
│   └── Uses: ModuleProgressBar for batch operations
│
├── ConfigManager
│   └── Uses: CLILogger for config validation/loading messages
│
├── GitManager
│   └── Uses: CLILogger for git operation logs
│
└── HTMLGenerator
    └── Uses: CLILogger for generation status
```

### With CLI Models Module
Configuration impacts utility behavior:

```
cli_models.config
├── Configuration
│   └── verbose: bool → passed to loggers
│
└── GenerationOptions
    └── affects: progress tracking verbosity
```

### Dependencies
```
External:
├── click (0.8+): colored output, progress bars
└── Python stdlib: datetime, time, sys

Internal:
└── None (utility module, no internal dependencies)
```

---

## Usage Patterns

### Pattern 1: Basic Logging

```python
from codewiki.cli.utils.logging import CLILogger

logger = CLILogger(verbose=True)
logger.debug("Detailed debug info")
logger.info("Operation started")
logger.success("Completed successfully")
logger.warning("Something might be wrong")
logger.error("Critical failure")
logger.step("Processing file", step=1, total=5)
elapsed = logger.elapsed_time()
```

### Pattern 2: Multi-Stage Progress

```python
from codewiki.cli.utils.progress import ProgressTracker

tracker = ProgressTracker(total_stages=5, verbose=True)

# Stage 1: Dependency Analysis
tracker.start_stage(1)
for file in files:
    tracker.update_stage(progress, f"Analyzing {file}")
tracker.complete_stage("Analysis complete")

# Stage 2: Clustering
tracker.start_stage(2, "Module Grouping")
# ... work ...
tracker.complete_stage()

# Get progress and ETA
progress = tracker.get_overall_progress()
eta = tracker.get_eta()
```

### Pattern 3: Module-by-Module Progress

```python
from codewiki.cli.utils.progress import ModuleProgressBar

bar = ModuleProgressBar(total_modules=50, verbose=False)

for module in modules:
    if cached(module):
        bar.update(module.name, cached=True)
    else:
        # Generate documentation
        bar.update(module.name, cached=False)

bar.finish()
```

---

## Error Handling & Edge Cases

### CLILogger Edge Cases
- **Elapsed time calculation**: Uses `datetime.now()` which respects system clock
- **Overflow handling**: No risk of overflow for reasonable operation durations
- **Output redirection**: Works correctly with stderr redirection for errors

### ProgressTracker Edge Cases
- **Zero progress**: `get_eta()` returns `None` to avoid division by zero
- **Negative ETA**: Clamped to avoid displaying negative times
- **Stage boundary**: Smoothly transitions between stages
- **Invalid stage numbers**: Handled gracefully with stage name lookup
- **Over 100%**: Progress clamped to 1.0 in `update_stage()`

### ModuleProgressBar Edge Cases
- **Context cleanup**: Properly exits progress bar context even on exceptions
- **Zero modules**: Handles edge case of empty module list
- **Verbose mode**: Does not use click progress bar, avoids terminal control conflicts

---

## Performance Characteristics

### CLILogger
- **Time Complexity**: O(1) for all operations
- **Space Complexity**: O(1) - only stores two attributes
- **I/O**: Minimal - only when methods called

### ProgressTracker
- **Time Complexity**: 
  - `start_stage()`: O(1)
  - `get_overall_progress()`: O(stages) = O(5) ≈ O(1)
  - `get_eta()`: O(1)
- **Space Complexity**: O(1) - fixed-size state dictionary

### ModuleProgressBar
- **Time Complexity**: O(1) for update/finish
- **Space Complexity**: O(1) - single bar reference

---

## Thread Safety

**Note**: These utilities are **not thread-safe**. They are designed for single-threaded CLI operations:
- `CLILogger`: Direct I/O to stdout/stderr
- `ProgressTracker`: Mutable state without locking
- `ModuleProgressBar`: Click progress bar is not thread-safe

Use in multi-threaded contexts requires external synchronization.

---

## Configuration & Customization

### Customizing Logger Colors
Modify `CLILogger` methods to change ANSI color codes:
```python
def success(self, message: str):
    click.secho(f"[OK] {message}", fg="green")  # Custom format
```

### Customizing Stage Weights
Adjust `STAGE_WEIGHTS` in `ProgressTracker`:
```python
STAGE_WEIGHTS = {
    1: 0.50,  # Increase analysis weight
    2: 0.20,
    3: 0.25,  # Decrease generation weight
    4: 0.03,
    5: 0.02,
}
```

### Customizing Stage Names
Provide custom descriptions in `start_stage()`:
```python
tracker.start_stage(1, "Custom Analysis Phase")
```

---

## Related Documentation

- [CLI Core Module](cli_core.md) - Consumers of logging and progress utilities
- [CLI Models Module](cli_models.md) - Configuration affecting utility behavior
- [Documentation Generation Module](documentation_generation.md) - Primary user of progress tracking

---

## Summary

The `cli_utils` module provides lightweight, efficient utilities for CLI user experience:

| Component | Purpose | Key Feature |
|-----------|---------|-------------|
| **CLILogger** | Colored logging | Multiple severity levels + time tracking |
| **ProgressTracker** | Multi-stage progress | Weighted stages + ETA estimation |
| **ModuleProgressBar** | Batch progress | Per-module feedback with caching status |

These utilities work together to provide **real-time, user-friendly feedback** during long-running documentation generation operations, helping users understand what the system is doing and how long it will take.
