# Running the Leaderboard Agent Locally

This tutorial walks you through running a leaderboard agent against a local instance of the SorryDB leaderboard server.

## Prerequisites

- Docker and Docker Compose installed
- Poetry installed and SorryDB dependencies set up (see main README)
- `jq` command-line tool installed

## Steps

### 1. Start the local leaderboard server

```sh
docker compose -f leaderboard_deployment/compose.yml up --build
```

The server will be available at `http://localhost:8080`

### 2. Create a test user

The server automatically creates an admin user on first startup:
- Email: `admin@sorrydb.org`
- Password: `changeme`

To create a regular user for the agent:

```sh
curl -X POST http://localhost:8080/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@example.com",
    "password": "testpassword"
  }'
```

### 3. Load sorries into the database

```sh
cat doc/sample-sorry-4-24.json \
| jq '.sorries' \
| curl -L -X POST \
    -d @- \
    -H "Content-Type: application/json" \
    http://127.0.0.1:8080/sorries/
```

### 4. Set environment variables

Copy the example environment file and configure your credentials:

```sh
cp .env.example .env
```

Edit `.env` and set:

```
LEADERBOARD_USERNAME=testuser@example.com
LEADERBOARD_PASSWORD=testpassword
LEADERBOARD_HOST=http://127.0.0.1:8080
```

### 5. Run the leaderboard agent

```sh
poetry run python sorrydb/cli/run_leaderboard_agent.py \
  --lean-data YOUR_LEAN_DATA_DIR
```

The agent will:
1. Authenticate with the leaderboard server
2. Request a challenge (a sorry to prove)
3. Attempt to prove it using the configured strategy (by default, tries the `rfl` tactic)
4. Submit the result back to the leaderboard

Results are submitted to the leaderboard API and stored in the database. Progress and results are logged to stdout (or use `--log-file` to save to a file).
