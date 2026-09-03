import random
from datetime import datetime
from typing import Any, Optional, Sequence

from sqlalchemy import extract
from sqlmodel import Session, col, desc, func, select

from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.challenge import Challenge, ChallengeStatus
from sorrydb.leaderboard.model.sorry import SorrySortField, SortOrder, SQLSorry
from sorrydb.leaderboard.model.user import User
from sorrydb.utils.lean_version import parse_lean_version as _parse_version


def _solved_sorry_exists():
    """Correlated EXISTS: has this sorry been closed by a successful challenge?"""
    return (
        select(Challenge.id)
        .where(
            col(Challenge.sorry_id) == SQLSorry.id,
            Challenge.status == ChallengeStatus.SUCCESS,
        )
        .exists()
    )


def _sorry_conditions(
    remote: Optional[str] = None,
    lean_version: Optional[str] = None,
    blame_date_from: Optional[datetime] = None,
    blame_date_to: Optional[datetime] = None,
    solved: Optional[bool] = None,
) -> list:
    """Build the WHERE conditions shared by the sorry list and its total count."""
    conditions = []
    if remote is not None:
        conditions.append(col(SQLSorry.remote) == remote)
    if lean_version is not None:
        conditions.append(col(SQLSorry.lean_version) == lean_version)
    if blame_date_from is not None:
        conditions.append(col(SQLSorry.blame_date) >= blame_date_from)
    if blame_date_to is not None:
        conditions.append(col(SQLSorry.blame_date) <= blame_date_to)
    if solved is not None:
        exists = _solved_sorry_exists()
        conditions.append(exists if solved else ~exists)
    return conditions


