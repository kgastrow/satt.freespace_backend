"""add user_notification table and in_app channel support

Revision ID: a1b2c3d4e5f6
Revises: c4c5256d3098
Create Date: 2026-01-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'c4c5256d3098'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_notification table
    op.create_table(
        'user_notification',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('created_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('organization_id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('link', sa.String(length=2048), nullable=True),
        sa.Column('category_id', UUID(as_uuid=True), nullable=True),
        sa.Column('read_time', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['category_id'], ['notification_category.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for user_notification
    op.create_index('ix_user_notification_organization_id', 'user_notification', ['organization_id'], unique=False)
    op.create_index('ix_user_notification_user_id', 'user_notification', ['user_id'], unique=False)
    op.create_index('ix_user_notification_category_id', 'user_notification', ['category_id'], unique=False)
    op.create_index('ix_user_notification_org_user', 'user_notification', ['organization_id', 'user_id'], unique=False)
    op.create_index('ix_user_notification_user_read', 'user_notification', ['user_id', 'read_time'], unique=False)
    op.create_index('ix_user_notification_user_created', 'user_notification', ['user_id', 'created_time'], unique=False)

    # Add in_app_enabled to user_notification_preference
    op.add_column('user_notification_preference', sa.Column('in_app_enabled', sa.Boolean(), nullable=False, server_default='true'))

    # Add in_app_enabled to user_category_preference
    op.add_column('user_category_preference', sa.Column('in_app_enabled', sa.Boolean(), nullable=False, server_default='true'))

    # Add in_app_enabled to organization_notification_settings
    op.add_column('organization_notification_settings', sa.Column('in_app_enabled', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    # Remove in_app_enabled from organization_notification_settings
    op.drop_column('organization_notification_settings', 'in_app_enabled')

    # Remove in_app_enabled from user_category_preference
    op.drop_column('user_category_preference', 'in_app_enabled')

    # Remove in_app_enabled from user_notification_preference
    op.drop_column('user_notification_preference', 'in_app_enabled')

    # Drop indexes for user_notification
    op.drop_index('ix_user_notification_user_created', table_name='user_notification')
    op.drop_index('ix_user_notification_user_read', table_name='user_notification')
    op.drop_index('ix_user_notification_org_user', table_name='user_notification')
    op.drop_index('ix_user_notification_category_id', table_name='user_notification')
    op.drop_index('ix_user_notification_user_id', table_name='user_notification')
    op.drop_index('ix_user_notification_organization_id', table_name='user_notification')

    # Drop user_notification table
    op.drop_table('user_notification')
