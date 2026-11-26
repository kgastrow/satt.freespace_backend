#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
The batch's full check: the full suites once for the branches of several orchestrated workflows, merged onto
origin/main, and who caused each failure (adw_modules/batch_check.py describes how).

Usage: uv run adws/adw_batch_check.py <check-dir>

<check-dir>/request.json: {"n", "run_id", "branches": [{"adw_id", "issue", "title", "branch", "sha"}]}. Writes
<check-dir>/status.json while it runs, then <check-dir>/result.json and a report-<adw_id>.md per branch. The Ore
trigger starts it and hands the results to the workflows (adw_report.py check waits for them).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from adw_modules import batch_check  # noqa: E402

if __name__ == "__main__":
    sys.exit(batch_check.main())
