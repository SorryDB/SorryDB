from typing import Optional, Sequence

from sqlmodel import Session, select

from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.challenge import Challenge
from sorrydb.leaderboard.model.sorry import SQLSorry


class SQLDatabase:
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

    def update_challenge(self, updated_challenge: Challenge) -> None:
        self.session.add(updated_challenge)
        self.session.commit()
        self.session.refresh(updated_challenge)

    def get_agents(self, skip, limit) -> Sequence[Agent]:
        return self.session.exec(select(Agent).offset(skip).limit(limit)).all()

    def get_agent(self, agent_id: str) -> Agent:
        return self.session.exec(select(Agent).where(Agent.id == agent_id)).one()

    def get_challenges(
        self, agent_id: str, skip: int, limit: int
    ) -> Sequence[Challenge]:
        return self.session.exec(
            select(Challenge)
            .where(Challenge.agent_id == agent_id)
            .offset(skip)
            .limit(limit)
        ).all()

    def get_challenge(self, challenge_id: str) -> Challenge:
        return self.session.exec(
            select(Challenge).where(Challenge.id == challenge_id)
        ).one()

    def get_sorry(self) -> Optional[SQLSorry]:
        return self.session.exec(select(SQLSorry)).first()

    def add_sorry(self, sorry: SQLSorry):
        self.session.add(sorry)
        self.session.commit()
        self.session.refresh(sorry)
