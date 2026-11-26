"""Migrate cron job parameters to SystemConfig

Revision ID: abc123def456
Revises: c78115755a41
Create Date: 2026-01-18 12:00:00.000000

This migration:
1. Reads current parameters from existing cron jobs that use them
2. Creates SystemConfig entries with those values
3. Clears the parameters column in cron_job_definition
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON


# revision identifiers, used by Alembic.
revision: str = 'abc123def456'
down_revision: Union[str, None] = 'c78115755a41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mapping of cron job codes to their SystemConfig keys
CRON_JOB_CONFIG_MAPPING = {
    "cleanup_old_notifications": {
        "param_key": "default_retention_days",
        "config_key": "cleanup.notifications.retention_days",
        "default": "90",
        "description": "Number of days to retain notifications before automatic cleanup",
    },
    "cleanup_deleted_files": {
        "param_key": "default_retention_days",
        "config_key": "cleanup.deleted_files.retention_days",
        "default": "30",
        "description": "Number of days to retain soft-deleted files before permanent deletion",
    },
    "cleanup_old_request_logs": {
        "param_key": "default_retention_days",
        "config_key": "request_logs.retention_days",
        "default": "30",
        "description": "Number of days to retain request logs before automatic cleanup",
    },
}


def upgrade() -> None:
    # Create connection for data migration
    connection = op.get_bind()

    # Get existing cron jobs with parameters
    cron_job_table = sa.table(
        'cron_job_definition',
        sa.column('id', UUID(as_uuid=True)),
        sa.column('code', sa.String),
        sa.column('parameters', JSON),
        sa.column('deleted_time', sa.DateTime(timezone=True)),
    )

    system_config_table = sa.table(
        'system_config',
        sa.column('id', UUID(as_uuid=True)),
        sa.column('key', sa.String),
        sa.column('value', JSON),
        sa.column('description', sa.Text),
        sa.column('created_time', sa.DateTime(timezone=True)),
        sa.column('updated_time', sa.DateTime(timezone=True)),
    )

    # Query existing cron jobs
    cron_jobs = connection.execute(
        sa.select(cron_job_table.c.code, cron_job_table.c.parameters)
        .where(cron_job_table.c.deleted_time.is_(None))
        .where(cron_job_table.c.code.in_(CRON_JOB_CONFIG_MAPPING.keys()))
    ).fetchall()

    # Migrate parameters to SystemConfig
    for job_code, parameters in cron_jobs:
        if job_code not in CRON_JOB_CONFIG_MAPPING:
            continue

        mapping = CRON_JOB_CONFIG_MAPPING[job_code]
        config_key = mapping["config_key"]

        # Check if config already exists
        existing = connection.execute(
            sa.select(system_config_table.c.id)
            .where(system_config_table.c.key == config_key)
        ).fetchone()

        if existing:
            continue  # Don't overwrite existing config

        # Get value from parameters or use default
        value = mapping["default"]
        if parameters and mapping["param_key"] in parameters:
            value = str(parameters[mapping["param_key"]])

        # Insert SystemConfig entry
        connection.execute(
            system_config_table.insert().values(
                id=uuid.uuid4(),
                key=config_key,
                value=value,
                description=mapping["description"],
                created_time=sa.func.now(),
                updated_time=sa.func.now(),
            )
        )

    # Clear parameters from cron jobs that have been migrated
    connection.execute(
        cron_job_table.update()
        .where(cron_job_table.c.code.in_(CRON_JOB_CONFIG_MAPPING.keys()))
        .where(cron_job_table.c.deleted_time.is_(None))
        .values(parameters={})
    )


def downgrade() -> None:
    # Create connection for data migration
    connection = op.get_bind()

    cron_job_table = sa.table(
        'cron_job_definition',
        sa.column('id', UUID(as_uuid=True)),
        sa.column('code', sa.String),
        sa.column('parameters', JSON),
        sa.column('deleted_time', sa.DateTime(timezone=True)),
    )

    system_config_table = sa.table(
        'system_config',
        sa.column('id', UUID(as_uuid=True)),
        sa.column('key', sa.String),
        sa.column('value', JSON),
    )

    # Restore parameters from SystemConfig
    for job_code, mapping in CRON_JOB_CONFIG_MAPPING.items():
        config_key = mapping["config_key"]
        param_key = mapping["param_key"]

        # Get value from SystemConfig
        config = connection.execute(
            sa.select(system_config_table.c.value)
            .where(system_config_table.c.key == config_key)
        ).fetchone()

        if config:
            value = config[0]
            # Try to convert to int if it's a number
            try:
                value = int(value)
            except (ValueError, TypeError):
                pass

            # Update cron job parameters
            connection.execute(
                cron_job_table.update()
                .where(cron_job_table.c.code == job_code)
                .where(cron_job_table.c.deleted_time.is_(None))
                .values(parameters={param_key: value})
            )

    # Delete the SystemConfig entries we created
    config_keys = [m["config_key"] for m in CRON_JOB_CONFIG_MAPPING.values()]
    connection.execute(
        system_config_table.delete()
        .where(system_config_table.c.key.in_(config_keys))
    )
