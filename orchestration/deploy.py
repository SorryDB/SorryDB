# Import your flow function
from prefect.docker.docker_image import DockerImage

from orchestration.update_database_workflow import update_sorrydb_data_flow

# --- Configuration ---
DEV_DATA_REPO_URL = "git@github.com:austinletson/sorrydb-data-test-mock-only.git"
TEST_DATA_REPO_URL = "git@github.com:austinletson/sorrydb-data-test.git"
# Local path where the data repository will be cloned.
LOCAL_CLONE_PATH = "/tmp/sorrydb-data-checkout"
DATA_REPO_BRANCH = "master"


def main():
    update_sorrydb_data_flow.serve(name="sorrydb update deployment")


def deploy_dev():
    update_sorrydb_data_flow.deploy(
        name="DEV: sorrydb update deployment",
        work_pool_name="my-docker-pool",
        image=DockerImage(
            name="prefect_update_sorrydb",
            tag="prefect-update-sorrydb",
            dockerfile="Dockerfile",
        ),
        push=False,
    )


def deploy_test():
    update_sorrydb_data_flow.serve(
        name="TEST: sorrydb update deployment",
        parameters={"data_repo_url": TEST_DATA_REPO_URL},
    )


def deploy_prod():
    pass
