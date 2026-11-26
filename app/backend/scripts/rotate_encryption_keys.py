#!/usr/bin/env python3
"""
Encryption key rotation script.

This script re-encrypts all encrypted data in the database with the current
primary encryption key. Run this after rotating to a new ENCRYPTION_KEY.

Key Rotation Process:
1. Generate new key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
2. Move current ENCRYPTION_KEY to ENCRYPTION_KEY_PREVIOUS in config
3. Set new key as ENCRYPTION_KEY
4. Run this script: python scripts/rotate_encryption_keys.py
5. Verify all data is accessible
6. Remove ENCRYPTION_KEY_PREVIOUS from config

Usage:
    python scripts/rotate_encryption_keys.py [--dry-run] [--verbose]

Options:
    --dry-run   Show what would be rotated without making changes
    --verbose   Show detailed progress for each record

Environment:
    Requires ENCRYPTION_KEY to be set (and optionally ENCRYPTION_KEY_PREVIOUS)
"""

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.core.encryption import (
    EncryptionKeyInfo,
    get_key_info,
    rotate_encrypted_value,
    validate_encryption_key,
)


@dataclass
class EncryptedFieldConfig:
    """Configuration for an encrypted field that needs rotation."""

    model_name: str
    table_name: str
    field_name: str
    id_field: str = "id"


@dataclass
class RotationResult:
    """Result of rotating a single field."""

    model_name: str
    field_name: str
    record_id: str
    rotated: bool
    error: Optional[str] = None


@dataclass
class RotationSummary:
    """Summary of the rotation process."""

    total_records: int = 0
    total_fields: int = 0
    rotated_fields: int = 0
    skipped_fields: int = 0  # Already using primary key
    null_fields: int = 0  # NULL values, nothing to rotate
    error_count: int = 0
    errors: List[RotationResult] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


# Define all encrypted fields in the system
# Add new encrypted fields here as they are created
ENCRYPTED_FIELDS: List[EncryptedFieldConfig] = [
    # OrganizationEmailSettings - org-level email credentials
    EncryptedFieldConfig(
        model_name="OrganizationEmailSettings",
        table_name="organization_email_settings",
        field_name="smtp_username",
    ),
    EncryptedFieldConfig(
        model_name="OrganizationEmailSettings",
        table_name="organization_email_settings",
        field_name="smtp_password",
    ),
    EncryptedFieldConfig(
        model_name="OrganizationEmailSettings",
        table_name="organization_email_settings",
        field_name="sendgrid_api_key",
    ),
    # SystemConfig - platform-level encrypted settings
    # Note: SystemConfig stores encrypted values for certain keys like email.sendgrid.api_key
    # These are handled separately below since they're identified by key, not by field
]


def print_header(text: str) -> None:
    """Print a section header."""
    print()
    print("=" * 60)
    print(text)
    print("=" * 60)


def print_key_info(key_info: EncryptionKeyInfo) -> None:
    """Print information about current encryption keys."""
    print("\nEncryption Key Status:")
    print(f"  Primary key configured: {key_info.has_primary_key}")
    print(f"  Previous key configured: {key_info.has_previous_key}")
    print(f"  Using fallback (JWT-derived): {key_info.using_fallback}")
    print(f"  Key source: {key_info.key_source}")

    if key_info.using_fallback:
        print("\n  WARNING: Using JWT-derived fallback key.")
        print("  This is insecure for production. Set ENCRYPTION_KEY in config.")
    elif not key_info.has_previous_key:
        print("\n  NOTE: No previous key configured.")
        print("  If you're rotating keys, set ENCRYPTION_KEY_PREVIOUS first.")


