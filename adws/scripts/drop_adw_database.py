#!/usr/bin/env python3
"""Drop isolated database for an ADW workflow.

Usage: python drop_adw_database.py <adw_id>

This script drops the isolated database created for an ADW workflow.
It should be called during worktree cleanup.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

from adw_modules.database_ops import drop_isolated_database, get_database_name_for_adw


def main():
    if len(sys.argv) < 2:
        print("Usage: python drop_adw_database.py <adw_id>")
        sys.exit(1)

    adw_id = sys.argv[1]

    # Setup simple logger
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    db_name = get_database_name_for_adw(adw_id)
    logger.info(f"Dropping database: {db_name}")

    success, error = drop_isolated_database(adw_id, logger)

    if success:
        print(f"Successfully dropped database: {db_name}")
        sys.exit(0)
    else:
        print(f"Failed to drop database: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
