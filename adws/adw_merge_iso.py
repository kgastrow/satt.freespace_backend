#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic"]
# ///

"""
Merge a pull request; when it conflicts with main, Claude resolves the conflicts first (adw_modules/pr_merge.py
describes the steps).

Usage: uv run adws/adw_merge_iso.py <pr-number>

Ore starts the same through the Ore trigger (`trigger_ore.py --ore-merge <n>`, the Merge button), which shows the
steps as a run. Environment: ADW_MERGE_MODEL (default claude-opus-5-5), ADW_MERGE_CHECKS_MIN (how long to wait for
pending checks, default 30), ADW_MERGE_CLAUDE_MIN (default 40). Notes and Claude's output: agents/merges/pr-<n>/.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

from adw_modules import pr_merge  # noqa: E402
from adw_modules.github import get_github_env  # noqa: E402


def merge_env() -> dict:
    """This environment plus the GitHub token; empty values (e.g. ANTHROPIC_API_KEY= in .env) are dropped, so they
    don't hide Claude's own sign-in."""
    env = {k: v for k, v in os.environ.items() if v != ""}
    env.update(get_github_env() or {})
    return env


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].lstrip("#").isdigit():
        print(__doc__, file=sys.stderr)
        return 2

    def on_step(key, status, note=""):
        print(f"[{status:>8}] {dict(pr_merge.STEPS).get(key, key)}" + (f": {note}" if note else ""), flush=True)

    try:
        out = pr_merge.Merge(sys.argv[1], ROOT, on_step, log=lambda t: None, env=merge_env()).run()
    except pr_merge.MergeError as e:
        print(f"Not merged: {e}", file=sys.stderr)
        return 1
    print(f"Merged PR #{out['number']} ({out['method'] or 'already'}): {out['url']}")
    if out["notes"]:
        print("\nConflict notes:\n" + out["notes"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