async def rotate_table_field(
    session: AsyncSession,
    field_config: EncryptedFieldConfig,
    dry_run: bool,
    verbose: bool,
) -> Tuple[int, int, int, int, List[RotationResult]]:
    """
    Rotate encrypted values for a single field in a table.

    Returns:
        Tuple of (total, rotated, skipped, errors, error_details)
    """
    from sqlalchemy import text

    # Get all non-deleted records with non-null values for this field
    query = text(f"""
        SELECT id, {field_config.field_name}
        FROM {field_config.table_name}
        WHERE deleted_time IS NULL
          AND {field_config.field_name} IS NOT NULL
    """)

    result = await session.execute(query)
    records = result.fetchall()

    total = len(records)
    rotated = 0
    skipped = 0
    errors = 0
    error_details: List[RotationResult] = []

    for record in records:
        record_id = str(record[0])
        encrypted_value = record[1]

        try:
            new_value, was_rotated = rotate_encrypted_value(encrypted_value)

            if was_rotated:
                if not dry_run:
                    update_query = text(f"""
                        UPDATE {field_config.table_name}
                        SET {field_config.field_name} = :new_value,
                            updated_time = :updated_time
                        WHERE id = :record_id
                    """)
                    await session.execute(
                        update_query,
                        {
                            "new_value": new_value,
                            "updated_time": datetime.now(timezone.utc),
                            "record_id": record_id,
                        },
                    )
                rotated += 1
                if verbose:
                    action = "Would rotate" if dry_run else "Rotated"
                    print(
                        f"    {action}: {field_config.model_name}.{field_config.field_name} "
                        f"(id: {record_id[:8]}...)"
                    )
            else:
                skipped += 1
                if verbose:
                    print(
                        f"    Skipped (already primary): {field_config.model_name}.{field_config.field_name} "
                        f"(id: {record_id[:8]}...)"
                    )

        except Exception as e:
            errors += 1
            error_result = RotationResult(
                model_name=field_config.model_name,
                field_name=field_config.field_name,
                record_id=record_id,
                rotated=False,
                error=str(e),
            )
            error_details.append(error_result)
            print(
                f"    ERROR: {field_config.model_name}.{field_config.field_name} "
                f"(id: {record_id[:8]}...): {e}"
            )

    return total, rotated, skipped, errors, error_details


async def rotate_system_config_secrets(
    session: AsyncSession,
    dry_run: bool,
    verbose: bool,
) -> Tuple[int, int, int, int, List[RotationResult]]:
    """
    Rotate encrypted values in SystemConfig.

    Some SystemConfig keys store encrypted values (e.g., email.sendgrid.api_key).
    These are identified by key pattern rather than by field.
    """
    from sqlalchemy import text

    # Keys that store encrypted values
    encrypted_keys = [
        "email.sendgrid.api_key",
        # Add other encrypted SystemConfig keys here
    ]

    total = 0
    rotated = 0
    skipped = 0
    errors = 0
    error_details: List[RotationResult] = []

    for key in encrypted_keys:
        query = text("""
            SELECT id, key, value
            FROM system_config
            WHERE key = :key
              AND deleted_time IS NULL
              AND value IS NOT NULL
              AND value != ''
        """)

        result = await session.execute(query, {"key": key})
        record = result.fetchone()

        if not record:
            continue

        total += 1
        record_id = str(record[0])
        encrypted_value = record[2]

        try:
            new_value, was_rotated = rotate_encrypted_value(encrypted_value)

            if was_rotated:
                if not dry_run:
                    update_query = text("""
                        UPDATE system_config
                        SET value = :new_value,
                            updated_time = :updated_time
                        WHERE id = :record_id
                    """)
                    await session.execute(
                        update_query,
                        {
                            "new_value": new_value,
                            "updated_time": datetime.now(timezone.utc),
                            "record_id": record_id,
                        },
                    )
                rotated += 1
                if verbose:
                    action = "Would rotate" if dry_run else "Rotated"
                    print(f"    {action}: SystemConfig.{key}")
            else:
                skipped += 1
                if verbose:
                    print(f"    Skipped (already primary): SystemConfig.{key}")

        except Exception as e:
            errors += 1
            error_result = RotationResult(
                model_name="SystemConfig",
                field_name=key,
                record_id=record_id,
                rotated=False,
                error=str(e),
            )
            error_details.append(error_result)
            print(f"    ERROR: SystemConfig.{key}: {e}")

    return total, rotated, skipped, errors, error_details


