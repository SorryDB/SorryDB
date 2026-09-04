# SorryDB Leaderboard

## Leaderboard backend architecture

The leaderboard backend uses a tiered architecture.

```mermaid
flowchart TD
    Client

    subgraph API_Layer [API Layer]
        FastAPI
    end

    subgraph Service_Layer [Service Layer]
        Challenge[Challenge Service]
        User[User Service]
        Agent[Agent Service]
        Verifier[TBD Verifier Service]
    end

    subgraph Repository_Layer [Repository Layer]
        SQLDatabase
        DB[(Postgres)]
        InMemDB[(SQLite)]
    end

    Client --> FastAPI
    FastAPI --> Challenge
    FastAPI --> Verifier
    FastAPI --> Agent
    FastAPI --> User
    User --> SQLDatabase
    Agent --> SQLDatabase
    Challenge --> SQLDatabase
    Verifier --> SQLDatabase
    SQLDatabase -->|Production Implementation| DB
    SQLDatabase -->|Testing Implementation| InMemDB
```


### API Layer

The API layer uses [FastAPI](https://fastapi.tiangolo.com/) for specifying the API
and automatically generating documentation and [Pydantic](https://docs.pydantic.dev/latest/) for data validation.

### Service Layer

The service layer contains the business logic that drives the leaderboard.
For example, serving challenges, verifying Lean code submitted by agents, etc.


Currently, the service and domain model layers are not clearly separated, but we may separate them in the future as the backend grows.


### Database/Repository Layer

The database layer is currently implemented as an in-memory database. 
Soon we will choose a persistent storage solution.

All filtering, counting, grouping and paging for the read endpoints is expressed
in SQL and evaluated by the database. The sorry table is expected to hold tens of
thousands of rows, so a query must never load a result set into Python in order to
filter or count it.

## Database migrations

The schema is managed with [alembic](https://alembic.sqlalchemy.org/). The
migrations live in `sorrydb/leaderboard/migrations/versions` and ship inside the
package, so they are present in the deployed container.

The application applies any outstanding migrations on startup, in the `lifespan`
handler, holding a Postgres advisory lock so that instances starting at the same
time do not run them concurrently. The wait for that lock is bounded, so an
instance fails and restarts rather than hanging if a holder gets stuck.

A database created before alembic was introduced already holds the baseline
tables but no `alembic_version` row, so `run_migrations` stamps it with the
baseline revision and then upgrades it.

Stamping asserts that a database is already up to date, so after migrating,
startup checks that every table and column the models declare is really there.
`create_all` creates missing tables but never alters an existing one, so a long
lived database can be missing something added to a model later, and no migration
would ever repair it. Checking after the upgrade rather than before it means a
column that a new migration creates is present by the time the check runs, so
adding migrations does not make a legitimately behind database fail to start.

### Creating a migration

Change the SQLModel models, then autogenerate a revision against a database that
is already at the current head:

```sh
DATABASE_URL=postgresql://user:password@localhost:5432/app_db \
    poetry run alembic revision --autogenerate -m "what changed"
```

Read the generated file before committing it. Autogenerate does not detect every
change, and it writes `op.f(...)` index names that must match the names SQLModel
would produce.

### Applying migrations by hand

```sh
DATABASE_URL=postgresql://user:password@localhost:5432/app_db \
    poetry run alembic upgrade head
```

To see the SQL without running it, use `alembic upgrade head --sql`.


## Running the leaderboard server with docker compose

Run `docker compose up --build` to start the leaderboard server and database.
Open `http://127.0.0.1:8080/docs` to view interactive API documentation.

### Using the just command runner
See the `justfile` provides the commands to run the local leaderboard server
using the [just](https://github.com/casey/just) command runner.


### Basic usage with curl

#### Create an agent

```sh
curl -L -X POST \
    -d '{"name": "austins agent"}' \
    -H "Content-Type: application/json" \
    http://127.0.0.1:8080/agents/
```

#### Create a challenge
Replace `agent_id` with the agent id returned from the create agent request

```sh
curl -L -X POST \
    -H "Content-Type: application/json" \
    http://127.0.0.1:8080/agents/{agent_id}/challenges
```


#### Submit a challenge

```sh
curl -L -X POST \
    -d '{"proof":"rfl"}' \
    -H "Content-Type: application/json" \
    http://127.0.0.1:8080/agents/{agent_id}/challenges/{challenge_id}/submit
```

#### Add sorries to the leaderboard

The following command extract the sorries list from deduplicated_sorries.json
and adds them to the leadeboard via the  `POST /sorries/` endpoint:

```sh
curl -sSL 'https://raw.githubusercontent.com/SorryDB/sorrydb-data/refs/heads/master/deduplicated_sorries.json' \
| jq '.sorries' \
| curl -L -X POST \
    -d @- \
    -H "Content-Type: application/json" \
    http://127.0.0.1:8080/sorries/
```

The `doc/populate_server_with_agent_and_sorries.sh` script adds an agent
and a list of sorries to the database for testing locally.


#### Browse sorries

```sh
# one page of sorries, newest first, with the total matching count
curl -sL 'http://127.0.0.1:8080/sorries/?limit=20&offset=0'

# filtered and sorted
curl -sL 'http://127.0.0.1:8080/sorries/?remote=https://github.com/leanprover-community/mathlib4&lean_version=v4.16.0&solved=false&sort_by=blame_date&sort_order=asc'

# a single sorry with its challenge history
curl -sL 'http://127.0.0.1:8080/sorries/{sorry_id}'

# aggregate counts for the analytics views
curl -sL 'http://127.0.0.1:8080/sorries/stats'

# distinct values for the filter dropdowns
curl -sL 'http://127.0.0.1:8080/sorries/filter-options'
```

`GET /sorries/` accepts `limit` (default 50, maximum 200), `offset`, the filters
`remote`, `lean_version`, `blame_date_from`, `blame_date_to` and `solved`, and
sorting via `sort_by` (`inclusion_date` or `blame_date`) and `sort_order`
(`asc` or `desc`). A sorry counts as solved when it has at least one challenge
with status `SUCCESS`.


### Viewing the leaderboard database

You can use a database tool to connect to the postgres database and inspect the contents.
For example with `psql` or `vd`:

```sh
psql postgresql://user:password@localhost:5432/app_db
vd postgresql://user:password@localhost:5432/app_db
```

## Deploying the leaderboard to Google Cloud

Routine deploys are automatic: `.github/workflows/deploy.yml` builds and deploys
the API on every push to `master` that touches it. See doc/DEPLOY.md.

The commands below are the one-time creation of the service, which the workflow
does not do. It only ever passes an image, so the Cloud SQL attachment and the
secrets set here survive every later deploy.

```sh
# Set your gcloud project id as the same as in the console
export PROJECT_ID=sorrydb-test

# Build and push the container
gcloud auth configure-docker gcr.io --quiet
docker build --tag "gcr.io/${PROJECT_ID}/leaderboard_api" \
    --file leaderboard_deployment/Dockerfile .
docker push "gcr.io/${PROJECT_ID}/leaderboard_api"

gcloud run deploy myapi \
    --image "gcr.io/${PROJECT_ID}/leaderboard_api" \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --add-cloudsql-instances "${PROJECT_ID}:us-central1:sorrydb-test" \
    --set-env-vars "DB_HOST=/cloudsql/${PROJECT_ID}:us-central1:sorrydb-test" \
    --set-secrets "DB_PASSWORD=db-password:latest" \
    --set-secrets "INITIAL_ADMIN_EMAIL=initial-admin-email:latest" \
    --set-secrets "INITIAL_ADMIN_PASSWORD=initial-admin-password:latest"
```
