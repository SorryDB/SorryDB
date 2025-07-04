from typing import Optional, Sequence

from sqlmodel import Session, select

from sorrydb.leaderboard.database.leaderboard_repository import LeaderboardRepository
from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.challenge import Challenge


class PostgresDatabase(LeaderboardRepository):
    def __init__(self, session: Session):
        self.session = session

    def add_agent(self, agent: Agent) -> None:
        self.session.add(agent)
        self.session.commit()
        self.session.refresh(agent)

    def add_challenge(self, challenge: Challenge) -> None:
        self.session.add(challenge)
        self.session.commit()
        self.session.refresh(challenge)

    def update_challenge(
        self, challenge_id: str, updated_challenge: Challenge
    ) -> None: ...

    def get_agents(self, skip, limit) -> Sequence[Agent]:
        return self.session.exec(select(Agent).offset(skip).limit(limit)).all()

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return self.session.exec(select(Agent).where(Agent.id == agent_id)).first()

    def get_challenges(
        self, agent_id: str, skip: int, limit: int
    ) -> Sequence[Challenge]:
        return self.session.exec(
            select(Challenge)
            .where(Challenge.agent_id == agent_id)
            .offset(skip)
            .limit(limit)
        ).all()

    def get_challenge(self, challenge_id: str) -> Optional[Challenge]:
        return self.session.exec(
            select(Challenge).where(Challenge.id == challenge_id)
        ).first()
