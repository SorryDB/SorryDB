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

Each per-repo checkpoint is written to a sibling temp file and renamed over the
target, so a task timeout cannot leave a half written database behind. On a
POSIX filesystem that rename is atomic. On a gcsfuse mount it is not: gcsfuse
implements rename as a copy followed by a delete. It is still the safer of the
two, because gcsfuse also buffers a written file locally and only uploads it on
close, so neither path streams a partial object into the bucket.

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

The branch is resolved from the remote rather than configured, because the data
repos disagree: `sorrydb-data` defaults to `master` while `sorrydb-data-test`
defaults to `main` and still carries a stale `master` that nobody reads. Publish
fails rather than guessing if the remote does not report a default branch. It
logs the branch it chose:

```
Publishing to the main branch of https://github.com/SorryDB/sorrydb-data-test.git
```

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

### Repos that are in the database but not crawled

The database holds the whole universe that met the inclusion criteria, not a
pre-filtered active list. Whether a repo is crawled tonight is a verdict stored
on its record and recomputed every run, so a repo that drops below the star
threshold or goes quiet keeps its record, its watermark and its history, and
resumes rather than starting over when it comes back.

Two independent things stop a repo being crawled, and they are deliberately not
merged, because they refresh on different cadences:

- **Ineligible**, from `SORRYDB_MIN_STARS`, `SORRYDB_ACTIVITY_DAYS`, or an
  `opted_out` flag set by hand. Recomputed from GitHub metadata every run.
- **Unsupported toolchain**, which is only observable by looking at the repo.

Both appear in `update_report.md`, ineligibility grouped by reason:

```
- **Repositories ineligible to crawl:** 423

| Reason | Repositories |
| fewer than 10 stars | 300 |
| no activity in 180 days | 120 |
| opted out by the repository owner | 3 |
```

Before deciding, the job refreshes every repo's stars and last activity from the
GitHub API, about one GraphQL call per 100 repos. It queries by the node id
stored on each record, so there is no URL to id lookup and a renamed repo still
refreshes. This reuses `GITHUB_TOKEN`, and needs no extra scope on it: GitHub
documents code search as working with fine-grained tokens without any
permissions, and all fine-grained tokens include read access to public
repositories.

A metadata refresh failure falls back to the stored metadata rather than
marking everything ineligible, and a refresh never clears `opted_out`. The run
continues on the stored metadata, and says so in the report:

```
- **Repo metadata refreshed:** 820 of 820
- **Repo metadata refreshed:** **REFRESH FAILED**, every verdict below came from stored metadata which may be out of date
- **Repo metadata refreshed:** 817 of 820, 3 did not resolve
```

A successful refresh is one unremarkable row. A failed one is called out,
because "300 repos are dormant" and "300 repos looked dormant in four month old
metadata" are otherwise the same sentence. The third case is separated out
because it is actionable: those repositories returned nothing from the API, so
they have gone private or been deleted, and they are named in the report. Such a
repository stays in the database indefinitely and fails its remote check every
night, which costs one `ls-remote` and no VM, so retire it by hand when it
shows up.

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
| `SORRYDB_LOG_DIR` | Root for the per repo build logs. The workflow sets it to `/data/logs` so they land in the bucket: Cloud Run discards the container filesystem, so otherwise only what reached stdout survives. Each run gets its own subdirectory, named after the Cloud Run execution. |
| `SORRYDB_MORPH_TTL` | Seconds before a crawler VM stops itself, and the age at which the sweeper treats one as orphaned. Defaults to 2400. |
| `GITHUB_TOKEN` | Token used to push to the data repo. Required for publish unless `SORRYDB_DRY_RUN` is set. |
| `MORPH_API_KEY` | MorphCloud API key. Required for the `morph` extractor. |
| `SORRYDB_DATA_REPO_URL` | HTTPS URL of the data repo. Defaults to `https://github.com/SorryDB/sorrydb-data.git`. |
| `SORRYDB_API_URL` | Leaderboard API base URL. The post is skipped if unset, and the workflow currently sets it empty. |
| `SORRYDB_EXTRACTOR` | `morph` (default) or `local`. |
| `SORRYDB_MIN_STARS` | Minimum GitHub stars for a repo to be crawled. Defaults to 10. Repos below it stay in the database and are re-checked each run. |
| `SORRYDB_ACTIVITY_DAYS` | A repo with no activity in this many days is not crawled. Defaults to 180. |
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


## Continuous deployment

`.github/workflows/deploy.yml` deploys on every push to `master`. `ci.yml` only
runs on `pull_request`, so the workflow runs the test suite itself, with the same
`lean-action` toolchain setup and `pytest -m "not local_only"`, and both deploys
depend on it. Nothing ships off a red suite. A concurrency group queues
overlapping merges instead of racing two deploys at the same resource.

What deploys is decided per resource from the changed paths, so a docs-only merge
deploys nothing:

