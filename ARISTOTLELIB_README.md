# Aristotle - The Era of Vibe Proving is Here

The Aristotle SDK is a Python library and command-line tool for interacting with the Aristotle API. Aristotle is capable of proving and formally verifying graduate and research level problems in math, software, and more.

[Sign up for access at aristotle.harmonic.fun](https://aristotle.harmonic.fun)

## Quick Start

```bash
# Install
uv pip install aristotlelib

# Authenticate
export ARISTOTLE_API_KEY="your-api-key-here"

# Submit a Lean project for sorry filling
aristotle submit "Fill in all sorries" --project-dir ./my-lean-project --wait

# Formalize a math paper into Lean
aristotle formalize paper.tex --wait --destination output.tar.gz
```

## Installation

**Requires Python 3.10 or later.** Pick one of the following methods.

### Using `uv` (recommended)

We recommend [`uv`](https://docs.astral.sh/uv/) for fast, reliable Python package management.

Run Aristotle directly without a separate install step:

```bash
uvx --from aristotlelib@latest aristotle --version
```

Or install it into your environment:

```bash
uv pip install aristotlelib
```

### Using `pip`

```bash
pip install aristotlelib
```

To upgrade:

```bash
pip install --upgrade aristotlelib
```

## Authentication

To use Aristotle, you need an API key.

1. Sign up or log in at [aristotle.harmonic.fun](https://aristotle.harmonic.fun).
2. Go to [Dashboard → API Keys](https://aristotle.harmonic.fun/dashboard/keys) and create a new key.

### Save it as an environment variable (recommended)

Set your key once so it's available automatically in every terminal session.

#### macOS / Linux

Open your terminal and run these two commands, replacing `your-api-key-here` with your actual key:

```bash
echo 'export ARISTOTLE_API_KEY="your-api-key-here"' >> ~/.zshrc
source ~/.zshrc
```

The first command saves the key to your shell startup file (`~/.zshrc`) so every new terminal session will have it. The second command loads it into your current session right away.

> If you use **bash** instead of zsh, replace `~/.zshrc` with `~/.bashrc` in both commands.

#### Windows

Open **PowerShell** and run:

```powershell
setx ARISTOTLE_API_KEY "your-api-key-here"
```

Then **close and reopen** PowerShell for the change to take effect.

### Pass it directly to a command

Alternatively, you can add `--api-key` to any command without saving it:

```bash
aristotle submit "My prompt" --api-key your-api-key-here
```

## Getting Started

### Lean Project Structure

When submitting a Lean project, Aristotle expects a standard Lean project directory. At a minimum, your project should contain:

- **`lakefile.toml`** (or `lakefile.lean`): the `Lake` build configuration, declaring your project name, dependencies (e.g., Mathlib), and any Lean options.
- **`lean-toolchain`**: specifies the Lean version (e.g., `leanprover/lean4:v4.24.0`).
- **`.lean` source files**: your Lean code, typically under a directory matching the project name.

A typical project layout:

```
my-lean-project/
├── lakefile.toml
├── lean-toolchain
├── lake-manifest.json
└── MyLeanProject/
    ├── Basic.lean
    └── Main.lean
```

Aristotle automatically packages the directory, skipping build artifacts (`.olean`, `.lake/packages/`), so you can directly point `--project-dir` at your working project.

### CLI Usage

Submit a project with a prompt:

```bash
aristotle submit "Fill in all sorries in this project" --project-dir ./my-lean-project --wait
```

Formalize a document:

```bash
aristotle formalize paper.tex --wait --destination output.tar.gz
```

List your recent projects:

```bash
aristotle list --limit 10
```

Get a project's result:

```bash
aristotle result <project-id> --destination result.tar.gz
```

### Python API Usage

```python
import asyncio
import aristotlelib

async def main():
    project = await aristotlelib.Project.create(
        prompt="Prove that 1 + 1 = 2"
    )
    print(f"Created project: {project.project_id}")

    result_path = await project.wait_for_completion(destination="result.tar.gz")
    print(f"Solution saved to: {result_path}")

asyncio.run(main())
```

## CLI Commands

### `aristotle submit`

Submit a new project to Aristotle.

```bash
aristotle submit <prompt> [options]
```

**Arguments:**
- `prompt`: Instructions telling Aristotle what to do

**Options:**
- `--project-dir PATH`: Directory containing files Aristotle needs (e.g., your Lean project or papers to formalize)
- `--wait`: Wait for completion before returning
- `--destination PATH`: Where to save the solution (requires `--wait`)

**Examples:**

```bash
# Submit a simple prompt
aristotle submit "Prove that the square root of 2 is irrational"

# Submit with a Lean project directory
aristotle submit "Fill in the sorries" --project-dir ./my-lean-project

# Submit and wait for results
aristotle submit "Formalize this theorem" --project-dir ./proofs --wait --destination output.tar.gz
```

### `aristotle formalize`

Formalize a document containing mathematics in natural language (`.tex`, `.txt`, `.md`).

```bash
aristotle formalize <input-file> [options]
```

**Arguments:**
- `input_file`: Document to formalize

**Options:**
- `--wait`: Wait for completion before returning
- `--destination PATH`: Where to save the solution (requires `--wait`)

**Example:**

```bash
aristotle formalize paper.tex --wait --destination formalized.tar.gz
```

### `aristotle list`

List your projects in descending order by creation date.

```bash
aristotle list [options]
```

**Options:**
- `--status STATUS [STATUS ...]`: Filter by status (can specify multiple)
- `--limit N`: Maximum projects to return (1-100, default: 10)
- `--pagination-key KEY`: Continue from a previous list request

**Example:**

```bash
# List recent projects
aristotle list --limit 20

# Only show complete and in progress projects
aristotle list --status COMPLETE IN_PROGRESS

# Get next page
aristotle list --pagination-key <key-from-previous-response>
```

### `aristotle result`

Get the result of a project.

```bash
aristotle result <project-id> [options]
```

**Arguments:**
- `project_id`: ID of the project

**Options:**
- `--wait`: Wait for completion before downloading
- `--destination PATH`: Where to save the solution

**Example:**

```bash
# Download result if ready
aristotle result abc-123-def

# Wait for completion and download
aristotle result abc-123-def --wait --destination result.tar.gz
```

### `aristotle cancel`

Cancel a queued or in-progress project.

```bash
aristotle cancel <project-id>
```

**Arguments:**
- `project_id`: ID of the project to cancel

**Example:**

```bash
aristotle cancel abc-123-def
```

## Python API Reference

### Project Class

The main class for interacting with Aristotle projects.

#### Class Methods

##### `Project.create(prompt, tar_file_path=None, public_file_path=None)`

Create a new project with a prompt and optional tar file.

**Parameters:**
- `prompt` (str): Instructions telling Aristotle what to do
- `tar_file_path` (Path | str, optional): Path to a tar.gz file containing supplementary files
- `public_file_path` (str, optional): Saved as the name of the input file for future reference (defaults to tar_file_path)

**Returns:** `Project` instance

**Example:**

```python
project = await Project.create(
    prompt="Prove the fundamental theorem of calculus"
)
```

##### `Project.create_from_directory(prompt, project_dir)`

Create a project from a directory by automatically creating a tar.gz archive.

**Parameters:**
- `prompt` (str): Instructions telling Aristotle what to do
- `project_dir` (Path | str): Path to directory containing files Aristotle needs (e.g., a Lean project)

**Returns:** `Project` instance

**Example:**

```python
project = await Project.create_from_directory(
    prompt="Fill in all the sorries",
    project_dir="./my-lean-project"
)
```

##### `Project.from_id(project_id)`

Load an existing project by ID.

**Parameters:**
- `project_id` (str): The project ID

**Returns:** `Project` instance

**Example:**

```python
project = await Project.from_id("abc-123-def")
```

##### `Project.list_projects(pagination_key=None, limit=30, status=None)`

List projects, ordered by creation date (most recent first).

**Parameters:**
- `pagination_key` (str, optional): Key to start from when paginating
- `limit` (int): Maximum number of projects to return (1-100, default: 30)
- `status` (ProjectStatus | list[ProjectStatus], optional): Filter by status

**Returns:** Tuple of `(list[Project], str | None)` - projects list and next pagination key

**Example:**

```python
projects, next_key = await Project.list_projects(limit=10)

# Filter by status
active_projects, _ = await Project.list_projects(
    status=[ProjectStatus.QUEUED, ProjectStatus.IN_PROGRESS]
)
```

#### Instance Methods

##### `project.wait_for_completion(destination=None, polling_interval_seconds=30)`

Wait for project completion and download the result.

**Parameters:**
- `destination` (Path | str, optional): Where to save the solution
- `polling_interval_seconds` (int): Seconds between status checks (default: 30)

**Returns:** `str | None` - Path to the downloaded file, or None if canceled/failed

**Example:**

```python
result_path = await project.wait_for_completion(destination="output.tar.gz")
```

##### `project.get_solution(destination=None)`

Download the solution file.

**Parameters:**
- `destination` (Path | str, optional): Where to save the solution

**Returns:** `Path` to the downloaded file

**Example:**

```python
solution = await project.get_solution(destination="solution.tar.gz")
```

##### `project.get_input(destination=None)`

Download the input file.

**Parameters:**
- `destination` (Path | str, optional): Where to save the input

**Returns:** `Path` to the downloaded file

##### `project.refresh()`

Refresh the project's status from the API.

**Example:**

```python
await project.refresh()
print(project.status)
```

##### `project.cancel()`

Cancel a queued or in-progress project.

**Example:**

```python
await project.cancel()
```

### Project Status

```python
class ProjectStatus(Enum):
    UNKNOWN = "UNKNOWN"
    NOT_STARTED = "NOT_STARTED"  # Deprecated
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    COMPLETE_WITH_ERRORS = "COMPLETE_WITH_ERRORS"
    OUT_OF_BUDGET = "OUT_OF_BUDGET"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
```

**Status Descriptions:**

- `UNKNOWN`: Unrecognized status from server - seeing this means you need to upgrade this package
- `NOT_STARTED`: (Deprecated) Legacy projects only
- `QUEUED`: Project is waiting to be processed
- `IN_PROGRESS`: Aristotle is actively working on the project
- `COMPLETE`: Project completed successfully
- `COMPLETE_WITH_ERRORS`: Project finished but had trouble parsing the input
- `OUT_OF_BUDGET`: Project ran out of budget/time
- `FAILED`: Internal error occurred
- `CANCELED`: Project was canceled

### Project Properties

Each `Project` instance has these properties:

- `project_id` (str): Unique project identifier
- `status` (ProjectStatus): Current status
- `created_at` (datetime): When the project was created
- `last_updated_at` (datetime): Last status update time
- `percent_complete` (int | None): Completion percentage (when `IN_PROGRESS`)
- `input_prompt` (str | None): The prompt text
- `file_name` (str | None): Name of the input file
- `description` (str | None): Project description

### Error Handling

The SDK provides the following exception:

- `AristotleAPIError`: Raised for API-related errors

**Example:**

```python
from aristotlelib import AristotleAPIError

try:
    project = await Project.create(prompt="My prompt")
except AristotleAPIError as e:
    print(f"API error: {e}")
```

### Utility Functions

#### `set_api_key(api_key)`

Set the API key programmatically.
The ARISTOTLE_API_KEY environment variable will also work.
This will take precedence over the environment variable if both are set.

**Parameters:**
- `api_key` (str): Your Aristotle API key

**Example:**

```python
import aristotlelib

aristotlelib.set_api_key("your-api-key-here")
```

## Examples

### Submit a simple prompt

```python
import asyncio
import aristotlelib

async def main():
    # Create a project with a prompt
    project = await aristotlelib.Project.create(
        prompt="Prove that the square root of 2 is irrational"
    )
    print(f"Created project: {project.project_id}")

    # Wait for completion
    result_path = await project.wait_for_completion(destination="output.tar.gz")
    if result_path:
        print(f"Solution saved to: {result_path}")

asyncio.run(main())
```

### Submit with a Lean project directory

```python
import asyncio
import aristotlelib
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    # Create project from a directory
    project = await aristotlelib.Project.create_from_directory(
        prompt="Fill in all the sorries in the Main.lean file",
        project_dir="./my-lean-project"
    )
    print(f"Created project: {project.project_id}")

    # Wait for completion
    await project.wait_for_completion(destination="results.tar.gz")

asyncio.run(main())
```

### Monitor an existing project

```python
import asyncio
import aristotlelib

async def main():
    # Load an existing project
    project = await aristotlelib.Project.from_id("your-project-id")

    # Check status
    await project.refresh()
    print(f"Status: {project.status.name}")

    if project.percent_complete:
        print(f"Progress: {project.percent_complete}%")

    # Wait for completion if still running
    if project.status in (aristotlelib.ProjectStatus.QUEUED, aristotlelib.ProjectStatus.IN_PROGRESS):
        await project.wait_for_completion(destination="output.tar.gz")

asyncio.run(main())
```

### List and filter projects

```python
import asyncio
import aristotlelib
from aristotlelib import ProjectStatus

async def main():
    # List recent projects
    projects, pagination_key = await aristotlelib.Project.list_projects(limit=10)

    for project in projects:
        print(f"{project.project_id}: {project.status.name}")

    # Filter by status
    active_projects, _ = await aristotlelib.Project.list_projects(
        status=[ProjectStatus.QUEUED, ProjectStatus.IN_PROGRESS],
        limit=20
    )
    print(f"Found {len(active_projects)} active projects")

    # Paginate through all projects
    all_projects = []
    pagination_key = None
    while True:
        batch, pagination_key = await aristotlelib.Project.list_projects(
            pagination_key=pagination_key,
            limit=100
        )
        all_projects.extend(batch)
        if not pagination_key:
            break

    print(f"Total projects: {len(all_projects)}")

asyncio.run(main())
```

### Cancel a project

```python
import asyncio
import aristotlelib

async def main():
    project = await aristotlelib.Project.from_id("your-project-id")

    # Cancel if it's running
    if project.status in (
        aristotlelib.ProjectStatus.QUEUED,
        aristotlelib.ProjectStatus.IN_PROGRESS
    ):
        await project.cancel()
        print("Project canceled")

asyncio.run(main())
```

### Error handling

```python
import asyncio
import logging
from aristotlelib import Project, ProjectStatus, AristotleAPIError

logging.basicConfig(level=logging.INFO)

async def main():
    try:
        project = await Project.create(
            prompt="Prove Fermat's Last Theorem"
        )

        result_path = await project.wait_for_completion()

        if project.status == ProjectStatus.COMPLETE:
            print(f"Success! Result: {result_path}")
        elif project.status == ProjectStatus.COMPLETE_WITH_ERRORS:
            print(f"Completed with errors. Check: {result_path}")
        elif project.status == ProjectStatus.OUT_OF_BUDGET:
            print(f"Ran out of budget. Partial result: {result_path}")
        elif project.status == ProjectStatus.FAILED:
            print("Project failed due to internal error")
        elif project.status == ProjectStatus.CANCELED:
            print("Project was canceled")

    except AristotleAPIError as e:
        print(f"API error: {e}")

asyncio.run(main())
```

## Support

For questions, issues, or feature requests:
- Visit [aristotle.harmonic.fun](https://aristotle.harmonic.fun)
- Contact aristotle@harmonic.fun

## License

See [LICENSE](LICENSE) file for details.
