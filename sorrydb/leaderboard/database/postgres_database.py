from typing import Optional, Sequence

from sqlmodel import Session, col, desc, func, select

from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.challenge import Challenge
from sorrydb.leaderboard.model.sorry import SQLSorry
from sorrydb.leaderboard.model.user import User


class SQLDatabase:
    def __init__(self, session: Session):
        self.session = session

    def add_agent(self, agent: Agent) -> None:
        self.session.add(agent)
        self.session.commit()
        self.session.refresh(agent)

    def update_agent(self, agent: Agent) -> None:
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

    def get_random_sorry(self) -> Optional[SQLSorry]:
        return self.session.exec(select(SQLSorry).order_by(func.random())).first()

    def _get_unattempted_sorries_statement(self, agent: Agent):
        """Returns a statement for unattempted sorries for a given agent."""
        agent_attempted_sorries_subquery = select(Challenge.sorry_id).where(
            Challenge.agent_id == agent.id
        )
        return select(SQLSorry).where(
            col(SQLSorry.id).not_in(agent_attempted_sorries_subquery)
        )

    def get_random_unattempted_sorry(self, agent: Agent) -> Optional[SQLSorry]:
        statement = self._get_unattempted_sorries_statement(agent)
        statement = statement.order_by(func.random()).limit(1)
        return self.session.exec(statement).first()

    def get_latest_unattempted_sorry(self, agent: Agent) -> Optional[SQLSorry]:
        statement = self._get_unattempted_sorries_statement(agent)
        # Order by inclusion_date to get the most recent sorries first.
        statement = statement.order_by(col(SQLSorry.inclusion_date).desc()).limit(1)
        return self.session.exec(statement).first()

    def add_sorry(self, sorry: SQLSorry):
        self.session.add(sorry)
        self.session.commit()
        self.session.refresh(sorry)

    def add_sorries(self, sorries: list[SQLSorry]):
        self.session.add_all(sorries)
        self.session.commit()

    def add_user(self, user: User) -> None:
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)

    def get_user_by_email(self, email: str) -> Optional[User]:
        return self.session.exec(select(User).where(User.email == email)).first()

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        return self.session.exec(select(User).where(User.id == user_id)).first()

    def get_agents_by_user(self, user_id: str, skip: int, limit: int) -> Sequence[Agent]:
        return self.session.exec(
            select(Agent).where(Agent.user_id == user_id).offset(skip).limit(limit)
        ).all()

    def get_leaderboard(self, limit: int = 100):
        """Get leaderboard ranked by number of successfully completed challenges."""
        from sorrydb.leaderboard.model.challenge import ChallengeStatus

        # Count successful challenges per agent
        statement = (
            select(
                Agent.id,
                Agent.name,
                func.count(Challenge.id).label("completed_challenges")
            )
            .join(Challenge, Challenge.agent_id == Agent.id, isouter=True)
            .where(
                (Challenge.status == ChallengeStatus.SUCCESS) | (Challenge.id.is_(None))
            )
            .group_by(Agent.id, Agent.name)
            .order_by(desc("completed_challenges"))
            .limit(limit)
        )

        return self.session.exec(statement).all()



