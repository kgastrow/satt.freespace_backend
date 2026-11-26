"""add impersonation_session table

Revision ID: c4c5256d3098
Revises: 34e118f67bc6
Create Date: 2026-01-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'c4c5256d3098'
down_revision: Union[str, None] = '34e118f67bc6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'impersonation_session',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('created_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('impersonator_id', UUID(as_uuid=True), nullable=False),
        sa.Column('target_user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('target_organization_id', UUID(as_uuid=True), nullable=False),
        sa.Column('ended_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ip_address', sa.String(length=255), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['impersonator_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['target_user_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['target_organization_id'], ['organization.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_impersonation_session_impersonator_id'), 'impersonation_session', ['impersonator_id'], unique=False)
    op.create_index(op.f('ix_impersonation_session_target_user_id'), 'impersonation_session', ['target_user_id'], unique=False)
    op.create_index(op.f('ix_impersonation_session_target_organization_id'), 'impersonation_session', ['target_organization_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_impersonation_session_target_organization_id'), table_name='impersonation_session')
    op.drop_index(op.f('ix_impersonation_session_target_user_id'), table_name='impersonation_session')
    op.drop_index(op.f('ix_impersonation_session_impersonator_id'), table_name='impersonation_session')
    op.drop_table('impersonation_session')
