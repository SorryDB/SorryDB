import random
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import extract
from sqlmodel import Session, col, desc, func, select

from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.challenge import Challenge, ChallengeStatus
from sorrydb.leaderboard.model.sorry import SorrySortField, SortOrder, SQLSorry
from sorrydb.leaderboard.model.user import User
from sorrydb.utils.lean_version import parse_lean_version as _parse_version


def _not_retired():
    """The sorry is still present in the latest crawled dataset.

    Every query that answers "what is in the dataset" carries this. The two that
    deliberately do not are get_sorry and get_challenges_for_sorry, because
    challenge history has to keep resolving a sorry after it is retired.
    """
    return col(SQLSorry.retired_at).is_(None)


def _current_sorry_ids():
    """Ids of the sorries an agent may be served: current, one per goal.

    Retired sorries are out, and of what remains only the most recent per goal
    survives. That reproduces deduplicate_sorries_by_goal, which the JSON side
    applies before publishing, so agents never see two copies of one goal. The
    key is the goal string, exactly as it is there, so the two cannot drift.
    The id breaks ties, which max() over inclusion_date leaves arbitrary.

    A window function rather than Postgres's DISTINCT ON, because the tests run
    on SQLite. It also wants no index on goal, which is just as well: goal
    states run long and a btree entry caps at about 8KB, so indexing the column
    would fail on insert of a large goal rather than at index creation.
    """
    ranked = (
        select(
            SQLSorry.id,
            func.row_number()
            .over(
                partition_by=col(SQLSorry.goal),
                order_by=(col(SQLSorry.inclusion_date).desc(), col(SQLSorry.id)),
            )
            .label("rank"),
        )
        .where(_not_retired())
        .subquery()
    )
    return select(ranked.c.id).where(ranked.c.rank == 1)


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
    conditions = [_not_retired()]
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
        return self.session.exec(
            select(SQLSorry)
            .where(col(SQLSorry.id).in_(_current_sorry_ids()))
            .order_by(func.random())
        ).first()

    def _get_unattempted_sorries_statement(self, agent: Agent):
        """Returns a statement for unattempted sorries for a given agent."""
        agent_attempted_sorries_subquery = select(Challenge.sorry_id).where(
            Challenge.agent_id == agent.id
        )
        return select(SQLSorry).where(
            col(SQLSorry.id).not_in(agent_attempted_sorries_subquery),
            col(SQLSorry.id).in_(_current_sorry_ids()),
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

    def replace_sorries(self, sorries: list[SQLSorry]) -> int:
        """Make the stored set match the posted set. Returns how many retired.

        The nightly job posts the whole latest dataset, so this reconciles
        rather than inserts: ids in the post are stored and un-retired, ids
        already stored but absent from it are retired. That is what makes
        Postgres a derived read model, correctable by re-posting, rather than a
        store that only ever grows and can never be told a sorry is gone.

        Clearing retired_at on the way in matters as much as setting it. A sorry
        can come back, when a repo reverts or when a failed run is re-run, and
        it should stop being retired when it does.

        Stored rows need no field updates: a sorry id is a content hash of every
        column except the inclusion date, so a matching id means matching
        content, and the stored inclusion date is the earlier and truer one.

        Deliberately dialect agnostic, a select then per row writes rather than
        ON CONFLICT, because the tests run on SQLite and production on Postgres.
        """
        # keyed by id because build_database.add_sorry does not deduplicate, so
        # the posted set can carry the same id twice
        posted = {sorry.id: sorry for sorry in sorries}
        now = datetime.now(timezone.utc)
        retired = 0

        # ponytail: loads the whole table, 932 rows plus retirements today. Move
        # to two UPDATE ... WHERE id IN statements if it ever stops being small.
        for stored in self.session.exec(select(SQLSorry)).all():
            if posted.pop(stored.id, None) is not None:
                stored.retired_at = None
            elif stored.retired_at is None:
                stored.retired_at = now
                retired += 1
            else:
                continue
            self.session.add(stored)

        self.session.add_all(posted.values())
        self.session.commit()
        return retired

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

        The page and the count are separate statements, so under the default
        READ COMMITTED isolation a write landing between them can leave the two
        slightly out of step. Sorries arrive from one nightly job, so the window
        is small and the effect is a briefly stale total rather than a wrong
        page. Wrap the pair in a REPEATABLE READ transaction if that ever
        stops being an acceptable trade.
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

        As with the sorry list, these are separate statements, so a write
        arriving mid-request can leave the totals and the grouped counts
        momentarily inconsistent with each other.
        """
        total = self.session.exec(
            select(func.count()).select_from(SQLSorry).where(_not_retired())
        ).one()

        # counting the distinct solved sorries straight off the much smaller
        # challenge table avoids running a correlated EXISTS once per sorry row.
        # sorry_id is a foreign key, so every value counted here exists.
        # Restricted to the current sorries so that it stays comparable with
        # total: the service reports unsolved as their difference, and counting
        # challenges against retired sorries could drive that negative.
        solved = self.session.exec(
            select(func.count(func.distinct(col(Challenge.sorry_id)))).where(
                Challenge.status == ChallengeStatus.SUCCESS,
                col(Challenge.sorry_id).in_(
                    select(SQLSorry.id).where(_not_retired())
                ),
            )
        ).one()

        by_remote = self.session.exec(
            select(SQLSorry.remote, func.count().label("count"))
            .where(_not_retired())
            .group_by(col(SQLSorry.remote))
            .order_by(desc("count"), col(SQLSorry.remote))
        ).all()

        by_lean_version = self.session.exec(
            select(SQLSorry.lean_version, func.count().label("count"))
            .where(_not_retired())
            .group_by(col(SQLSorry.lean_version))
            .order_by(desc("count"), col(SQLSorry.lean_version))
        ).all()

        by_blame_month = self.session.exec(
            _month_counts(col(SQLSorry.blame_date)).where(_not_retired())
        ).all()
        by_inclusion_month = self.session.exec(
            _month_counts(col(SQLSorry.inclusion_date)).where(_not_retired())
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
        # a blank value is excluded because the list endpoint reads a blank
        # filter as "no filter", so offering one would advertise a choice that
        # cannot be made
        remotes = self.session.exec(
            select(SQLSorry.remote)
            .where(col(SQLSorry.remote) != "", _not_retired())
            .distinct()
            .order_by(col(SQLSorry.remote))
        ).all()
        lean_versions = self.session.exec(
            select(SQLSorry.lean_version)
            .where(col(SQLSorry.lean_version) != "", _not_retired())
            .distinct()
            .order_by(col(SQLSorry.lean_version))
        ).all()
        return remotes, lean_versions
