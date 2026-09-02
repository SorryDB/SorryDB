## Deploying nightly SorryDB updates

Nightly updates run as a [Cloud Run job](https://cloud.google.com/run/docs/create-jobs)
on a [Cloud Scheduler](https://cloud.google.com/scheduler) cron. The job runs
`orchestration/nightly_update.py`, which:

1. clones or refreshes the data repo over HTTPS,
2. updates `sorry_database.json`,
3. writes `deduplicated_sorries.json`,
4. commits, tags the day, and pushes to the data repo,
5. posts the deduplicated sorries to the leaderboard API in chunks.

### Crawl and publish

The job has two modes, and the default `SORRYDB_MODE=all` runs both in order.

**Crawl** updates `sorry_database.json` in place at `SORRYDB_DATABASE_PATH`,
checkpointing after every repo, and touches no git. On Cloud Run that path is a
[Cloud Storage volume mount](https://cloud.google.com/run/docs/configuring/jobs/cloud-storage-volume-mounts)
of the bucket holding the database, so the script sees an ordinary local path and
needs no GCS client library. The bucket is the source of truth between runs, and
`sorrydb init` seeds it.

**Publish** clones the data repo, copies the database plus the stats and report
into it, writes `deduplicated_sorries.json`, commits, force-moves the daily tag,
pushes once, then posts the deduplicated sorries to the leaderboard API. Run it
on its own with `SORRYDB_MODE=publish` to publish a crawl that died before
finishing.

Splitting the two is what makes the crawl checkpoints worth anything: they land
in the bucket, so an execution that dies keeps its progress.

### Where the Lean builds happen

The Lean builds do not happen in the Cloud Run job. With the default `morph`
extractor, each (repo, commit) is built on its own
[MorphCloud](https://morphcloud.ai) VM (4 vCPU, 16 GiB, 25 GB disk) and only the
extracted sorries come back as JSON. Cloud Run's filesystem is in-memory and
counts against its memory cap, so elan toolchains and mathlib olean caches would
not fit. Because the job only coordinates, 1 vCPU and 2 GiB is enough for it.

A morph crawl runs in two passes. Pass one lists every repo's new leaf commits,
which is one `ls-remote` plus one shallow clone per repo and the only sequential
network work of the run. All the extractions then fan out across up to
`SORRYDB_MORPH_WORKERS` VMs at once, and pass two replays the results through the
ordinary crawl loop. A repo whose VM failed is logged and skipped, exactly as a
failed local build is today.

### Repos with nothing to extract

Most of a crawl's cost is Lean builds, and plenty of repos have nothing to
extract at all. In one production run LSpec, llmlean, lean-training-data,
LeanCopilot, ground_zero and lean4-parser each found 0 sorries after paying for
a full build.

So before building, the VM runs the real `get_potential_sorry_files` over the
checkout and writes a marker file only if there are candidates. The
`lake exe cache get` and `lake build` steps test for that marker and no-op
without it. This is the actual predicate rather than a grep for "sorry", which
matters for mathlib: on master its candidate set is empty because the filter
intersects the diffs against `origin/master`, not because the string is absent.

Look for these lines in the job log:

```
[candidates] https://github.com/leanprover-community/mathlib4: 0 candidate sorry files, skipping cache get and lake build
[candidates] https://github.com/some/repo: 12 candidate sorry files
```

The count is logged for every repo, so the fraction of the repo list that skips
its build is measurable from one run's output.

If the check cannot decide, it writes the marker and the build proceeds. The
extraction entrypoint re-derives the candidates itself and calls
`build_lean_project` when there are any, so a wrong marker means the build
happens on the extraction instance instead of in the snapshot: slower, never
wrong.

### Repos the REPL cannot handle

Extraction builds the [Lean REPL](https://github.com/leanprover-community/repl)
at a tag matching the repo's `lean-toolchain`, and the REPL does not tag every
Lean patch release: there is a v4.33.0 and a v4.34.0-rc1 but no v4.33.1. Two
things follow.

First, `setup_repl` falls back to the highest REPL tag at or below the requested
version **within the same minor**, so v4.33.1 uses v4.33.0 and v4.23.0 uses
v4.23.0-rc2. It never falls back across a minor version: a v4.11 REPL against a
v4.13 toolchain risks subtly wrong goals, and bad data in the database is worse
than a repo we skip. A fallback logs:

```
No REPL tag v4.33.1, falling back to nearest tag v4.33.0
```

Second, the listing pass resolves each repo's toolchain over HTTP, without
cloning, and drops repos that have no usable tag before any work is queued.
Those repos cost no VM, are not counted as failures, and keep their watermarks,
so they are re-checked cheaply every night and start working on their own if
they upgrade. Skips log:

```
49 of 424 repos skipped for unsupported toolchain
Unsupported toolchain, skipping https://github.com/x/y: no REPL tag for Lean v4.12.0
Unsupported toolchain, skipping https://github.com/x/z: no lean-toolchain at the default branch head
```

and appear in `update_report.md` as a summary count plus a table of repos and
reasons. A repo whose toolchain cannot be resolved at all, for instance a
non-GitHub remote or a failed request, is attempted rather than skipped.

### Branches

Work scales with branch heads, not repositories. Every branch head gets its own
VM and its own full Lean build, and the dedup step then collapses most of the
resulting sorries because branches of one repository largely share goals. In a
20-repo trial, 54 work items came out of 20 repos and two of them produced 38:
one repo had 23 active branches and mathlib4 had 15.

So a crawl reads only each repository's default branch. Set
`SORRYDB_ALL_BRANCHES=1` to crawl every branch head instead, which is supported
and sometimes what you want, but price it first.

The change-detection hash follows the same mode: in default-branch-only mode it
covers just the default branch head, so a push to a feature branch does not
trigger a listing pass that finds nothing to do. Existing databases store hashes
computed over all branches, so the first run after this change sees a mismatch
for every repo and does one extra listing pass. That pass extracts nothing and
rewrites the hash, so it is self-correcting after one night.

Set `SORRYDB_EXTRACTOR=local` to build in the job's own container instead, which
is useful for small repo lists and for debugging. The local extractor is serial.

### Not leaking VMs

A crawler VM is 4 vCPU and 16 GiB, so one left running overnight is real money.
`Snapshot.abuild` in the MorphCloud SDK starts its own instance with no TTL, no
metadata, and a `finally` that only runs on the normal path, so a killed
coordinator used to leak build VMs that billed until someone noticed. Three
independent defences now apply, in the order a VM survives them:

1. **A TTL on every VM we create**, `SORRYDB_MORPH_TTL` seconds, default 2400.
   An orphan stops itself with no cooperation from our process, so this is the
   only defence that survives SIGKILL, an OOM kill, or the machine vanishing.
2. **A sweeper**, run before the crawl starts and again in a `finally`. It stops
   crawler instances older than the TTL. It identifies ours by the
   `sorrydb_role=crawler` metadata we tag every instance with, filtered server
   side, so it can never touch the agent experiments started by
   `morphcloud_runner.py`, which legitimately run for hours. Age alone is not
   enough to be swept, and neither is the tag alone.
3. **SIGTERM and SIGINT handlers** that stop in-flight instances before exiting.
   Cloud Run sends SIGTERM before it kills a task, so this covers the task
   timeout.

To inspect or clean up by hand:

```sh
# list every crawler VM with its age, marking the stale ones
poetry run python -m sorrydb.runners.morphcloud_crawler

# stop the stale ones
poetry run python -m sorrydb.runners.morphcloud_crawler --stop
```

Both accept `--min-age SECONDS` to override the staleness threshold. Neither can
select an untagged or agent-runner instance, so if you need to stop one of those
do it from the Morph console.

### Configuration

Everything is configured through the environment:

| Variable | Description |
|----------|-------------|
| `SORRYDB_MODE` | `all` (default), `crawl` or `publish`. |
| `SORRYDB_DATABASE_PATH` | Database to crawl and publish. Defaults to `/data/sorry_database.json`, which is where the bucket is mounted. |
| `SORRYDB_MORPH_WORKERS` | Concurrent MorphCloud VMs during a crawl. Defaults to 8. |
| `SORRYDB_MORPH_TTL` | Seconds before a crawler VM stops itself, and the age at which the sweeper treats one as orphaned. Defaults to 2400. |
| `GITHUB_TOKEN` | Token used to push to the data repo. Required for publish unless `SORRYDB_DRY_RUN` is set. |
| `MORPH_API_KEY` | MorphCloud API key. Required for the `morph` extractor. |
| `SORRYDB_DATA_REPO_URL` | HTTPS URL of the data repo. Defaults to `https://github.com/SorryDB/sorrydb-data.git`. |
| `SORRYDB_API_URL` | Leaderboard API base URL. The post is skipped if unset. |
| `SORRYDB_EXTRACTOR` | `morph` (default) or `local`. |
| `SORRYDB_ALL_BRANCHES` | Set to crawl every branch head. Default is the default branch only, because each extra branch head costs a whole VM and a full Lean build. |
| `SORRYDB_DRY_RUN` | Set to anything to skip the push and the API post. |
| `SORRYDB_COMMIT` | SorryDB commit the MorphCloud VMs check out. Required in the container, which has no git checkout; outside it defaults to the local HEAD. Must already be pushed. |

On Cloud Run, `GITHUB_TOKEN` and `MORPH_API_KEY` come from Secret Manager
secrets mounted as environment variables.

### Running it locally

```sh
SORRYDB_DATABASE_PATH=./sorry_database.json \
SORRYDB_DATA_REPO_URL=https://github.com/SorryDB/sorrydb-data-dev.git \
SORRYDB_EXTRACTOR=local \
SORRYDB_DRY_RUN=1 \
poetry run python -m orchestration.nightly_update
```

The `aristotle` strategies need the `aristotlelib` wheel, which is not
distributed with this repository, so it is not a dependency and the image builds
without it. See CONTRIBUTING.md if you need it locally.

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
