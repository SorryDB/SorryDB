from pathlib import Path

from sorrydb.agents.json_agent import load_sorry_json
from sorrydb.database.sorry import Sorry


def select_sample_sorry() -> Sorry:
    """
    Test sorry selector which returns a sample sorry from the `sample_sorry_list.json`
    """
    # TODO: This is a hack. If we want to serve sample sorries we should move them into the `leaderboard` module
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    sample_sorries_path = project_root / "doc" / "sample_sorry_list.json"
    sample_sorries = load_sorry_json(json_path=sample_sorries_path)
    return sample_sorries[0]
