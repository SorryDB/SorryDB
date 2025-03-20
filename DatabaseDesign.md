# Database format

The database consists of two json files. One contains the actual database
content, which is a list of sorries in public Lean 4 repositories. The other is
a list of repositories to crawl, and the necessary information to help decide
when to update the database.

## List of sorries

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

### `repo`

This fied contains all information necessary to rebuild the repository locally. For example:

```bash
# clone and check out the relevant commit
git clone <repo.remote> $repo_dir
cd $repo_dir
git checkout <repo.commit>

# obtain mathlib cache and build the repository
lake exe cache get
lake build
```

### `location`

Specifies the location of the sorried proof within the specific commit of the repository (typically encoded with the lean "sorry" keyword). For example, opening the file in VS Code using

```shell
# open the file containing the sorry in VS Code
code <location.file>
```

and navigating the cursor to `(start_line, start_column)`, one should see a goal
matching `debug_info.goal` in the Lean infoview.

Alternatively, one can use the basic REPL client provided to reproduce the sorry
in [REPL](https://github.com/leanprover-community/repl/)

### `debug_info`

This field is only for human consumption. It provides a  pretty-printed proof goal, and a direct link to the relevant line of code on github. These should only be used for debugging purposes.

### `metadata`

Contains various items for internal use by the databse. `blame_date` is the date on which the line of code containing the sorry was committed and `blame_email_hash` the hashed email address of the author of that commit, both according to `git blame`. The field `inclusion_date` specifies when this record was added to the database.

### `id`

Finally, we provide a unique ID to the sorry, built as a hash from the `repo`
and `location` fields. We consider *any* change to *any* file in the repository
as a change to *all* sorries in the repository (as a change somewhere else may
be critical in definitions used in the statement, or in lemmas available to the
prover).

## List of repositories

In order to keep track of which repositories to visit, and to decide if the
database should be updated, we also keep track of a list of repositories. This
is a list of dict items, using the following format.

```json
{
      "remote_url": "https://github.com/austinletson/sorryClientTestRepo",
      "last_time_visited": "2025-03-17T11:35:11.161845+00:00",
      "remote_heads_hash": "24f2d32ed5ed",
}
```

The first field is a `git` remote url and `last_time_visited` denotes either the
last time the database updater visited this repository, or a user-provided
cut-off date to be used in deciding which branches to check on the initial visit.

The `remote_heads_hash` provides a combined hash of all the commit shas of the
leaf commits at the time of the last visit. It allows for an efficient check
using `git remote-ls` to decide if it the repository needs to be cloned for
further inspection.
