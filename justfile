# Start leaderboard docker compose with changes
up:
    docker compose -f leaderboard_deployment/compose.yml up --build

# Stop docker containers
down:
    docker compose -f leaderboard_deployment/compose.yml down

# Stop docker containers and remove volumes, deleting database
down-v:
    docker compose -f leaderboard_deployment/compose.yml down -v

# Connect to the database with VisiData
db:
    vd postgresql://user:password@localhost:5432/app_db
