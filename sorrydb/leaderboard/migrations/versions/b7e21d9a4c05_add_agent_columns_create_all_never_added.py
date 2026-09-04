"""add the agent columns create_all never added

Revision ID: b7e21d9a4c05
Revises: a1c4f0b27e93
Create Date: 2026-09-04 13:10:00.000000

The deployed database predates alembic, so it is stamped at the baseline without
ever having been compared to it. `agent` is missing four columns that the model
declares, because they were added to the model after the table was created and
`create_all` only ever creates tables, never alters them. The schema check in
`run_migrations` caught it and refused to start, which is what it is for:

    The database does not match the models after migrating. Missing:
    agent.description, agent.max_lean_version, agent.min_lean_version,
    agent.visible

c31a7d0f42b8 tried this and was withdrawn on two objections. Both are answered
here rather than left to be done by hand:

- *`agent.user_id` has the same problem and cannot be backfilled.* It does not
  have the same problem in practice: the check named four columns and user_id
  was not among them, so it is already there. Nor could it be fixed here if it
  were, being a NOT NULL foreign key with no value to invent. All four columns
  below are nullable or carry a default, so all four are safe to add.
- *`ADD COLUMN IF NOT EXISTS` is Postgres only.* So do not write DDL that needs
  it. Ask the inspector which columns exist and add only the missing ones. That
  is dialect agnostic, so the leaderboard tests still run on SQLite, and it is
  idempotent, so a database created fresh from the baseline already has all four
  and this revision does nothing to it.

`visible` is NOT NULL, so it gets a server default for the rows already in the
table. The default stays: the model defaults it too, and dropping it would only
add another dialect specific step.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e21d9a4c05"
down_revision: Union[str, Sequence[str], None] = "a1c4f0b27e93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Ordered as the model declares them, though only the names matter here.
MISSING_COLUMNS = (
    sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("description", sa.String(), nullable=True),
    sa.Column("min_lean_version", sa.String(), nullable=True),
    sa.Column("max_lean_version", sa.String(), nullable=True),
)


def _existing_agent_columns() -> set:
    return {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("agent")
    }


def upgrade() -> None:
    existing = _existing_agent_columns()
    for column in MISSING_COLUMNS:
        if column.name not in existing:
            op.add_column("agent", column)


def downgrade() -> None:
    # Only drop what this revision could have added, so a database that already
    # had these columns before it ran keeps them.
    existing = _existing_agent_columns()
    for column in reversed(MISSING_COLUMNS):
        if column.name in existing:
            op.drop_column("agent", column.name)
