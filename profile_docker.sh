docker run \
  --memory=10g \
  --memory-swap=10g \
  --mount type=bind,source=/home/austin/development/lean/sorry-index/SorryDB/data,target=/app/data \
  sorrydb:latest \
  poetry run profiling/profile_update_database.py
