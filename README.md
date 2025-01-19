# Lean4 sorry scraper

This repository contains scripts to collect recent `sorry` statements in public Lean4 repositories on github.

## Scripts

All scripts require a `GITHUB_TOKEN` environment variable

`get_mathlib_contributors.py`: Gets all contributors to mathlib4 and saves results to `all_contributors.txt`
Sample output:

```
leanprover-community
Username0
Username1
```

`get_lean_repos.py` takes `all_contributors.txt` as input and checks each contributor's repositories for `lakefile.lean`. Ouputs a list of Lean4 repositories to `lean4_repos.txt`
Sample output:

```
leanprover-community/mathlib
Username0/CategoryTheory
Username1/BanchSpaces
```

`find_new_sorries.py` cycles through all repos in `lean4_repos.txt` and looks for `sorry` statements whose blame date is less than 1 week ago. Output to
`new_sorries.json`. Sample output:


```
[ 
  {
    "repository": "Blackfeather007/Filtered_Ring",
    "branch": "main",
    "commit_sha": "837f24bdd3e1ecf8caae514bc879ef94f445ced1",
    "file_path": "FilteredRing/Ascending/graded_category.lean",
    "github_url": "https://github.com/Blackfeather007/Filtered_Ring/blob/837f24bdd3e1ecf8caae514bc879ef94f445ced1/FilteredRing/Ascending/graded_category.lean#L85",
    "line_number": 85,
    "blame": {
      "author": "Username",
      "email": "first.last@example.com",
      "date": "2025-01-12T08:38:05Z",
      "message": "update graded_category"
    }
  },
```