async def rotate_all_encrypted_data(
    dry_run: bool = False,
    verbose: bool = False,
) -> RotationSummary:
    """
    Rotate all encrypted data in the database to use the current primary key.

    Args:
        dry_run: If True, show what would be rotated without making changes
        verbose: If True, show detailed progress for each record

    Returns:
        RotationSummary with results
    """
    summary = RotationSummary()

    # Check key configuration
    key_info = get_key_info()
    print_header("Encryption Key Rotation")
    print_key_info(key_info)

    if key_info.using_fallback:
        print("\nWARNING: Cannot rotate with fallback key.")
        print("Please configure ENCRYPTION_KEY before rotating.")
        return summary

    if dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***")

    # Connect to database
    print("\nConnecting to database...")
    engine = create_async_engine(
        settings.DATABASE_URL_DIRECT,
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 100,
            "command_timeout": 60,
        },
    )
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            # Process each encrypted field
            print("\nRotating encrypted fields...")

            for field_config in ENCRYPTED_FIELDS:
                print(f"\n  Processing {field_config.model_name}.{field_config.field_name}...")

                total, rotated, skipped, errors, error_details = await rotate_table_field(
                    session, field_config, dry_run, verbose
                )

                summary.total_records += total
                summary.total_fields += total
                summary.rotated_fields += rotated
                summary.skipped_fields += skipped
                summary.error_count += errors
                summary.errors.extend(error_details)

                print(f"    Found: {total}, Rotated: {rotated}, Skipped: {skipped}, Errors: {errors}")

            # Process SystemConfig secrets
            print("\n  Processing SystemConfig encrypted values...")

            total, rotated, skipped, errors, error_details = await rotate_system_config_secrets(
                session, dry_run, verbose
            )

            summary.total_fields += total
            summary.rotated_fields += rotated
            summary.skipped_fields += skipped
            summary.error_count += errors
            summary.errors.extend(error_details)

            print(f"    Found: {total}, Rotated: {rotated}, Skipped: {skipped}, Errors: {errors}")

            # Commit all changes
            if not dry_run:
                await session.commit()
                print("\n  Changes committed to database.")
            else:
                await session.rollback()
                print("\n  Dry run complete - no changes made.")

        except Exception as e:
            await session.rollback()
            print(f"\nERROR: Rotation failed: {e}")
            import traceback

            traceback.print_exc()
            raise

    await engine.dispose()

    # Print summary
    print_header("Rotation Summary")

    action = "Would rotate" if dry_run else "Rotated"
    print(f"\n  Total encrypted values found: {summary.total_fields}")
    print(f"  {action}: {summary.rotated_fields}")
    print(f"  Already using primary key: {summary.skipped_fields}")
    print(f"  Errors: {summary.error_count}")

    if summary.errors:
        print("\n  Errors encountered:")
        for error in summary.errors:
            print(f"    - {error.model_name}.{error.field_name} (id: {error.record_id[:8]}...)")
            print(f"      {error.error}")

    if not dry_run and summary.rotated_fields > 0:
        print("\n  Next steps:")
        print("  1. Verify that all data can be read correctly")
        print("  2. Test application functionality")
        print("  3. Once verified, remove ENCRYPTION_KEY_PREVIOUS from config")

    return summary


def main():
    """Entry point for the key rotation script."""
    parser = argparse.ArgumentParser(
        description="Rotate encrypted data to use the current primary encryption key.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be rotated without making changes",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress for each record",
    )
    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Generate a new encryption key and exit",
    )
    parser.add_argument(
        "--check-keys",
        action="store_true",
        help="Check encryption key configuration and exit",
    )

    args = parser.parse_args()

    if args.generate_key:
        from src.core.encryption import generate_encryption_key

        key = generate_encryption_key()
        print("Generated new encryption key:")
        print(key)
        print("\nAdd this to your config.json under 'encryption.key'")
        return

    if args.check_keys:
        key_info = get_key_info()
        print_key_info(key_info)

        if settings.ENCRYPTION_KEY:
            print(f"\n  ENCRYPTION_KEY valid: {validate_encryption_key(settings.ENCRYPTION_KEY)}")
        if settings.ENCRYPTION_KEY_PREVIOUS:
            print(
                f"  ENCRYPTION_KEY_PREVIOUS valid: {validate_encryption_key(settings.ENCRYPTION_KEY_PREVIOUS)}"
            )
        return

    # Run the rotation
    asyncio.run(rotate_all_encrypted_data(dry_run=args.dry_run, verbose=args.verbose))


if __name__ == "__main__":
    main()
