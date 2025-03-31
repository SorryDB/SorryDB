# Repository Lists

This directory contains JSON files that define lists of Lean repositories to be
processed by SorryDB. These files are used as input for initializing and
updating the SorryDB database. At this stage, they are mostly intended for
testing and debugging.

## Generating lists from Reservoir

The script `data/repo_lists/scripts/scrape_reservoir.py` generates JSON
repository lists based on [Reservoir](https://reservoir.lean-lang.org/packages).
Usage:

```shell
python3 scrape_reservoir.py --updated-since 2025-01-01 --minimum-stars 10 --output active_repos.json
```

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
