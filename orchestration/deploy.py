import os
from enum import Enum
from typing import NamedTuple

import typer
from prefect.docker.docker_image import DockerImage

from orchestration.update_database_workflow import sorrydb_update_flow

# --- Configuration ---
DEV_DATA_REPO_URL = "git@github.com/SorryDB/sorrydb-data-dev.git"
TEST_DATA_REPO_URL = "git@github.com/SorryDB/sorrydb-data-test.git"
PROD_DATA_REPO_URL = "git@github.com:SorryDB/sorrydb-data.git"


class EnvironmentConfig(NamedTuple):
    name: str
    data_repo_url: str


# This Enum is primarily used for the Typer cli argument
class EnvironmentName(str, Enum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


ENV_CONFIGS: dict[EnvironmentName, EnvironmentConfig] = {
    EnvironmentName.DEV: EnvironmentConfig(
        name=EnvironmentName.DEV.value, data_repo_url=DEV_DATA_REPO_URL
    ),
    EnvironmentName.TEST: EnvironmentConfig(
        name=EnvironmentName.TEST.value, data_repo_url=TEST_DATA_REPO_URL
    ),
    EnvironmentName.PROD: EnvironmentConfig(
        name=EnvironmentName.PROD.value, data_repo_url=PROD_DATA_REPO_URL
    ),
}


# --- CLI ---

app = typer.Typer()


@app.command()
def deploy_sorrydb(
    environment: EnvironmentName = typer.Argument(
        EnvironmentName.TEST,
        help="The environment to deploy to. Accepts 'dev', 'test', 'prod' (case-insensitive).",
    ),
):
    """Deploys the sorrydb update flow to the specified environment."""
    env_config: EnvironmentConfig = ENV_CONFIGS[environment]
    print(f"Deploying to {env_config.name} environment...")
    _deploy_sorrydb_update_flow(env_config=env_config)
    print(f"Successfully initiated deployment for {env_config.name} environment.")


def _deploy_sorrydb_update_flow(env_config: EnvironmentConfig):
    """Helper function to deploy the Prefect flow."""
    sorrydb_update_flow.deploy(
        name=f"{env_config.name.upper()}: sorrydb update deployment",
        work_pool_name="sorrydb-work-pool",
        image=DockerImage(
            name="prefect_update_sorrydb",
            tag=env_config.name.lower(),
            dockerfile="Dockerfile",
        ),
        job_variables={
            # use the ssh credentials of the host machine to access GitHub
            "volumes": [f"{os.path.expanduser('~/.ssh')}:/home/sorrydbuser/.ssh"],
            "mem_limit": "10g",
            "memswap_limit": "10g",
        },
        parameters={"data_repo_url": env_config.data_repo_url},
        push=False,
    )
