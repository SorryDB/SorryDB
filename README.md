# Lean4 SorryDB

This repository aims to build a continuously updating database of `sorry` statements in public Lean4 repositories. The idea is to use this as a basis for a continuously running benchmark which tests the performance of automated proof systems against *real world* Lean statements.

For a detailed explanation of the project's motivation, philosophy, and goals, see [ABOUT.md](ABOUT.md).

Currently we are building:

1. A list of repos/branches to continuously check for new sorries
2. A database updater which searches for sorries in the repos, tries to reproduce them locally using [REPL](https://github.com/leanprover-community/repl/), and updates the database
3. The database itself, with all information needed to reproduce the sorries independently.
4. A simple sample client which locally reproduces a sorry from the database and tries to prove it.

At a later stage, this should be extended with:

- More advanced clients, which hopefully can obtain a non-zero success rate (outside of artificial test sorries)
- Sample clients built on different lean-interaction tools (e.g. [Pantograph](https://github.com/stanford-centaur/PyPantograph))
- A leaderboard server with an API that clients can poll to obtain sorries
- A web site with a *leaderboard* ranking the performance of different automated proof systems.

See [DatabaseDesign](DatabaseDesign) for design choices for the database of sorries.

See [LeanRepoScripts.md](LeanRepoScripts.md) for information on scripts build and update the database.
