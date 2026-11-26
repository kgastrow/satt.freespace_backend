"""BF-68: nothing in source control contains FCM / Google key material.

Scans every file git would commit (tracked + untracked-not-ignored), like
ParkIT's own secret scan. The patterns are assembled at runtime so this file
does not match itself.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from src.core.config import settings


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = Path(__file__).resolve().parents[2]

_BEGIN = "-----" + "BEGIN"
PEM_PRIVATE_KEY = re.compile(
    _BEGIN + r" (?:RSA |EC |ENCRYPTED )?" + "PRIVATE" + r" KEY-----"
)
SERVICE_ACCOUNT_TYPE = re.compile(r'"type"\s*:\s*"service' + r'_account"')
PRIVATE_KEY_FIELD = re.compile(r'"private' + r'_key"\s*:\s*"[^"]{40,}')
# Google OAuth access tokens / API keys pasted into source
GOOGLE_ACCESS_TOKEN = re.compile(r"\bya29\.[0-9A-Za-z_\-]{40,}")
GOOGLE_API_KEY = re.compile(r"\bAIza" + r"[0-9A-Za-z_\-]{35}\b")

MAX_BYTES = 5 * 1024 * 1024


def _candidate_files() -> list[Path]:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git not available")
    try:
        output = subprocess.run(
            [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout
    except (subprocess.SubprocessError, OSError) as exc:
        pytest.skip(f"not a git checkout: {exc}")
    return [REPO_ROOT / name for name in output.decode().split("\0") if name]


def _text(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None  # binary (PDFs, images)
    return data.decode("utf-8", errors="ignore")


def test_no_key_material_in_source_control():
    offenders: list[str] = []
    for path in _candidate_files():
        text = _text(path)
        if text is None:
            continue
        relative = str(path.relative_to(REPO_ROOT))
        if PEM_PRIVATE_KEY.search(text):
            offenders.append(f"{relative}: PEM private key")
        if SERVICE_ACCOUNT_TYPE.search(text) and PRIVATE_KEY_FIELD.search(text):
            offenders.append(f"{relative}: Google service-account JSON")
        if GOOGLE_ACCESS_TOKEN.search(text):
            offenders.append(f"{relative}: Google OAuth access token")
        if GOOGLE_API_KEY.search(text):
            offenders.append(f"{relative}: Google API key")
    assert offenders == [], "key material committed: " + ", ".join(offenders)


def test_patterns_detect_a_service_account_file():
    """The scan would catch a real service-account JSON."""
    fake = json.dumps(
        {
            "type": "service" + "_account",
            "project_id": "x",
            "private" + "_key": _BEGIN + " PRIVATE" + " KEY-----\\n" + "A" * 64,
        }
    )
    assert SERVICE_ACCOUNT_TYPE.search(fake) and PRIVATE_KEY_FIELD.search(fake)
    assert PEM_PRIVATE_KEY.search(fake.replace("\\n", "\n"))


def test_configured_credentials_path_is_outside_the_repository():
    path = settings.FREESPACE_FCM_CREDENTIALS_PATH
    if not path:
        return  # not configured: push delivery disabled
    resolved = Path(path).resolve()
    assert (
        REPO_ROOT not in resolved.parents
    ), "FCM credentials must live outside the repo"
