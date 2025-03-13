## Deploying SorryDB with Docker

### Building the Docker image

Build a Docker image that includes both Lean and SorryDB:

```shell
git clone https://github.com/LennyTaelman/SorryDB
cd SorryDB
docker build -t sorrydb .
```

This command builds an image from the `./Dockerfile` tags it as `sorrydb`.

### Updating the Sorry Database

To update a sorry database with the Docker image:

```shell
docker run \
  --user $(id -u):$(id -g) \
  --mount type=bind,source=/path/to/your/database/directory,target=/data \
  sorrydb:latest \
  poetry run update_db --database-file /data/sorry_database.json
```

Where:
- `--user $(id -u):$(id -g)` runs the container as your current user (recommended for security)
- `--mount type=bind,source=/path/to/your/database/directory,target=/data` mounts your local database directory to `/data` inside the container
- `poetry run update_db --database-file /data/sorry_database.json` is the command to run inside the container

Replace `/path/to/your/database/directory` with the actual path to your database directory.


## Security Considerations

- **Code Execution**: The `update_db` command downloads and executes Lean code from the internet. 
Running it inside a Docker container provides isolation from your host system.

- **User Permissions**: The Docker image created by the provided Dockerfile is configured to run as a non-root user by default. 
Additionally, using the `--user` flag ensures files created in mounted volumes have the correct ownership.

- **Volume Mounts**: Only mount the specific directories needed for operation to limit access to your filesystem.
