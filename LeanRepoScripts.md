# Scripts for finding Lean repositories with recent sorries

## Scripts

Scripts can be run from poetry's virtual environment by running
`poetry run <script name> <options>`. 

For example, `poetry run offline_sorries --repo-url https://github.com/austinletson/sorryClientTestRepoMath`

Scripts can also be run by activating poetry's virtual environment `eval $(poetry env activate)` and running the script directly.


### List of scripts

1. `get_mathlib_contributors.py`: Gets all contributors to mathlib4 and saves
   results to `all_contributors.txt`
2. `get_lean_repos.py` takes `all_contributors.txt` as input and checks each contributor's repositories for `lakefile.lean`. Ouputs a list of Lean4 repositories to `lean4_repos.txt`
3. `offline_sorries.py` clones a repo/branch and runs it through REPL to find
   sorries and determine their proof goal. Outputs list of sorries to a json
   file.

The `get_mathlib_contributors.py` and `get_lean_repos.py` scripts require a `GITHUB_TOKEN` environment variable.