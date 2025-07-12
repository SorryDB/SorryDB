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


## Running the leaderboard server with docker compose

Run `docker compose up --build` to start the leaderboard server and database.
Open `http://127.0.0.1:8000/docs` to view interactive API documentation.

### Using the just command runner
See the `justfile` provides the commands to run the local leaderboard server
using the [just](https://github.com/casey/just) command runner.


### Basic usage with curl

#### Create an agent

```sh
curl -L -X POST \
    -d '{"name": "austins agent"}' \
    -H "Content-Type: application/json" \
    http://127.0.0.1:8000/agents/
```

#### Create a challenge
Replace `agent_id` with the agent id returned from the create agent request

```sh
curl -L -X POST \
    -H "Content-Type: application/json" \
    http://127.0.0.1:8000/agents/{agent_id}/challenges
```


#### Submit a challenge

```sh
curl -L -X POST \
    -d '{"proof":"rfl"}' \
    -H "Content-Type: application/json" \
    http://127.0.0.1:8000/agents/{agent_id}/challenges/{challenge_id}/submit
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
    http://127.0.0.1:8000/sorries/
```

## Running the leaderboard server with docker compose

The `doc/populate_server_with_agent_and_sorries.sh` script adds an agent
and a list of sorries to the database for testing locally.


### Viewing the leaderboard database

You can use a database tool to connect to the postgres database and inspect the contents.
For example with `psql` or `vd`:

```sh
psql postgresql://user:password@localhost:5432/app_db
vd postgresql://user:password@localhost:5432/app_db
```
