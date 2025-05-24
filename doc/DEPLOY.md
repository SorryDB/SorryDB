## Deploying SorryDB updates with Prefect

SorryDB uses [Prefect](https://www.prefect.io/) for workflow orchestration.
The prefect server handles the workflows for all of the SorryDB environments
and allows maintainers to easily operate the database update.

> [!NOTE]  
> Activate the poetry environment before running prefect commands:
> `eval $(poetry env activate)`

### How to set up the prefect server
Run the prefect server:
```sh
prefect server start --host 0.0.0.0
```

### Deploying a SorryDB workflow with a specific environment
Set the `PREFECT_API_URL` environment variable: 
```sh
export PREFECT_API_URL="http://100.77.156.73:4200/api"
```

Deploy the sorrydb in the desired environment

```sh
poetry run deploy_sorrydb [environment]
```


### Deployment environments

Deployment environments allow us to point instances of a SorryDB workflow to different repo lists and databases stored on different GitHub repos.
| Environment | Description                                                                 | Type of Data                                  | GitHub Repo URL                                     |
|-------------|-----------------------------------------------------------------------------|-----------------------------------------------|-----------------------------------------------------|
| DEV         | Used for development of new features.                                       | Primarily mock repos and mock "sorries".      | https://github.com/SorryDB/sorrydb-data-dev         |
| TEST        | Used for testing SorryDB on different repo sets (e.g., all of Reservoir).   | Varied repository sets for comprehensive testing. | https://github.com/SorryDB/sorrydb-data-test        |
| PROD        | Used for the main SorryDB database.                                         | Primary production data for SorryDB.          | https://github.com/SorryDB/sorrydb-data             |


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
