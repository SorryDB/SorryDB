curl -L -X POST \
    -d '{"name": "austins agent"}' \
    -H "Content-Type: application/json" \
    http://127.0.0.1:8000/agents/
curl -sSL 'https://raw.githubusercontent.com/SorryDB/sorrydb-data/refs/heads/master/deduplicated_sorries.json' \
| jq '.sorries' \
| curl -L -X POST \
    -d @- \
    -H "Content-Type: application/json" \
    http://127.0.0.1:8000/sorries/
