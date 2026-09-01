## Deploying nightly SorryDB updates

Nightly updates run as a [Cloud Run job](https://cloud.google.com/run/docs/create-jobs)
on a [Cloud Scheduler](https://cloud.google.com/scheduler) cron. The job runs
`orchestration/nightly_update.py`, which:

1. clones or refreshes the data repo over HTTPS,
2. updates `sorry_database.json`,
3. writes `deduplicated_sorries.json`,
4. commits, tags the day, and pushes to the data repo,
5. posts the deduplicated sorries to the leaderboard API in chunks.

### Where the Lean builds happen

The Lean builds do not happen in the Cloud Run job. With the default `morph`
extractor, each (repo, commit) is built on its own
[MorphCloud](https://morphcloud.ai) VM (4 vCPU, 16 GiB, 25 GB disk) and only the
extracted sorries come back as JSON. Cloud Run's filesystem is in-memory and
counts against its memory cap, so elan toolchains and mathlib olean caches would
not fit. Because the job only coordinates, 1 vCPU and 2 GiB is enough for it.

Set `SORRYDB_EXTRACTOR=local` to build in the job's own container instead, which
is useful for small repo lists and for debugging.

### Configuration

Everything is configured through the environment:

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | Token used to push to the data repo. Required unless `SORRYDB_DRY_RUN` is set. |
| `MORPH_API_KEY` | MorphCloud API key. Required for the `morph` extractor. |
| `SORRYDB_DATA_REPO_URL` | HTTPS URL of the data repo. Defaults to `https://github.com/SorryDB/sorrydb-data.git`. |
| `SORRYDB_API_URL` | Leaderboard API base URL. The post is skipped if unset. |
| `SORRYDB_EXTRACTOR` | `morph` (default) or `local`. |
| `SORRYDB_DRY_RUN` | Set to anything to skip the push and the API post. |
| `SORRYDB_COMMIT` | SorryDB commit the MorphCloud VMs check out. Required in the container, which has no git checkout; outside it defaults to the local HEAD. Must already be pushed. |

On Cloud Run, `GITHUB_TOKEN` and `MORPH_API_KEY` come from Secret Manager
secrets mounted as environment variables.

### Running it locally

```sh
SORRYDB_DATA_REPO_URL=https://github.com/SorryDB/sorrydb-data-dev.git \
SORRYDB_EXTRACTOR=local \
SORRYDB_DRY_RUN=1 \
poetry run python -m orchestration.nightly_update
```

### Deployment environments

Deployment environments allow us to point instances of the nightly update at different repo lists and databases stored on different GitHub repos.
| Environment | Description                                                                 | Type of Data                                  | GitHub Repo URL                                     |
|-------------|-----------------------------------------------------------------------------|-----------------------------------------------|-----------------------------------------------------|
| DEV         | Used for development of new features.                                       | Primarily mock repos and mock "sorries".      | https://github.com/SorryDB/sorrydb-data-dev         |
| TEST        | Used for testing SorryDB on different repo sets (e.g., all of Reservoir).   | Varied repository sets for comprehensive testing. | https://github.com/SorryDB/sorrydb-data-test        |
| PROD        | Used for the main SorryDB database.                                         | Primary production data for SorryDB.          | https://github.com/SorryDB/sorrydb-data             |


## Deploying SorryDB with Docker

### Building the Docker image

Build a Docker image that includes both Lean and SorryDB:

```shell
git clone https://github.com/SorryDB/SorryDB
cd SorryDB
docker build -t sorrydb .
```

This command builds an image from the `./Dockerfile` tags it as `sorrydb`.

### Updating the Sorry Database

To update a sorry database with the Docker image:

```shell
docker run \
  --mount type=bind,source=/path/to/your/database/directory,target=/data \
  sorrydb:latest \
  poetry run update_db --database-file /data/sorry_database.json
```

Where:
- `--mount type=bind,source=/path/to/your/database/directory,target=/data` mounts your local database directory to `/data` inside the container
- `poetry run sorrydb update --database-path /data/sorry_database.json` is the command to run inside the container

Replace `/path/to/your/database/directory` with the actual path to your database directory.

## Security Considerations

- **Code Execution**: The `update_db` command downloads and executes Lean code from the internet. Running it inside a Docker container provides isolation from your host system.

- **User Permissions**: The Docker image created by the provided Dockerfile is configured to run as a non-root user by default.

- **Volume Mounts**: Only mount the specific directories needed for operation to limit access to your filesystem.
