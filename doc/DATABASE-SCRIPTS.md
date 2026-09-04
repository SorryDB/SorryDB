# Database scripts

The SorryDB database is created using a number of python scripts that use `git`, `lake
build`, and the Lean `REPL` to collect sorries from Lean repositories. Below we provide
instructions for setting up and managing your own database, e.g. for scraping your own repository.

> [!NOTE]
> We are currently developing a more robust CLI for SorryDB.
> The main database functions (`init`, `update`, and `deduplicate`) are run through the `sorrydb` CLI tool.
> Other functionality is accessed by directly running python scripts.


## Building a database instance

### 1. Obtain a list of repositories

To initialize a database file, one needs a json with a list of repositories to
monitor. See [`sample_repo_list.json`](sample_repo_list.json) for a sample.

One can also generate that list from the GitHub API with the `index_github`
script. Running

`GITHUB_TOKEN=... poetry run python -m sorrydb.cli.index_github --output repo_list.json`

writes every public repository with a root `lake-manifest.json` and an
OSI-approved license, together with its GitHub node id, star count, last
activity and license. It logs how many candidates it found and how many met the
criteria.

That artifact is the whole universe, not a pre-filtered active list, and it has
deliberately no star or recency filter. Those are activity policy rather than
inclusion criteria: the crawl recomputes each repository's eligibility on every
run from `SORRYDB_MIN_STARS` and `SORRYDB_ACTIVITY_DAYS`, and refreshes the
metadata from the GitHub API first. So a repository that drops below the star
floor or goes quiet keeps its record, its watermark and its history, and resumes
where it left off if it becomes active again. Baking a star floor into this file
would instead drop it permanently. `--updated-since` and `--minimum-stars` were
removed from this command for that reason.

`index_github` stands in for the Lean
[Reservoir](https://reservoir.lean-lang.org/packages) index while
[reservoir#109](https://github.com/leanprover/reservoir/issues/109) is open,
because Reservoir's own discovery query silently drops everything past
GitHub's 1000-result code search cap. The older `scrape_reservoir` script still
reads the Reservoir index directly, and still applies star and recency filters,
so its output is a pre-filtered list of the old kind.

A fine-grained personal access token is enough for both, and needs no
permissions added: GitHub documents code search as working with fine-grained
tokens without any permissions, and all fine-grained tokens include read access
to public repositories.

### 2. Initialize a database file

Starting from a list of repositories, one can then initialize the database file using

`poetry run sorrydb init --repos-path repo_list.json --database-path sorry_database.json`

This provides an initialised database `sorry_database.json` which does not yet contain
any sorries. 

### 3. Updating the database file

Now one can update the database regularly using:

`poetry run sorrydb update --database-path sorry_database.json`

> [!TIP]
> By default, the database only looks for sorries on branches updated since the database was created with `sorrydb init`. 
> Users can optionally specify an earlier starting data when initializing the database via the `--starting-date` option.
> Run `sorrydb init --help` for more info.

See [DEPLOY.md](DEPLOY.md) for instructions on running the database updater in a
docker.

### 4. Deduplicating the database

After updating the database, you may want to deduplicate sorries that share the same goal.
The `deduplicate` command removes duplicate sorries,
keeping the most recently included version of each unique goal:

`poetry run sorrydb deduplicate --database-path sorry_database.json`

The `--max-sorries` option limits the number of sorries in the output:

`poetry run sorrydb deduplicate --database-path sorry_database.json --max-sorries 100 --query-results-path 100_recent_varied_sorries.json`

> [!NOTE]
> When the output is limited `--max-sorries`, 
> `deduplicate` prioritizes diversity of repositories and recent blame dates.

## Configuring `sorrydb`

In addition to CLI argument,
users can configure `sorrydb` through environment variables and a `sorrydb_config.toml`.


### Precedence

The order of precedence for configuration sources is:
- cli arguments
- environment variables
- TOML configuration file

### Environment variables

`sorrydb` will read configuration from environment variables prefixed with `SORRYDB_`.

#### Environment variable configuration example

```sh
SORRYDB_LOG_LEVEL=DEBUG sorrydb update --database-path sorry_database.json
```

### TOML configuration file

`sorrydb` will search for a `sorrydb_config.toml` in the current directory.

#### TOML configuration example

```toml
log_level = "DEBUG"
log_file = "/tmp/sorrydb.log"
```
