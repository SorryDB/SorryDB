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

`find_new_sorries.py --cutoff 7` cycles through all repos in `lean4_repos.txt`
and looks for `sorry` statements whose blame date is less than 7 days old. Output to
`new_sorries.json`. 
```


## Known issues

1. No guarantee that we find all lean repositories, we only search for the
   repositories of users that have contributed to mathlib4 (and the repositories
   of leanprover-community)
2. Does not filter out sorries that are part of a comment block
3. Does not do any lean validation, so some sorries might not compile.
4. Duplication: a sorry might occur in two different branches. Depending on the
   context in each branch, they may or may not be equivalent.
5. Age of a sorry is measured by the blame date, which may not reflect the
   actual age for example in case of a hard refactor.
