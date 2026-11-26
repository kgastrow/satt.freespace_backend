"""Add sso_allowed field to organization_sso_settings

Revision ID: e33f01836b17
Revises: d22e02935a16
Create Date: 2026-01-09 21:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e33f01836b17'
down_revision: Union[str, None] = 'd22e02935a16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add sso_allowed column - master switch controlled by super admin
    op.add_column(
        'organization_sso_settings',
        sa.Column('sso_allowed', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade() -> None:
    # Remove sso_allowed column
    op.drop_column('organization_sso_settings', 'sso_allowed')
