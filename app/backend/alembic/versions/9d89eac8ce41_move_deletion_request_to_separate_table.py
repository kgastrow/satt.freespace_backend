"""move_deletion_request_to_separate_table

Revision ID: 9d89eac8ce41
Revises: ef2d605b47d4
Create Date: 2025-12-30 17:55:40.087453

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9d89eac8ce41'
down_revision: Union[str, None] = 'ef2d605b47d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the new organization_deletion_request table
    op.create_table(
        'organization_deletion_request',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('requested_by_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], name='fk_org_deletion_request_org'),
        sa.ForeignKeyConstraint(['requested_by_id'], ['user.id'], name='fk_org_deletion_request_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', name='uq_organization_deletion_request_org')
    )
    op.create_index(
        'ix_organization_deletion_request_organization_id',
        'organization_deletion_request',
        ['organization_id'],
        unique=True
    )

    # Migrate existing deletion request data from organization table
    # This creates records in the new table for any organizations that had deletion requested
    op.execute("""
        INSERT INTO organization_deletion_request (id, created_time, organization_id, requested_by_id)
        SELECT gen_random_uuid(), deletion_requested_time, id, deletion_requested_by
        FROM organization
        WHERE deletion_requested_time IS NOT NULL AND deletion_requested_by IS NOT NULL
    """)

    # Drop the foreign key constraint from organization table
    op.drop_constraint('fk_organization_deletion_requested_by', 'organization', type_='foreignkey')

    # Drop the columns from organization table
    op.drop_column('organization', 'deletion_requested_by')
    op.drop_column('organization', 'deletion_requested_time')


def downgrade() -> None:
    # Add the columns back to organization table
    op.add_column('organization', sa.Column('deletion_requested_time', sa.DateTime(timezone=True), nullable=True))
    op.add_column('organization', sa.Column('deletion_requested_by', sa.UUID(), nullable=True))

    # Migrate data back from the separate table
    op.execute("""
        UPDATE organization o
        SET deletion_requested_time = odr.created_time,
            deletion_requested_by = odr.requested_by_id
        FROM organization_deletion_request odr
        WHERE o.id = odr.organization_id
    """)

    # Re-create the foreign key constraint
    op.create_foreign_key(
        'fk_organization_deletion_requested_by',
        'organization',
        'user',
        ['deletion_requested_by'],
        ['id']
    )

    # Drop the index and table
    op.drop_index('ix_organization_deletion_request_organization_id', table_name='organization_deletion_request')
    op.drop_table('organization_deletion_request')
