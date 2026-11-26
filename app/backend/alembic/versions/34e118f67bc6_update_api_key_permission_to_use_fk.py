"""update_api_key_permission_to_use_fk

Revision ID: 34e118f67bc6
Revises: f447ed1bbbfd
Create Date: 2026-01-11 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '34e118f67bc6'
down_revision: Union[str, None] = 'f447ed1bbbfd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old permission string column
    op.drop_column('api_key_permission', 'permission')

    # Add the new permission_id FK column
    op.add_column(
        'api_key_permission',
        sa.Column('permission_id', UUID(as_uuid=True), nullable=False)
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_api_key_permission_permission_id',
        'api_key_permission',
        'permission',
        ['permission_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Add index on permission_id
    op.create_index(
        'ix_api_key_permission_permission_id',
        'api_key_permission',
        ['permission_id']
    )

    # Add index on api_key_id (was missing)
    op.create_index(
        'ix_api_key_permission_api_key_id',
        'api_key_permission',
        ['api_key_id']
    )

    # Add unique constraint to prevent duplicate grants
    op.create_unique_constraint(
        'uq_api_key_permission',
        'api_key_permission',
        ['api_key_id', 'permission_id']
    )


def downgrade() -> None:
    # Drop unique constraint
    op.drop_constraint('uq_api_key_permission', 'api_key_permission', type_='unique')

    # Drop indexes
    op.drop_index('ix_api_key_permission_api_key_id', 'api_key_permission')
    op.drop_index('ix_api_key_permission_permission_id', 'api_key_permission')

    # Drop foreign key constraint
    op.drop_constraint(
        'fk_api_key_permission_permission_id',
        'api_key_permission',
        type_='foreignkey'
    )

    # Drop permission_id column
    op.drop_column('api_key_permission', 'permission_id')

    # Restore the old permission string column
    op.add_column(
        'api_key_permission',
        sa.Column('permission', sa.String(100), nullable=False)
    )
