# Design choices for the database of sorries

Below is a sketch of what the database should look like.

## External input

A list of lean repositories/branches, provided as git remote info and branch name.

## Database content

### Sorries

The main content of the database is a json containing the list of sorries. Each sorry has the following format:

```json
{
  "repo": {
    "remote": "https://github.com/austinletson/sorryClientTestRepo",
    "branch": "branch1",
    "commit": "78202012bfe87f99660ba2fe5973eb1a8110ab64",
    "lean_version": "v4.16.0"
  },
  "location": {
    "start_line": 4,
    "start_column": 2,
    "end_line": 4,
    "end_column": 7,
    "file": "SorryClientTestRepo/BasicWithElabTactic.lean"
  },
  "debug_info": {
      "goal": "\u22a2 1 + 1 = 2",
      "url": "https://github.com/austinletson/sorryClientTestRepo/blob/78202012bfe87f99660ba2fe5973eb1a8110ab64/SorryClientTestRepo/BasicWithElabTactic.lean#L4"
  }
  "metadata": {
    "blame_email_hash": "1679c78ca90b",
    "blame_date": "2025-02-27T16:30:37+01:00"
    "inclusion_date": "2025-03-14T12:00:00+00:00"
  },
  "id": "a7f9b3c5d2e1"
}
```

Below we specify in more detail the contents of this item.

1. `repo` contains all information necessary to rebuild the repository locally, and to feed it to a lean interaction tool. For example:

```shell
# clone and check out the relevant commit
git clone <repo.remote> $repo_dir
cd $repo_dir
git checkout <repo.commit>

# obtain mathlib cache and build the repository
lake exe cache get
lake build
```

2. `location` field specifies the location of the sorried proof within the specific commit of the repository (typically encoded with the lean "sorry" keyword). Using the `lean_version` tag and a lean interaction tool compatible with this version, one can recreate the sorry locally. For example, using [REPL](https://github.com/leanprover-community/repl/):

```shell
# Clone and build the correct REPL version
git clone https://github.com/leanprover-community/repl $repl_dir/<repo.lean_version>
cd $repl_dir/<repo.lean_version>
git checkout <repo.lean_version>
lake build

# Run REPL on the specified lean file
cd $REPO_DIR
echo {"path": "<location.file>", "allTactics": true} | lake env "$REPL_DIR/<repo.lean_version>/.lake/build/bin/repl" > output.json
```

The output should contain a field `sorries`, containing 
```json
{
    // ...
    "sorries": [
        // ... 
        {
            "proofState": 123,  
            "pos": {
                "line": 4,
                "column": 2
            },
            "endPos": {
                "line": 4,
                "column": 7
            },
            "goal": "⊢ 1 + 1 = 2"  
        },
        // ... 
    ]
    // ...
}
```
matching the provided location data.

3. `debug_info` provides a pretty-printed proof goal, and a direct link to the relevant line of code on github. These should only be used for debugging purposes. 

4. `metadata` is for internal purposes only, and will not be served to the client. `blame_date` is the date on which the line of code containing the sorry was committed and `blame_email_hash` the hashed email address of the author of that commit, both according to `git blame`. The field `inclusion_date` specifies when this record was added to the database.

5. `id` provides a unique ID to the sorry, built as a hash from the `repo` and `location` fields.

### Repositories

In order to keep track of which repositories to visit, and to decide if the database should be updated, we also keep track of a list of repositories. 