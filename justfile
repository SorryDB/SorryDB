# Activate poetry environment
env:
    eval $(poetry env activate)

# Start leaderboard docker compose with changes
up:
    docker compose up --build

# Stop docker containers
down:
    docker compose down

# Stop docker containers and remove volumes, deleting database
down-v:
    docker compose down -v

# Connect to the database with VisiData
db:
    vd postgresql://user:password@localhost:5432/app_db
