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


## Database schema


The database structure includes two collections: repos and sorries. 

Repos is used internally for processing git repos it is simply:

```json
{
      "remote_url": "https://github.com/austinletson/sorryClientTestRepo",
      "last_time_visited": "2025-03-17T11:35:11.161845+00:00",
      "remote_heads_hash": "24f2d32ed5ed",
}
```
Sorries is the primary database and it contains:

```json
{
  "remote_url": "https://github.com/austinletson/sorryClientTestRepo",
  "commit": {
    "sha": "78202012bfe87f99660ba2fe5973eb1a8110ab64",
    "branch": "branch1",
    "lean_version": "v4.16.0"
  },
  "goal": {
    "type": "\u22a2 1 + 1 = 2",
    "hash": "c118ed11456b",
    "parentType": "Prop"
  },
  "location": {
    "startLine": 4,
    "startColumn": 2,
    "endLine": 4,
    "endColumn": 7,
    "file": "SorryClientTestRepo/BasicWithElabTactic.lean",
    "url": "https://github.com/austinletson/sorryClientTestRepo/blob/master/SorryClientTestRepo/BasicWithElabTactic.lean"
  },
  "blame": {
    "commit": "4a5aa5852385523841b4802064777062c636c771",
    "author_email_hash": "1679c78ca90b",
    "date": "2025-02-27T16:30:37+01:00"
  },
  "uuid": "ac128bbe-c2b2-4942-9d84-c47ee7280d68"
}
```
