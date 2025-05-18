import os
from typing import NamedTuple

from prefect.docker.docker_image import DockerImage

from orchestration.update_database_workflow import sorrydb_update_flow

# --- Configuration ---
DEV_DATA_REPO_URL = "git@github.com:austinletson/sorrydb-data-test-mock-only.git"
TEST_DATA_REPO_URL = "git@github.com:austinletson/sorrydb-data-test.git"
PROD_DATA_REPO_URL = "git@github.com:SorryDB/sorrydb-data.git"


class EnvironmentConfig(NamedTuple):
    name: str
    data_repo_url: str


DEV_ENV_CONFIG = EnvironmentConfig(name="dev", data_repo_url=DEV_DATA_REPO_URL)
TEST_ENV_CONFIG = EnvironmentConfig(name="test", data_repo_url=TEST_DATA_REPO_URL)
PROD_ENV_CONFIG = EnvironmentConfig(name="prod", data_repo_url=PROD_DATA_REPO_URL)


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


def deploy_dev():
    _deploy_sorrydb_update_flow(env_config=DEV_ENV_CONFIG)


def deploy_test():
    _deploy_sorrydb_update_flow(env_config=TEST_ENV_CONFIG)


def deploy_prod():
    _deploy_sorrydb_update_flow(env_config=PROD_ENV_CONFIG)