def _month_counts(date_column):
    """Count rows per calendar month of `date_column`.

    `extract` is used rather than `date_trunc` because SQLAlchemy renders it on
    both Postgres and the SQLite engine the tests run against.
    """
    year = extract("year", date_column).label("year")
    month = extract("month", date_column).label("month")
    return (
        select(year, month, func.count().label("count"))
        .group_by(year, month)
        .order_by(year, month)
    )


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

    def _filter_sorries_by_version(
        self, sorries: Sequence[SQLSorry], agent: Agent
    ) -> list[SQLSorry]:
        """Filter sorries by agent's min/max Lean version constraints."""
        if not agent.min_lean_version and not agent.max_lean_version:
            return list(sorries)
        
        filtered = []
        for sorry in sorries:
            v = _parse_version(sorry.lean_version)
            if agent.min_lean_version and v < _parse_version(agent.min_lean_version):
                continue
            if agent.max_lean_version and v > _parse_version(agent.max_lean_version):
                continue
            filtered.append(sorry)
        return filtered

    def get_random_unattempted_sorry(self, agent: Agent) -> Optional[SQLSorry]:
        statement = self._get_unattempted_sorries_statement(agent)
        candidates = self.session.exec(statement).all()
        filtered = self._filter_sorries_by_version(candidates, agent)
        return random.choice(filtered) if filtered else None

    def get_latest_unattempted_sorry(self, agent: Agent) -> Optional[SQLSorry]:
        statement = self._get_unattempted_sorries_statement(agent)
        statement = statement.order_by(col(SQLSorry.inclusion_date).desc())
        candidates = self.session.exec(statement).all()
        filtered = self._filter_sorries_by_version(candidates, agent)
        return filtered[0] if filtered else None

    def add_sorry(self, sorry: SQLSorry):
        self.session.add(sorry)
        self.session.commit()
        self.session.refresh(sorry)

    def add_sorries(self, sorries: list[SQLSorry]):
        """Insert the sorries that are not stored yet.

        Sorry ids are content hashes and the nightly update re-posts the whole
        deduplicated list, so most of a batch is usually already present.
        Inserting those again would fail the entire batch on the primary key.
        """
        ids = [sorry.id for sorry in sorries]
        seen = set(
            self.session.exec(
                select(SQLSorry.id).where(col(SQLSorry.id).in_(ids))
            ).all()
        )

        new_sorries = []
        for sorry in sorries:
            if sorry.id in seen:
                continue
            seen.add(sorry.id)  # also drops duplicates within the batch
            new_sorries.append(sorry)

        self.session.add_all(new_sorries)
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
        """Get leaderboard ranked by number of successfully completed challenges.
        Only includes visible agents.
        """
        from sorrydb.leaderboard.model.challenge import ChallengeStatus

        # Count successful challenges per agent
        statement = (
            select(
                Agent.id,
                Agent.name,
                Agent.description,
                func.count(Challenge.id).label("completed_challenges")
            )
            .join(Challenge, Challenge.agent_id == Agent.id, isouter=True)
            .where(
                Agent.visible == True,
                (Challenge.status == ChallengeStatus.SUCCESS) | (Challenge.id.is_(None))
            )
            .group_by(Agent.id, Agent.name, Agent.description)
            .order_by(desc("completed_challenges"))
            .limit(limit)
        )

        return self.session.exec(statement).all()

    def get_sorries(
        self,
        limit: int,
        offset: int,
        remote: Optional[str] = None,
        lean_version: Optional[str] = None,
        blame_date_from: Optional[datetime] = None,
        blame_date_to: Optional[datetime] = None,
        solved: Optional[bool] = None,
        sort_by: SorrySortField = SorrySortField.inclusion_date,
        sort_order: SortOrder = SortOrder.desc,
    ) -> tuple[Sequence[Any], int]:
        """Return one page of (sorry, solved) rows and the total matching count.

        Filtering, ordering and paging all happen in SQL so that the table can
        grow without the page cost growing with it.
        """
        conditions = _sorry_conditions(
            remote, lean_version, blame_date_from, blame_date_to, solved
        )
        sort_column = col(getattr(SQLSorry, sort_by.value))
        ordering = (
            sort_column.desc() if sort_order == SortOrder.desc else sort_column.asc()
        )

        statement = (
            select(SQLSorry, _solved_sorry_exists().label("solved"))
            .where(*conditions)
            # the id breaks ties so paging is stable across sorries that share a date
            .order_by(ordering, col(SQLSorry.id))
            .offset(offset)
            .limit(limit)
        )
        rows = self.session.exec(statement).all()

        total = self.session.exec(
            select(func.count()).select_from(SQLSorry).where(*conditions)
        ).one()

        return rows, total

    def get_sorry(self, sorry_id: str) -> Optional[SQLSorry]:
        return self.session.exec(
            select(SQLSorry).where(col(SQLSorry.id) == sorry_id)
        ).first()

    def get_challenges_for_sorry(self, sorry_id: str) -> Sequence[Any]:
        """Return the (challenge, agent_name) history of a single sorry."""
        return self.session.exec(
            select(Challenge, Agent.name)
            .join(Agent, col(Challenge.agent_id) == Agent.id, isouter=True)
            .where(col(Challenge.sorry_id) == sorry_id)
            .order_by(col(Challenge.deadline).desc())
        ).all()

    def get_sorry_stats(self) -> dict:
        """Aggregate the whole sorry table into a handful of grouped rows.

        Every count is computed by the database, so the response size depends on
        the number of distinct repos, versions and months, not on the row count.
        """
        total = self.session.exec(select(func.count()).select_from(SQLSorry)).one()

        # counting the distinct solved sorries straight off the much smaller
        # challenge table avoids running a correlated EXISTS once per sorry row.
        # sorry_id is a foreign key, so every value counted here exists.
        solved = self.session.exec(
            select(func.count(func.distinct(col(Challenge.sorry_id)))).where(
                Challenge.status == ChallengeStatus.SUCCESS
            )
        ).one()

        by_remote = self.session.exec(
            select(SQLSorry.remote, func.count().label("count"))
            .group_by(col(SQLSorry.remote))
            .order_by(desc("count"), col(SQLSorry.remote))
        ).all()

        by_lean_version = self.session.exec(
            select(SQLSorry.lean_version, func.count().label("count"))
            .group_by(col(SQLSorry.lean_version))
            .order_by(desc("count"), col(SQLSorry.lean_version))
        ).all()

        by_blame_month = self.session.exec(
            _month_counts(col(SQLSorry.blame_date))
        ).all()
        by_inclusion_month = self.session.exec(
            _month_counts(col(SQLSorry.inclusion_date))
        ).all()

        return {
            "total": total,
            "solved": solved,
            "by_remote": by_remote,
            "by_lean_version": by_lean_version,
            "by_blame_month": by_blame_month,
            "by_inclusion_month": by_inclusion_month,
        }

    def get_sorry_filter_options(self) -> tuple[Sequence[str], Sequence[str]]:
        """Distinct values the frontend offers as filter dropdowns."""
        remotes = self.session.exec(
            select(SQLSorry.remote).distinct().order_by(col(SQLSorry.remote))
        ).all()
        lean_versions = self.session.exec(
            select(SQLSorry.lean_version).distinct().order_by(col(SQLSorry.lean_version))
        ).all()
        return remotes, lean_versions
