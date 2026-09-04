# Plan: make Postgres a correct derived read model

Written 2026-09-04, after the first successful end-to-end nightly run
(`sorrydb-nightly-ws54z`, 2026-09-03). Everything in the "measured" sections
below is observed from that run, not estimated. You should not need to re-derive
any of it.

## Status

Tasks 1 to 5 landed on `plan/postgres-read-model`, rebased onto
`analytics-endpoints`. Task 6 is the only one left and is still deliberately
off. Three things were decided differently from what is written below, each for
a reason recorded in the code:

- The write endpoint is `PUT /sorries/`, and the old `POST /sorries/` is gone
  rather than kept alongside it. One write endpoint with one meaning.
- Read-time dedup uses a `row_number()` window function, not `DISTINCT ON`,
  because the leaderboard tests run on SQLite. That also needs no index on
  `goal`, so the 8KB btree trap in Task 4 does not arise and no `md5(goal)`
  index was added.
- Task 5 reuses the existing admin user auth rather than introducing a shared
  ingest secret. The job authenticates with `SORRYDB_API_EMAIL` and
  `SORRYDB_API_PASSWORD`, both required whenever `SORRYDB_API_URL` is set. These
  are wired to the `initial-admin-email` and `initial-admin-password` secrets,
  which already existed because the API service bootstraps its admin user from
  them, so no new secret was created. `sorrydb-nightly@` has been granted
  `secretmanager.secretAccessor` on both, and `POST /auth/token` against the
  deployed service returns 200 with those credentials, so the admin user really
  is there. Task 6 is therefore just the URL.

## The decision this plan implements

There are three stores and, until now, no stated source of truth. The decision:

| Store | Role |
|---|---|
| `sorrydb-data` on GitHub | **source of truth** for the dataset. Versioned, tagged daily, already what humans read. |
| `gs://sorrydb-test-nightly/` | private working state: per-repo crawl checkpoints, watermarks, build logs. An implementation detail of the job. |
| Postgres (leaderboard) | **derived read model.** Disposable and rebuildable. Never authoritative. |

The point of naming Postgres "derived" is that staleness stops being a
correctness problem: if it is ever wrong, you rebuild it.

Not in scope here, but the change that would make the decision literal: `crawl()`
should read its database from GitHub at the start of a run rather than from the
bucket, with the bucket keeping its role as the mid-run checkpoint so a crash
still resumes. Today the bucket is the de facto truth because it is what the job
reads.

## Measured facts about the dataset

From the 2026-09-03 run. Use these to sanity check your work.

```
sorries in sorry_database.json      932
sorries in deduplicated_sorries.json 827      (dedup collapses same-goal, keeps latest)
distinct remotes                     26
Lean versions                         8
blame dates span                     41 months
missing blame dates / empty goals     0
```

`deduplicated_sorries.json` exists **only in the GitHub repo**, not in the
bucket: `deduplicate_database` runs inside `publish` and writes into the clone.

## Ownership split

Two branches. Do not mix them.

- **Tasks 1 and 2** are pipeline-side and belong on `master` (this repo). There
  is no migration tooling here.
