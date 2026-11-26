"""Rename refresh_tokens table and timestamp columns

Revision ID: d7c9e4f2a1b3
Revises: b85560203205
Create Date: 2026-01-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7c9e4f2a1b3'
down_revision: Union[str, None] = 'b85560203205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename table from plural to singular (consistency fix)
    op.rename_table('refresh_tokens', 'refresh_token')

    # Rename columns to match standard timestamp naming convention
    op.alter_column('refresh_token', 'created_at', new_column_name='created_time')
    op.alter_column('refresh_token', 'last_active_at', new_column_name='updated_time')

    # Update partial unique index name for consistency
    # First drop the old index, then recreate with consistent naming
    op.drop_index('uq_refresh_token_active', table_name='refresh_token')
    op.create_index(
        'uq_refresh_token_active',
        'refresh_token',
        ['token'],
        unique=True,
        postgresql_where=sa.text('deleted_time IS NULL')
    )


def downgrade() -> None:
    # Revert column renames
    op.alter_column('refresh_token', 'updated_time', new_column_name='last_active_at')
    op.alter_column('refresh_token', 'created_time', new_column_name='created_at')

    # Revert table rename
    op.rename_table('refresh_token', 'refresh_tokens')

    # Recreate index on old table name
    op.drop_index('uq_refresh_token_active', table_name='refresh_tokens')
    op.create_index(
        'uq_refresh_token_active',
        'refresh_tokens',
        ['token'],
        unique=True,
        postgresql_where=sa.text('deleted_time IS NULL')
    )
