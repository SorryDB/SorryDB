import asyncio
import json
import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from morphcloud.api import MorphCloudClient, Snapshot

from ..database.sorry import RepoInfo, Sorry, SorryJSONEncoder
from ..agents.json_agent import load_sorry_json

load_dotenv()
MORPH_API_KEY = os.environ["MORPH_API_KEY"]
print(MORPH_API_KEY)

# Create a module-level logger
logger = logging.getLogger(__name__)


async def prepare_repository(repo: RepoInfo) -> Snapshot:
    mc = MorphCloudClient(api_key=MORPH_API_KEY)
    snap = await mc.snapshots.acreate(vcpus=4, memory=16384, disk_size=15000, digest="sorrydb-08-10-25")
    steps = []

    # OS deps
    steps.append(
        "apt-get update && apt-get install -y curl git wget htop gnupg python3 python3-pip python3-venv python-is-python3 pipx python3-dev"
        " && curl https://elan.lean-lang.org/elan-init.sh -sSf | sh -s -- -y --default-toolchain leanprover/lean4:v4.21.0"
        " && pipx install poetry"
    )

    # Clone and build repo
    steps.append(
        'git clone https://github.com/SorryDB/SorryDB.git && cd SorryDB && export PATH="$HOME/.local/bin:$PATH"'
        " && poetry install"
    )

    steps.append(
        f'git clone {repo.remote} repo && cd repo && git checkout {repo.commit} && export PATH="$HOME/.elan/bin:$PATH" && (lake exe cache get || true) && lake build'
    )

    return await snap.abuild(steps=steps)


async def prepare_sorries(sorry_url: str):
    SORRY_PATH = Path(__file__).parent.parent.parent / "mock_sorry.json"
    response = requests.get(sorry_url)
    with open(SORRY_PATH, "wb") as file:
        file.write(response.content)

    sorries = load_sorry_json(Path(SORRY_PATH))
    remote_commit_pair_set = {(s.repo.remote, s.repo.commit): s.repo for s in sorries}
    # build snapshots for each unique (remote, commit) pair
    await asyncio.gather(*[prepare_repository(repo) for _, repo in list(remote_commit_pair_set.items())[4:5]])
    return sorries


async def run_agent(sorry: Sorry):
    mc = MorphCloudClient(api_key=MORPH_API_KEY)
    snap = await prepare_repository(sorry.repo)
    cmd = f"cd SorryDB && export PATH=\"$HOME/.elan/bin:$PATH\" && git checkout dev/morphcloud && poetry install && eval $(poetry env activate) && python sorrydb/agents/run_single_agent.py --repo-path repo --sorry-json '{json.dumps(sorry, cls=SorryJSONEncoder)}'"
    with await mc.instances.astart(snapshot_id=snap.id) as instance:
        print(await instance.aexec(cmd))


if __name__ == "__main__":
    # Run with poetry run python -m sorrydb.agents.json_agent_morphcloud
    SORRY_URL = "https://raw.githubusercontent.com/SorryDB/sorrydb-data/refs/heads/master/static_100_varied_recent_deduplicated_sorries.json"
    sorries = asyncio.run(prepare_sorries(SORRY_URL))

    asyncio.run(
        run_agent(
            sorry=sorries[4],
        )
    )
