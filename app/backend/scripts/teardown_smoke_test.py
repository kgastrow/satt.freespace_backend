#!/usr/bin/env python3
"""
Teardown script for smoke test data.

Hard-deletes all data associated with a smoke test organization.
This is NOT a soft delete - data is permanently removed.

Uses dynamic table discovery to find all tables referencing organization_id,
eliminating the need to manually maintain a list of tables.

Usage: python scripts/teardown_smoke_test.py --adw-id <adw_id>

Outputs JSON to stdout:
{
  "success": true,
  "deleted_org_slug": "smoke-test-<adw_id>",
  "tables_cleaned": ["user", "organization", ...]
}
"""

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.crud.organization import get_organization_by_slug


async def get_tables_with_organization_id(session: AsyncSession) -> list[str]:
    """
    Dynamically discover all tables that have an organization_id column.

    Returns:
        List of table names that have an organization_id column
    """
    query = text("""
        SELECT table_name
        FROM information_schema.columns
        WHERE column_name = 'organization_id'
        AND table_schema = 'public'
        AND table_name != 'organization'
    """)
    result = await session.execute(query)
    return [row[0] for row in result.fetchall()]


async def get_tables_with_user_id(session: AsyncSession) -> list[str]:
    """
    Dynamically discover all tables that have a user_id column.

    Returns:
        List of table names that have a user_id column
    """
    query = text("""
        SELECT table_name
        FROM information_schema.columns
        WHERE column_name = 'user_id'
        AND table_schema = 'public'
        AND table_name != 'user'
    """)
    result = await session.execute(query)
    return [row[0] for row in result.fetchall()]


async def get_foreign_key_dependencies(session: AsyncSession) -> dict[str, set[str]]:
    """
    Get foreign key dependencies between tables.

    Returns:
        Dict mapping table_name -> set of tables it references (depends on)
    """
    query = text("""
        SELECT
            tc.table_name as child_table,
            ccu.table_name as parent_table
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_schema = 'public'
    """)
    result = await session.execute(query)

    dependencies: dict[str, set[str]] = defaultdict(set)
    for row in result.fetchall():
        child_table, parent_table = row
        dependencies[child_table].add(parent_table)

    return dependencies


def topological_sort(tables: set[str], dependencies: dict[str, set[str]]) -> list[str]:
    """
    Sort tables in dependency order (children before parents).

    Args:
        tables: Set of table names to sort
        dependencies: Dict mapping table -> tables it depends on

    Returns:
        List of tables sorted so dependents come before their dependencies
    """
    # Filter dependencies to only include tables we care about
    filtered_deps = {
        t: deps & tables for t, deps in dependencies.items() if t in tables
    }

    # Add tables with no dependencies
    for table in tables:
        if table not in filtered_deps:
            filtered_deps[table] = set()

    # Kahn's algorithm for topological sort
    # We want children first, so we reverse the relationship
    in_degree: dict[str, int] = {t: 0 for t in tables}
    reverse_deps: dict[str, set[str]] = defaultdict(set)

    for table, deps in filtered_deps.items():
        for dep in deps:
            if dep in tables:
                reverse_deps[dep].add(table)
                in_degree[table] += 1

    # Start with tables that have no dependencies (leaves)
    queue = [t for t in tables if in_degree[t] == 0]
    result = []

    while queue:
        table = queue.pop(0)
        result.append(table)

        for dependent in reverse_deps[table]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Handle any remaining tables (cycles or isolated)
    remaining = tables - set(result)
    result.extend(remaining)

    return result


