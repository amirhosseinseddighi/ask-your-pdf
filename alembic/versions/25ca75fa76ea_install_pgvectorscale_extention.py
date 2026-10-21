"""install vector extensions

Revision ID: 25ca75fa76ea
Revises: 
Create Date: 2026-10-21 12:22:32.502337

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '25ca75fa76ea'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # CASCADE also installs the `vector` extension (pgvector), which vectorscale depends on
    op.execute("CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS vectorscale")
    op.execute("DROP EXTENSION IF EXISTS vector")