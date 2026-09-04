#!/bin/bash
# Seed a local leaderboard. Both endpoints need a logged in user, and the sorry
# set replaces rather than appends, so it needs an admin one.
#
#   TOKEN=$(curl -sL -X POST -d 'username=admin@example.com&password=...' \
#       http://127.0.0.1:8080/auth/token | jq -r .access_token) \
#   ./doc/populate_server_with_agent_and_sorries.sh

curl -L -X POST \
    -d '{"name": "austins agent"}' \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    http://127.0.0.1:8080/agents/
curl -sSL 'https://raw.githubusercontent.com/SorryDB/sorrydb-data/refs/heads/master/sorry_database.json' \
| jq '.sorries' \
| curl -L -X PUT \
    -d @- \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    http://127.0.0.1:8080/sorries/
