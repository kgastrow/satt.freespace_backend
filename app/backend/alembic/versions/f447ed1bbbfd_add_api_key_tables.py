"""add_api_key_tables

Revision ID: f447ed1bbbfd
Revises: e33f01836b17
Create Date: 2026-01-10 23:50:16.683922

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'f447ed1bbbfd'
down_revision: Union[str, None] = 'e33f01836b17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create api_key table
    op.create_table(
        'api_key',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('created_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('organization_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('key_hash', sa.String(255), nullable=False),
        sa.Column('prefix', sa.String(8), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id']),
        sa.ForeignKeyConstraint(['created_by'], ['user.id']),
        sa.UniqueConstraint('organization_id', 'name', name='uq_api_key_org_name'),
        sa.UniqueConstraint('key_hash', name='uq_api_key_hash'),
    )
    op.create_index('ix_api_key_organization_id', 'api_key', ['organization_id'])
    op.create_index('ix_api_key_prefix', 'api_key', ['prefix'])

    # Create api_key_permission table
    op.create_table(
        'api_key_permission',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('created_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('organization_id', UUID(as_uuid=True), nullable=False),
        sa.Column('api_key_id', UUID(as_uuid=True), nullable=False),
        sa.Column('permission', sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id']),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_key.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_api_key_permission_organization_id', 'api_key_permission', ['organization_id'])


def downgrade() -> None:
    # Drop api_key_permission table
    op.drop_index('ix_api_key_permission_organization_id', 'api_key_permission')
    op.drop_table('api_key_permission')

    # Drop api_key table
    op.drop_index('ix_api_key_prefix', 'api_key')
    op.drop_index('ix_api_key_organization_id', 'api_key')
    op.drop_table('api_key')
