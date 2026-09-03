"""reconcile agent columns that create_all could not add

Revision ID: c31a7d0f42b8
Revises: 8f7763c80e19
Create Date: 2026-09-02 06:30:00.000000

`visible`, `description`, `min_lean_version` and `max_lean_version` were added to
the Agent model after the database had already been created. The only schema
tool at the time was SQLModel's create_all, which creates missing tables but
never alters an existing one, so a long lived database may still be without
them. Stamping such a database with the baseline revision would otherwise record
it as already up to date and hide the drift for good.

Every statement is idempotent, so this is a no-op on a database that already has
the columns, which includes every database created from the baseline migration.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c31a7d0f42b8"
down_revision: Union[str, Sequence[str], None] = "8f7763c80e19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the columns only where they are missing."""
    # `visible` is NOT NULL in the model, so existing rows need a value. The
    # default is dropped afterwards to match the model, which has no server default.
    op.execute("ALTER TABLE agent ADD COLUMN IF NOT EXISTS visible BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE agent ALTER COLUMN visible DROP DEFAULT")

    op.execute("ALTER TABLE agent ADD COLUMN IF NOT EXISTS description VARCHAR")
    op.execute("ALTER TABLE agent ADD COLUMN IF NOT EXISTS min_lean_version VARCHAR")
    op.execute("ALTER TABLE agent ADD COLUMN IF NOT EXISTS max_lean_version VARCHAR")


def downgrade() -> None:
    """Deliberately empty.

    These columns belong to the current Agent model, so dropping them here would
    take the schema further from the model rather than closer to it.
    """