async def teardown_smoke_test(adw_id: str) -> dict:
    """
    Hard-delete all data for a smoke test organization.

    Uses dynamic table discovery to find all tables with organization_id
    and deletes them in proper FK dependency order.

    Args:
        adw_id: The ADW identifier for the org slug

    Returns:
        Dictionary with success status and deleted tables
    """
    org_slug = f"smoke-test-{adw_id}"

    # Create engine - use direct connection for deletion
    engine = create_async_engine(
        settings.DATABASE_URL_DIRECT,
        echo=False,
        poolclass=NullPool,
    )

    # Create session factory
    async_session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    tables_cleaned = []

    async with async_session_factory() as session:
        try:
            # Find the organization
            org = await get_organization_by_slug(session, org_slug)

            if not org:
                # Nothing to clean up
                await engine.dispose()
                return {
                    "success": True,
                    "deleted_org_slug": org_slug,
                    "message": "Organization not found, nothing to delete",
                    "tables_cleaned": []
                }

            org_id = str(org.id)

            # Dynamically discover tables
            org_tables = await get_tables_with_organization_id(session)
            user_tables = await get_tables_with_user_id(session)
            dependencies = await get_foreign_key_dependencies(session)

            # Get user IDs for this organization
            user_ids_result = await session.execute(
                text('SELECT id FROM "user" WHERE organization_id = :org_id'),
                {"org_id": org_id}
            )
            user_ids = [str(row[0]) for row in user_ids_result.fetchall()]

            # Find tables that reference user but not organization directly
            # These need to be deleted by user_id first
            user_only_tables = set(user_tables) - set(org_tables)

            # Sort user-only tables by dependencies
            if user_only_tables:
                sorted_user_tables = topological_sort(user_only_tables, dependencies)

                # Delete user-scoped tables first
                for table_name in sorted_user_tables:
                    if user_ids:
                        try:
                            for user_id in user_ids:
                                await session.execute(
                                    text(f'DELETE FROM "{table_name}" WHERE user_id = :id'),
                                    {"id": user_id}
                                )
                            tables_cleaned.append(table_name)
                        except Exception as table_error:
                            if "does not exist" not in str(table_error).lower():
                                raise

            # Sort organization tables by dependencies
            all_org_tables = set(org_tables) | {"user", "organization"}
            sorted_org_tables = topological_sort(all_org_tables, dependencies)

            # Ensure 'user' comes before 'organization' at the end
            if "user" in sorted_org_tables:
                sorted_org_tables.remove("user")
            if "organization" in sorted_org_tables:
                sorted_org_tables.remove("organization")
            sorted_org_tables.append("user")
            sorted_org_tables.append("organization")

            # Delete organization-scoped tables
            for table_name in sorted_org_tables:
                try:
                    if table_name == "organization":
                        # Delete the organization by id
                        await session.execute(
                            text(f'DELETE FROM "{table_name}" WHERE id = :org_id'),
                            {"org_id": org_id}
                        )
                    else:
                        # Delete by organization_id
                        await session.execute(
                            text(f'DELETE FROM "{table_name}" WHERE organization_id = :org_id'),
                            {"org_id": org_id}
                        )
                    tables_cleaned.append(table_name)
                except Exception as table_error:
                    # Some tables might not exist or have no data, continue
                    if "does not exist" not in str(table_error).lower():
                        raise

            await session.commit()

        except Exception as e:
            await session.rollback()
            await engine.dispose()
            return {
                "success": False,
                "error": str(e),
                "deleted_org_slug": org_slug,
                "tables_cleaned": tables_cleaned
            }

    await engine.dispose()

    return {
        "success": True,
        "deleted_org_slug": org_slug,
        "tables_cleaned": tables_cleaned
    }


def main():
    """Entry point for the smoke test teardown script."""
    parser = argparse.ArgumentParser(
        description="Hard-delete smoke test organization and all associated data"
    )
    parser.add_argument(
        "--adw-id",
        required=True,
        help="ADW identifier for the org slug to delete (e.g., 'abc123')"
    )
    args = parser.parse_args()

    result = asyncio.run(teardown_smoke_test(args.adw_id))

    # Output JSON to stdout
    print(json.dumps(result, indent=2))

    # Exit with error code if deletion failed
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
