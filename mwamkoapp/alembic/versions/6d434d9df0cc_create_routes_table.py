"""Create routes table

Revision ID: 6d434d9df0cc
Revises: 30c1d4691195
Create Date: 2025-11-20 07:50:24.950160

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6d434d9df0cc'
down_revision: Union[str, Sequence[str], None] = '30c1d4691195'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('routes')
    # ### end Alembic commands ###
