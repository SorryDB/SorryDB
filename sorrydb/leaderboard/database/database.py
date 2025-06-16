from sorrydb.leaderboard.database.leaderboard_repository import LeaderboardRepository
from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.challenge import Challenge


# TODO: We should probably replace this with an in-memory fake sqlalchemy db engine
# to support concurrent access and better align with the actual database
class InMemoryLeaderboardDatabase(LeaderboardRepository):
    """
    In memory database for testing.

    Currently, does not support async so could behave poorly in more complicated tests.
    """

    def __init__(self):
        # lists for in-memory storage for agents
        self.agents: list[Agent] = []
        self.challenges: list[Challenge] = []

    def add_agent(self, agent: Agent):
        self.agents.append(agent)

    def add_challenge(self, challenge: Challenge):
        self.challenges.append(challenge)

    def update_challenge(self, challenge_id: str, updated_challenge: Challenge):
        for i, updated_challenge in enumerate(self.challenges):
            if updated_challenge.id == challenge_id:
                self.challenges[i] = updated_challenge
                return

    def get_agents(self, skip, limit):
        return self.agents[skip : skip + limit]

    def get_agent(self, agent_id: str):
        return next(a for a in self.agents if a.id == agent_id)

    def get_challenges(self, agent_id: str, skip: int, limit: int) -> list[Challenge]:
        agent_challenges = [c for c in self.challenges if c.agent_id == agent_id]
        return agent_challenges[skip : skip + limit]

    def get_challenge(self, challenge_id: str) -> Challenge:
        return next(c for c in self.challenges if c.id == challenge_id)
