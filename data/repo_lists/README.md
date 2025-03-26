# Repository Lists

This directory contains JSON files that define lists of Lean repositories to be processed by SorryDB. These files are used as input for initializing and updating the SorryDB database. At this stage, they are mostly intended for testing and debugging. At a later stage, we may use [Reservoir](https://reservoir.lean-lang.org/packages) to automatically generate repository lists.

## File Format

Each JSON file follows this structure:

```json
{
    "documentation": "Description of this repository list",
    "repos": [
        {
            "remote": "https://github.com/username/repository"
        },
        {
            "remote": "https://github.com/another-user/another-repo"
        }
    ]
}
```

