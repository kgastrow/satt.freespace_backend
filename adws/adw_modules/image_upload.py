"""Upload a screenshot so GitHub comments, PR bodies and Ore can show it: returns an https URL.

1. Cloudflare R2 (adw_modules/r2_uploader.py, as the smoke test and review use it) when CLOUDFLARE_* is configured
   and boto3 is installed: a public URL that every viewer, Ore included, can load.
2. Otherwise a commit on the repo's `adw-screenshots` branch (ADW_SCREENSHOT_BRANCH), an orphan branch that only
   holds screenshots, pushed with the repo's own git credentials; the URL is
   https://github.com/<owner>/<repo>/raw/<branch>/<path>. In a private repo only people signed in to GitHub with
   access can load it (GitHub comments and PRs show it; Ore shows the link).

GitHub's comment attachments have no API, so they can't be used from a script.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time

BRANCH = os.getenv("ADW_SCREENSHOT_BRANCH", "adw-screenshots")


def _git(args: list[str], cwd: str, env: dict | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True,
                          timeout=timeout)


def upload_r2(path: str, key: str, logger: logging.Logger) -> str | None:
    if not os.getenv("CLOUDFLARE_R2_BUCKET_NAME"):
        return None
    try:
        from adw_modules.r2_uploader import R2Uploader
    except ImportError:                          # boto3 missing
        return None
    up = R2Uploader(logger)
    return up.upload_file(path, key) if up.enabled else None


def repo_slug(cwd: str) -> str | None:
    try:
        from adw_modules.github import extract_repo_path, get_repo_url
        return extract_repo_path(get_repo_url(cwd))
    except Exception:  # noqa: BLE001
        return None


def upload_branch(path: str, dest: str, cwd: str, branch: str = BRANCH, attempts: int = 4) -> str | None:
    """Commit `path` as `dest` on the orphan screenshot branch (created on first use) and push it; retried when
    another workflow pushed a screenshot at the same time."""
    slug = repo_slug(cwd)
    if not slug:
        return None
    blob = _git(["hash-object", "-w", path], cwd).stdout.strip()
    if not blob:
        return None
    ident = {"GIT_AUTHOR_NAME": "ADW", "GIT_AUTHOR_EMAIL": "adw@localhost", "GIT_COMMITTER_NAME": "ADW",
             "GIT_COMMITTER_EMAIL": "adw@localhost"}
    for n in range(attempts):
        fetched = _git(["fetch", "--quiet", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}"], cwd)
        parent = _git(["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"], cwd).stdout.strip() \
            if fetched.returncode == 0 else ""
        fd, index = tempfile.mkstemp(prefix="adw-shot-index-")
        os.close(fd)
        os.unlink(index)
        env = {"GIT_INDEX_FILE": index, **ident}
        try:
            _git(["read-tree", f"{parent}^{{tree}}"] if parent else ["read-tree", "--empty"], cwd, env)
            _git(["update-index", "--add", "--cacheinfo", f"100644,{blob},{dest}"], cwd, env)
            tree = _git(["write-tree"], cwd, env).stdout.strip()
            commit = _git(["commit-tree", tree, *(["-p", parent] if parent else []), "-m", f"ADW screenshot {dest}"],
                          cwd, env).stdout.strip()
        finally:
            if os.path.exists(index):
                os.unlink(index)
        if not commit:
            return None
        if _git(["push", "--quiet", "origin", f"{commit}:refs/heads/{branch}"], cwd).returncode == 0:
            return f"https://github.com/{slug}/raw/{branch}/{dest}"
        time.sleep(1 + n)                         # someone else pushed first: fetch again and retry
    return None


def upload(path: str, adw_id: str, cwd: str, logger: logging.Logger | None = None) -> tuple[str | None, str]:
    """(url or None, how): R2 first, else the screenshot branch."""
    logger = logger or logging.getLogger("adw.image_upload")
    name = os.path.basename(path)
    url = upload_r2(path, f"adw/{adw_id}/screens/{name}", logger)
    if url:
        return url, "r2"
    url = upload_branch(path, f"{adw_id}/{name}", cwd)
    return (url, "branch") if url else (None, "none")
