"""add_deleted_time_to_settings_models

Revision ID: 9a75512b59e8
Revises: 9d89eac8ce41
Create Date: 2025-12-30 18:12:01.122759

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a75512b59e8'
down_revision: Union[str, None] = '9d89eac8ce41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add deleted_time column to user_notification_preference
    op.add_column(
        'user_notification_preference',
        sa.Column('deleted_time', sa.DateTime(timezone=True), nullable=True)
    )

    # Add deleted_time column to user_category_preference
    op.add_column(
        'user_category_preference',
        sa.Column('deleted_time', sa.DateTime(timezone=True), nullable=True)
    )

    # Add deleted_time column to file_usage
    op.add_column(
        'file_usage',
        sa.Column('deleted_time', sa.DateTime(timezone=True), nullable=True)
    )

    # Add deleted_time column to organization_notification_settings
    op.add_column(
        'organization_notification_settings',
        sa.Column('deleted_time', sa.DateTime(timezone=True), nullable=True)
    )

    # Add deleted_time column to organization_file_settings
    op.add_column(
        'organization_file_settings',
        sa.Column('deleted_time', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('organization_file_settings', 'deleted_time')
    op.drop_column('organization_notification_settings', 'deleted_time')
    op.drop_column('file_usage', 'deleted_time')
    op.drop_column('user_category_preference', 'deleted_time')
    op.drop_column('user_notification_preference', 'deleted_time')
