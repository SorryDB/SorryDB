# Lean4 SorryDB

The SorryDB project aims to build tools and infrastructure to facilitate developing and testing automated theorem provers against *real world* mathematical propositions in Lean. 

At its core, it provides a continuously updating *database* of `sorry` statements in public Lean 4 repositories. It also provides template *provers* that attempt to prove such statements, and a *verifier* that checks the correctness of proposed proofs.

In the longer run, we hope to host a continuously running sorry-filling competition, with a public *leaderboard*. 

For a detailed explanation of the project's motivation, philosophy, and goals, see [ABOUT.md](doc/ABOUT.md).


## The database

The database is hosted at [sorrydb-data](https://github.com/austinletson/sorrydb-data). It is updated nightly, by crawling Lean 4 repositories listed at on [Reservoir](https://reservoir.lean-lang.org/) for sorried (`Prop`-valued) statements.

For each such statement, it contains all information needed to locally reproduce it. This includes repository information (remote url, revision), the Lean 4 version used, and coordinates for the sorry (path, line, column).

See [DATABASE.md](doc/DATABASE.md) for more detailed information on the database format.

## The crawler

The database is updated using a crawler which uses `git` and `lake build` to clone and build the repository locally, and then uses the [Lean REPL](https://github.com/leanprover-community/repl/) to locate and analyse sorries in the repository.

## The provers

We treat each entry of the database as a theorem-proving challenge, where the precise task is to replace the `"sorry"` string with a string of tactics that fill the proof.

We provide two sample provers which take as input a list of sorry items from the database, and attempt to provide proofs. These are
1. `rfl_prover` which checks if the tactic `rfl` completes the sorried proof
2. `llm_prover` which polls uses an LLM to make a one-shot attempt at filling the proof.

These are *not* meant for consumption, but serve as template code on which one can base more advanced provers.  

See TODO for more information on buidling your own prover.

## Scripts for creating and updating the database

Scripts can be run from poetry's virtual environment by running
`poetry run <script name> <options>`.

To initialize a database file, one needs a json with a list of repositories to
monitor. The folder `repo_lists` provides some examples. Then run for example

`poetry run sorrydb/cli/init_db.py --repos-file data/repo_lists/mock_repos.json --database-file mock_db.json`

This provides an initialised database `mock_db.json` which does not yet contain
any sorries. Now one can update the database repeatedly using:

`poetry run sorrydb/cli/update_db.py --database-file mock_db.json`

## Contributing

See `CONTRIBUTING.md` for contribution guidelines.
