"""retire sorries absent from the latest dataset

Revision ID: a1c4f0b27e93
Revises: c31a7d0f42b8
Create Date: 2026-09-04 11:20:00.000000

Nullable with no backfill on purpose. NULL reads as "present in the latest
dataset", which is what every existing row is until proven otherwise, and the
first full-set PUT after deploy retires the ones that are actually gone.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c4f0b27e93"
down_revision: Union[str, Sequence[str], None] = "c31a7d0f42b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("sqlsorry", sa.Column("retired_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sqlsorry", "retired_at")
