"""retired: reconcile agent columns

Revision ID: c31a7d0f42b8
Revises: 8f7763c80e19
Create Date: 2026-09-02 06:30:00.000000

This revision once added the Agent columns that create_all could not add. It was
withdrawn because it could not be made correct: agent.user_id has the same
problem and is a NOT NULL foreign key with no value to backfill, and its
ADD COLUMN IF NOT EXISTS is Postgres only, which broke startup on every other
dialect. `run_migrations` now checks the schema after migrating instead.

The file stays as a no-op so that a database which already reached this revision
can still resolve it and walk forward. Deleting it would leave such a database
unable to identify its own version, and the startup handler would fail there
with no way out. It can go once no database is at this revision.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "c31a7d0f42b8"
down_revision: Union[str, Sequence[str], None] = "8f7763c80e19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Deliberately empty. See the module docstring."""


def downgrade() -> None:
    """Deliberately empty. See the module docstring."""