- **Tasks 3, 4 and 5** belong on the `analytics-endpoints` branch (PR #218),
  which already has `alembic.ini`.
- **Task 6 goes last**, after 2 through 5 have landed. It is the switch that
  turns the whole path on.

---

## Task 1: tolerate GraphQL partial failure (urgent)

**Do this first.** It is silently corrupting the dataset the dashboard will be
built on, and it will recur every single night until fixed.

`sorrydb/database/github_index.py:180`, in `fetch_repos`:

```python
if "errors" in result:
    raise RuntimeError(f"GitHub GraphQL query failed: {result['errors']}")
repos.extend(repo for repo in result["data"]["nodes"] if repo)
```

GraphQL's `nodes(ids:)` is partial by design. An unresolvable id yields `null`
in its slot **plus** a `NOT_FOUND` entry in `errors`, while every other node in
the batch comes back fine in `data`. The very next line already handles this
correctly — `if repo` filters the nulls — but the raise happens first and throws
the good data away.

What happened on 2026-09-03:

```
Could not resolve to a node with the global id of 'R_kgDOTMua-g'
    path: ['nodes', 17]
```

That is `https://github.com/roed-math/gq2-lean`, a 3-star repo indexed on
2026-09-01 and since deleted (`gh api repos/roed-math/gq2-lean` → 404). One dead
repo failed the refresh for all 2,589, so `refresh_repo_metadata` failed open and
every eligibility verdict in the run came from stored metadata. The report says
so plainly:

```
Repo metadata refreshed: REFRESH FAILED, every verdict below came from
stored metadata which may be out of date
```

The node id is in the database forever, so this repeats nightly. Stars and
activity are frozen at their 2026-09-01 values right now.

**Change:** keep the nodes that resolved; raise only on errors that are not
`NOT_FOUND`. A bad token, a rate limit, or a malformed query must still be a
hard failure — those are the cases the fail-open in `refresh_repo_metadata` is
protecting against, and turning them into partial successes would be worse than
the current bug.

Route the ids that did not resolve into the value
`refresh_repo_metadata` already returns for "did not come back". Read its
docstring (`sorrydb/database/build_database.py:114`) before you start: it
deliberately distinguishes

- `None` — the lookup itself failed, so we know nothing about any repo (broken
  token), from
- a list of urls — these specific repos did not come back (repos to retire).

A deleted repo belongs in the second bucket. Putting it in the first is exactly
the bug.

**Test:** mock a GraphQL response with 3 nodes where one is `null` and `errors`
holds a single `NOT_FOUND` for it. Assert the two good repos come back and the
missing one is reported as missing rather than raising. Add a second case with a
non-`NOT_FOUND` error and assert it still raises.

---

## Task 2: post the full set in one request

`orchestration/nightly_update.py:245` chunks the post at `POST_CHUNK_SIZE = 500`
(defined at `:70`), and `:296` posts `deduplicated_sorries.json`.

Two changes:

**2a. Post `sorry_database.json`'s sorries, not the deduplicated file.** All 932,
not 827. Reasoning is in Task 3 — read it before doing this, because the two are
one decision.

**2b. Drop the chunk loop; send the set in one request.** At 500 per chunk, 932
sorries arrive as two requests and **the server cannot tell when the set is
complete**, so it cannot reconcile. That is fatal to Task 3.

Alternatives that were considered and rejected:

- *A run id plus a completion endpoint.* Correct, but adds a table and an
  endpoint to carry "did the run finish", which one request makes unnecessary.
- *Stamp `last_seen` per chunk and have readers filter on `MAX(last_seen)`.*
  Silently hides sorries whenever a run half-fails, because `MAX` then points at
  a partial run. Avoid.

932 sorries is about 1MB. `POST_TIMEOUT` is already 300s. One request is the
smallest correct option.

---

## Task 3: full-set reconciliation in Postgres

### What goes in the table

`sqlsorry`, one row per sorry id — **the full database, 932 rows today, not the
deduplicated 827.**

Every column already exists (`sorrydb/leaderboard/model/sorry.py`), so no schema
work beyond one addition:

```
id (pk, content hash)  remote  branch  commit  lean_version
path  start_line  start_column  end_line  end_column
goal  url
blame_email_hash  blame_date  inclusion_date
```

**Add one column:** `retired_at: datetime | None`, default `NULL`. Meaning: the
sorry is no longer present in the latest crawled dataset.

### Why the full set and not the deduplicated view

Because a challenge must keep resolving against the exact sorry it was created
for, and the deduplicated view is not stable.

`Sorry.__post_init__` (`sorrydb/database/sorry.py:79`) hashes `asdict(self)` minus
`id` and `inclusion_date`. `asdict` includes `repo.commit`, so **the same
unresolved sorry gets a new id every time its repo advances.** The new id then
wins the dedup tiebreak (`deduplicate_sorries_by_goal` keeps the most recent
`inclusion_date`) and the old id drops out of the deduplicated set.

So if the API were fed only the deduplicated view, every open challenge would
have its target leave the set the moment its repo pushed a commit. The agent is
proving sorry A *at commit X*; verification needs A's commit and location, not
A′'s. Keeping every sorry makes that correct by construction.

### Why retirement is a flag and never a delete

`challenge.sorry_id` is a foreign key to `sqlsorry.id`
(`sorrydb/leaderboard/model/challenge.py:35`). Deleting a retired sorry would
break challenge history. A completed challenge must still resolve after the repo
has moved on.

### The change

`sorrydb/leaderboard/database/postgres_database.py:105`, `add_sorries`, becomes
replace-the-set rather than insert-the-new. In one transaction:

```
for ids in the posted set:        upsert, retired_at = NULL
for rows not in the posted set:   retired_at = now()
```

Clearing `retired_at` on upsert matters: a sorry can come back (a repo reverts,
or a run that failed is re-run), and it should stop being retired when it does.

The existing method already computes `seen`, the ids already present, so the
shape of the query you need is there. Note the current implementation is
deliberately dialect-agnostic — a `select` then an insert of the difference —
because the tests run against SQLite while production is Postgres. Keep it that
way; do not reach for `ON CONFLICT`.

Since the endpoint's semantics change from "add" to "replace", consider whether
it should become `PUT /sorries/`. Either way, document it — and see Task 5,
which this change makes a prerequisite rather than a nicety.

### Migration

Alembic revision adding `retired_at` as nullable with no default backfill.
Existing rows get `NULL`, which reads as "current", and the first full-set post
after deploy corrects any that are actually gone.

---

## Task 4: dedup at read time

Two call sites hand sorries to agents:

- `sorrydb/leaderboard/database/postgres_database.py:59` — `select(SQLSorry).order_by(func.random())`
- `sorrydb/leaderboard/database/postgres_database.py:66` — the filtered query

Both need `WHERE retired_at IS NULL` **and** dedup, so agents never see two
copies of one goal. Any new analytics endpoint needs the same `retired_at`
filter.

The dedup key is the goal **string**, and `SQLSorry.goal` already stores exactly
it (`deduplicate_database.py:20` groups on `sorry.debug_info.goal`). So

```sql
DISTINCT ON (goal) ... ORDER BY goal, inclusion_date DESC
```

reproduces `deduplicate_sorries_by_goal` exactly, with no new column and nothing
to keep in sync with the JSON side.

**Indexing wrinkle.** Goal states can be long and a Postgres btree entry caps at
about 8KB, so a plain index on `goal` can fail on a large goal — and it fails at
insert time, not at index creation, so it will surface as a mystery write error
long after you added it. Index `md5(goal)`, or add a hash column used purely for
indexing. If you add a hash column, it must not become the dedup key: the key
stays the string so it cannot drift from `deduplicate_sorries_by_goal`.

At 932 rows a night this is not a performance problem yet. It is a correctness
trap, which is why it is written down.

---

## Task 5: authenticate `POST /sorries/`

`sorrydb/leaderboard/api/sorries.py:14` is unauthenticated and
`sorrydb/leaderboard/api/app.py:112` sets `allow_origins=["*"]`.

Today the worst case is that anyone can insert junk sorries. **After Task 3 the
worst case is that anyone can retire the entire dataset**, because the endpoint
replaces the set. That upgrades this from a follow-up to a prerequisite: land it
with Task 3, not after.

---

## Task 6: turn it on

`.github/workflows/deploy.yml:166` sets `SORRYDB_API_URL=` empty, deliberately:
git is versioned and a bad publish is one revert, whereas Postgres had no undo.
Tasks 3 to 5 give it one.

Done: `deploy.yml` sets it to `https://myapi-redoowlhhq-uc.a.run.app`, the
service's own run.app host. `sorrydb.org` maps to the frontend rather than the
API, and the service is invokable by `allUsers`, so the bearer token from
`/auth/token` is the only credential the post needs.

It had to go last, and specifically after the API was serving a revision with
`PUT /sorries/`: on the revision live before that, `PUT /sorries/` answered 405,
so setting this any earlier would have failed the post at the very end of a
multi-hour crawl.

The credentials it needs are already in place: `PUT /sorries/` is admin only, so
the job reads `SORRYDB_API_EMAIL` and `SORRYDB_API_PASSWORD` from the existing
`initial-admin-email` and `initial-admin-password` secrets, which are the same
two the API service bootstraps its admin user from. `deploy.yml` wires them and
`sorrydb-nightly@` has `secretmanager.secretAccessor` on both. `main()` refuses
to start if the URL is set without them, so with them already wired this really
is one line.

Worth revisiting separately: the nightly authenticating as the human admin
account is convenient rather than right, and that account's password is seven
characters. A dedicated non-interactive service identity would be better, and
matters more now that this endpoint can retire the whole dataset rather than
merely insert rows.

To unblock frontend work before any of this lands, seed Postgres by hand from
`deduplicated_sorries.json` using the curl in
`sorrydb/leaderboard/README.md:108`. Do not wait on this plan for that.

---

## Counts mean occurrences, not unique goals

`/sorries/stats` and the sorry list filter retired rows but deliberately do not
deduplicate, because dedup is global by goal: a list filtered to one repo would
drop rows whose goal also appears in another. So `total` counts sorry
occurrences, 932 on 2026-09-03, while agents are served one per goal, 827. About
11% apart. Label the dashboard number accordingly, or it will disagree with what
agents see and look like a bug in one of the two.

## Verification

After Tasks 1 to 5, trigger a run and check:

```
gcloud run jobs execute sorrydb-nightly --region us-central1
```

1. `update_report.md` no longer says `REFRESH FAILED`, and reports a refreshed
   count with `roed-math/gq2-lean` named as a repo that did not come back.
2. Postgres row count equals the run's `Total number of sorries after update`.
3. Run it twice. The row count must not double, and `retired_at` must be set on
   exactly the ids absent from the second run.
4. Challenge rows created before the second run still resolve to their sorry,
   including where that sorry is now retired. This is the whole point of the
   design; test it explicitly.
5. The agent-facing queries return no two sorries sharing a goal.

There is no Cloud Scheduler cron yet, so nothing runs unattended. Runs happen
only when someone triggers them.

## Known issues deliberately not in this plan

Recorded so they are not rediscovered from scratch.

- **The listing pass is sequential.** ~50 min for 2,343 repos on 2026-09-03. It
  is now scoped to eligible repos only (PR #220), so roughly 420, but it is pure
  network I/O and parallelises trivially.
- **Per-repo "Processing Time" in `update_report.md` is meaningless in morph
  mode.** Every row read ~6h32m because it measures from a timestamp taken
  before the prefetch, so it reports run elapsed time. Real per-repo timings are
  in the bucket build logs: median 8.9m, p90 21.5m, max 55.4m.
- **148 sorries excluded for undetermined parent type**, 14% of the 932 found.
  Three repos lost every sorry they had and so look sorry-free in the data:
  `leanprover/comparator` (26), `leanprover-community/import-graph` (1),
  `pengzhang91/Feige` (1). `digama0/lean4lean` lost 63 of 115. This is
  fail-closed by choice, and the exclusion counter exists so the loss is visible
  rather than silent. If the exclusions cluster on particular Lean versions, the
  fix belongs in the REPL interaction, not in the filter.
- **`SORRYDB_ACTIVITY_DAYS` is currently inert.** All 23 repos it excludes would
  be dropped by the commit-date filter anyway, because `last_activity` is
  repo-level `pushedAt` and is therefore always at least as recent as any
  default-branch commit. It only does real work if the database is re-initialised
  with a starting date further back than the activity window, which is what a
  re-bootstrap would do. Keep it; do not mistake it for an active filter.
- **`morphcloud_runner.py`** (the agent experiment runner, distinct from
  `morphcloud_crawler.py`) still starts VMs with no TTL and no `sorrydb_role`
  metadata, so the crawler's sweeper cannot identify them and they leak. Four
  VMs were lost this way on 2026-09-01, about 45 VM-hours.
