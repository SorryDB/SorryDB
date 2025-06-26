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

One can also generate a list of repositories from the Lean
[Reservoir](https://reservoir.lean-lang.org/packages) using the
`scrape_reservoir` script. Running

`poetry run sorrydb/cli/scrape_reservoir.py --updated-since 2025-01-01
--minimum-stars 10 --output repo_list.json`

will generate a json file containing all Lean repositories listed on reservoir
that have been updated since Jan 1, and have at least 10 GitHub stars.

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