| Resource | Deploys when these change |
|----------|---------------------------|
| Cloud Run job `sorrydb-nightly` | `sorrydb/**`, `orchestration/**`, `Dockerfile`, `pyproject.toml`, `poetry.lock`, `.github/workflows/deploy.yml` |
| Cloud Run service `myapi` | `sorrydb/leaderboard/**`, `leaderboard_deployment/**`, `pyproject.toml`, `poetry.lock`, `.github/workflows/deploy.yml` |

`deploy.yml` is in both lists because it owns the job's environment. Without it,
editing the environment would deploy nothing and appear to have no effect until
an unrelated commit landed.

A leaderboard-only change deploys both, which is correct: the crawler image
copies the whole `sorrydb` package.

Images are tagged with the merge commit sha rather than `latest`, so what is
running is identifiable and a rollback is a redeploy of an earlier tag:

```sh
gcloud run jobs update sorrydb-nightly --region=us-central1 \
  --image=gcr.io/sorrydb-test/sorrydb_crawler:<older-sha>
gcloud run deploy myapi --region=us-central1 \
  --image=gcr.io/sorrydb-test/leaderboard_api:<older-sha>
```

### The job's environment is owned by the workflow

`--set-env-vars` removes every existing environment variable before applying the
new set, so the workflow holds the complete environment for `sorrydb-nightly` and
is the source of truth for it.

**A manual `gcloud run jobs update --set-env-vars` is reverted by the next merge
that touches the crawler.** To change the job's environment, change
`.github/workflows/deploy.yml`. Editing it in the console will appear to work and
then quietly disappear.

Every variable the job needs must be listed in the workflow, including ones
that are currently empty. `SORRYDB_API_URL` is set but blank: that is how the
leaderboard post stays disabled for now, and **to enable posting, set it in
`deploy.yml`**, not in the console. Omitting it entirely would wipe a hand set
value on the next merge and silently stop posting.

`SORRYDB_COMMIT` is set to the merge sha. The Morph VMs check that commit out
from GitHub, so using the merge sha makes it a pushed commit by construction.

The service is treated the opposite way. `gcloud run deploy` is a partial update:
anything not passed keeps its current value, so the workflow passes the image and
nothing else, and the Cloud SQL attachment and the service's four Secret Manager
variables survive untouched. Adding `--set-env-vars` there would wipe them.

### One-time setup

None of this is created by the workflow. The workflow uses
`gcloud run jobs update` and `gcloud run deploy`, both of which need the resource
to already exist, which is deliberate: a missing resource fails loudly instead of
being recreated without its bucket mount.

Workload Identity Federation, so the workflow authenticates without a service
account key:

```sh
PROJECT_ID=sorrydb-test
PROJECT_NUMBER=754129481175
REPO=SorryDB/SorryDB

gcloud iam service-accounts create sorrydb-deployer \
  --project="$PROJECT_ID" --display-name="GitHub Actions deployer"

gcloud services enable iamcredentials.googleapis.com --project="$PROJECT_ID"

gcloud iam workload-identity-pools create github \
  --project="$PROJECT_ID" --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --project="$PROJECT_ID" --location=global --workload-identity-pool=github \
  --display-name="GitHub" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='$REPO'"

# Only this repository may impersonate the deployer
gcloud iam service-accounts add-iam-policy-binding \
  "sorrydb-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
  --project="$PROJECT_ID" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"

# Push images, update the job and the service, and act as the runtime account.
# cloudbuild.builds.editor is only needed if a build is ever moved to
# `gcloud builds submit`; the workflow builds in the runner and pushes directly.
for role in roles/run.developer roles/storage.admin roles/iam.serviceAccountUser \
            roles/cloudbuild.builds.editor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --role="$role" \
    --member="serviceAccount:sorrydb-deployer@$PROJECT_ID.iam.gserviceaccount.com"
done
```

The `attribute-condition` is what stops any other repository presenting a GitHub
token and impersonating the deployer. The resulting values are already in
`deploy.yml`:

```
projects/754129481175/locations/global/workloadIdentityPools/github/providers/github-provider
sorrydb-deployer@sorrydb-test.iam.gserviceaccount.com
```

The Cloud Run job, including the bucket mount and the secrets the workflow does
not manage:

```sh
gcloud run jobs create sorrydb-nightly \
  --project=sorrydb-test --region=us-central1 \
  --image=gcr.io/sorrydb-test/sorrydb_crawler:latest \
  --service-account=sorrydb-nightly@sorrydb-test.iam.gserviceaccount.com \
  --cpu=1 --memory=2Gi --max-retries=0 --task-timeout=24h \
  --add-volume=name=data,type=cloud-storage,bucket=<database-bucket> \
  --add-volume-mount=volume=data,mount-path=/data \
  --set-secrets=MORPH_API_KEY=morph-api-key:latest,GITHUB_TOKEN=github-token:latest
```

The Cloud Run service `myapi` is created once with its Cloud SQL attachment,
its `DB_HOST` environment variable and its three Secret Manager secrets. Those
commands are in [sorrydb/leaderboard/README.md](../sorrydb/leaderboard/README.md).
The workflow only ever passes an image, so all of that survives.

The Cloud Scheduler cron is deliberately left as manual one-time setup and is not
touched by the workflow.

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
