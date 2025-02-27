# Design choices for the database of sorries

Below is a sketch of what the database should look like.

## External input

A list of lean repositories/branches, provided as git remote info and branch name.

## Database content

A list of repo/branches with the following information:

1. Remote git info
2. Branch name
3. Timestamp of latest update of database for this repo/branch
4. Timestamp of latest poll of this repo/branch
5. Most recent commit hash
6. Link to the list of sorries in this repo/branch

For each repo/branch a list of sorries containing:

1. Unique ID
2. Coordinates (repo, branch, commit hash, file, line, char)
3. All info required to locally reproduce (lean version, REPL version used, ...)
4. Pretty printed proof goal, and its hash
5. Parent type of target of the sorry (or just if the target is Prop-valued or not)
6. Blame info for the line containig the sorry
7. Is this sorry *live*, i.e. is it on a leaf of the git tree?
8. List of IDs of newer instances of this sorry (with same proof goal, but possibly different global contexts)
