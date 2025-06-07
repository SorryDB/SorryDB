from typing import List

from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.challenge import Challenge


class InMemoryLeaderboardDatabase:
    """
    In memory database for testing.
    """

    def __init__(self):
        # Lists for in-memory storage for agents
        self.agents: List[Agent] = []
        self.challenges: List[Challenge] = []

    def add_agent(self, agent: Agent):
        self.agents.append(agent)

    def add_challenge(self, challenge: Challenge):
        self.challenges.append(challenge)

    def update_challenge(self, challenge_id: str, updated_challenge: Challenge):
        for i, updated_challenge in enumerate(self.challenges):
            if updated_challenge.id == challenge_id:
                self.challenges[i] = updated_challenge
                return

    def get_agents(self):
        return self.agents

    def get_challenges(self, agent_id):
        return [c for c in self.challenges if c.agent_id == agent_id]
