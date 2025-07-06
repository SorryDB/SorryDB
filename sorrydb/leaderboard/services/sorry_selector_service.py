from logging import Logger
from pathlib import Path

from sorrydb.agents.json_agent import load_sorry_json
from sorrydb.leaderboard.database.leaderboard_repository import LeaderboardRepository
from sorrydb.leaderboard.model.sorry import SQLSorry


def select_sample_sorry() -> SQLSorry:
    """
    Test sorry selector which returns a sample sorry from the `sample_sorry_list.json`
    """
    # TODO: This is a hack. If we want to serve sample sorries we should move them into the `leaderboard` module
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    sample_sorries_path = project_root / "doc" / "sample_sorry_list.json"
    sample_sorries = load_sorry_json(json_path=sample_sorries_path)
    return SQLSorry.from_json_sorry(sample_sorries[0])


class NoSorryError(Exception):
    pass


# TODO: create a better sorry selection algorithm
def select_sorry(logger: Logger, repo: LeaderboardRepository) -> SQLSorry:
    if not (sorry := repo.get_sorry()):
        msg = "No sorry to serve"
        logger.error(msg)
        raise NoSorryError
    else:
        return sorry
