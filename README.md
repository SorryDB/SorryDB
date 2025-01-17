# Lean4 sorry scraper

This repository contains scripts to collect recent `sorry` statements in public Lean4 repositories on github.

## Scripts

All scripts require a `GITHUB_TOKEN` environment variable

`get_mathlib_contributors.py`: Gets all contributors to mathlib4 and saves results to `all_contributors.txt`
Sample output:

```
0art0
4hma4d
ADedecker
Aaron1011
AlexBrodbelt
AlexKontorovich
```

`get_lean_repos.py` takes `all_contributors.txt` as input and checks each contributor's repositories for `lakefile.lean`. Ouputs a list of Lean4 repositories to `lean4_repos.txt`
Sample output:

```
0art0/CategoryTheory
0art0/ComputationalComplexity
0art0/IISER-Pune-Type-Theory-Talks
0art0/lean-slides
0art0/rewrite-system-interface
ADedecker/ProperAction
```

`find_new_sorries.py` cycles through all repos in `lean4_repos.txt` and looks for `sorry` statements whose blame date is less than 1 week ago. Output to
`new_sorries.json`. Sample output:



 

