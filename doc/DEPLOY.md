## Deploying SorryDB with Prefect

Run the prefect server:
```sh
prefect server start --host 0.0.0.0
```

Set the `PREFECT_API_URL` environment variable: 
```sh
export PREFECT_API_URL="http://100.77.156.73:4200/api"
```

Deploy the sorrydb in the desired environment

```sh
poetry run deploy_sorrydb dev
```


## Deploying SorryDB with Docker

### Building the Docker image

Build a Docker image that includes both Lean and SorryDB:

```shell
git clone https://github.com/SorryDB/SorryDB
cd SorryDB
docker build -t sorrydb .
```

This command builds an image from the `./Dockerfile` tags it as `sorrydb`.

### Updating the Sorry Database

To update a sorry database with the Docker image:

```shell
docker run \
  --mount type=bind,source=/path/to/your/database/directory,target=/data \
  sorrydb:latest \
  poetry run update_db --database-file /data/sorry_database.json
```

Where:
- `--mount type=bind,source=/path/to/your/database/directory,target=/data` mounts your local database directory to `/data` inside the container
- `poetry run sorrydb update --database-path /data/sorry_database.json` is the command to run inside the container

Replace `/path/to/your/database/directory` with the actual path to your database directory.

## Security Considerations

- **Code Execution**: The `update_db` command downloads and executes Lean code from the internet. Running it inside a Docker container provides isolation from your host system.

- **User Permissions**: The Docker image created by the provided Dockerfile is configured to run as a non-root user by default.

- **Volume Mounts**: Only mount the specific directories needed for operation to limit access to your filesystem.
