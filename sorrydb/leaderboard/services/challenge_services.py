from logging import Logger

from sorrydb.leaderboard.database.leaderboard_repository import LeaderboardRepository
from sorrydb.leaderboard.model.challenge import Challenge, ChallengeStatus
from sorrydb.leaderboard.services.agent_services import get_agent
from sorrydb.leaderboard.services.sorry_selector_service import select_sample_sorry


class ChallangeNotFound(Exception):
    pass


def request_sorry_challenge(agent_id: str, logger: Logger, repo: LeaderboardRepository):
    challenge = Challenge(agent_id=agent_id, sorry=select_sample_sorry())

    repo.add_challenge(challenge)

    logger.info(
        f"Created new sample challege with id {challenge.id} for agent {agent_id}"
    )
    return challenge


def submit_proof(
    agent_id: str,
    challenge_id: str,
    proof: str,
    logger: Logger,
    repo: LeaderboardRepository,
):
    try:
        challenge = repo.get_challenge(challenge_id)
    except Exception as e:
        msg = f"Challange not found with id {challenge_id}"
        logger.info(msg)
        raise ChallangeNotFound(msg) from e

    challenge.status = ChallengeStatus.PENDING_VERIFICATION
    challenge.submission = proof

    repo.update_challenge(challenge_id, challenge)
    logger.info(
        f"Received proof: {proof} for agent {agent_id} and challenge {challenge_id}"
    )
    return challenge


def list_challenges(
    agent_id: str,
    leaderboard_repo: LeaderboardRepository,
    logger: Logger,
    skip: int,
    limit: int,
):
    _ = get_agent(
        agent_id, logger, leaderboard_repo
    )  # Raises AgentNotFound if not found
    return leaderboard_repo.get_challenges(agent_id, skip=skip, limit=limit)
