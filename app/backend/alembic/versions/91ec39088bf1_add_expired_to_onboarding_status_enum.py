"""add_expired_to_onboarding_status_enum

Revision ID: 91ec39088bf1
Revises: f7a38c2335a0
Create Date: 2026-02-21 08:28:01.543142

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '91ec39088bf1'
down_revision: Union[str, None] = 'f7a38c2335a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE onboarding_status ADD VALUE IF NOT EXISTS 'expired'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly.
    # To fully reverse this, you'd need to recreate the type and update the column.
    pass
