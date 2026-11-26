"""add_announcement_text_color

Revision ID: a1b2c3d4e5f7
Revises: 95cf50fe008c
Create Date: 2026-01-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = '95cf50fe008c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'announcement',
        sa.Column('text_color', sa.String(length=50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('announcement', 'text_color')
