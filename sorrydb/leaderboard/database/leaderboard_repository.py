from typing import List, Protocol

from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.challenge import Challenge


class LeaderboardRepository(Protocol):
    """
    Repository protocol defining the interface for leaderboard storage.

    As we add features to the Leaderboard, this might should be split into seperate repositorys,
    i.e., UserRepository, AgentRepository, ChallengeRepository, SorryRepository, etc....
    """

    def add_agent(self, agent: Agent) -> None: ...

    def add_challenge(self, challenge: Challenge) -> None: ...

    def update_challenge(
        self, challenge_id: str, updated_challenge: Challenge
    ) -> None: ...

    def get_agents(self) -> List[Agent]: ...

    def get_agent(self, agent_id: str) -> Agent: ...

    def get_challenges(self, agent_id: str) -> List[Challenge]: ...

    def get_challenge(self, challenge_id: str) -> Challenge: ...
