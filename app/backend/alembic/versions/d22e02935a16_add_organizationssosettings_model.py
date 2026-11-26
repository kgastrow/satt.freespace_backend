"""Add OrganizationSSOSettings model

Revision ID: d22e02935a16
Revises: 9a75512b59e8
Create Date: 2026-01-09 15:49:11.184830

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd22e02935a16'
down_revision: Union[str, None] = '9a75512b59e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create organization_sso_settings table
    op.create_table(
        'organization_sso_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('google_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('google_client_id', sa.String(length=255), nullable=True),
        sa.Column('google_client_secret', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id')
    )


def downgrade() -> None:
    # Drop organization_sso_settings table
    op.drop_table('organization_sso_settings')
