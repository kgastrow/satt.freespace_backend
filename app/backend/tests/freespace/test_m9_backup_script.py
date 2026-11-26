"""M9: backup script argument/environment validation (BF-83). Never dumps a real DB."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "backup" / "freespace_backup.sh"
)
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def run(env: dict[str, str], path: str | None = None):
    base = {"PATH": path or "/usr/bin:/bin", "HOME": "/nonexistent"}
    base.update(env)
    return subprocess.run(
        [BASH, str(SCRIPT)], env=base, capture_output=True, text=True, timeout=30
    )


@pytest.fixture
def stub_bin(tmp_path):
    """A PATH directory whose pg_dump writes a small file instead of dumping."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pg_dump = bin_dir / "pg_dump"
    pg_dump.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do case "$a" in --file=*) out="${a#--file=}";; esac; done\n'
        'echo FAKEDUMP > "$out"\n'
    )
    pg_dump.chmod(0o755)
    for tool in ("find", "date", "wc", "mkdir", "mv", "rm", "basename"):
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    return bin_dir


@pytest.fixture
def valid_env(tmp_path):
    pgpass = tmp_path / "pgpass"
    pgpass.write_text("*:*:*:*:secret\n")
    pgpass.chmod(0o600)
    return {
        "FREESPACE_BACKUP_DIR": str(tmp_path / "backups"),
        "PGHOST": "localhost",
        "PGUSER": "freespace",
        "PGDATABASE": "freespace",
        "PGPASSFILE": str(pgpass),
    }


def test_script_is_executable_and_syntax_valid():
    assert os.access(SCRIPT, os.X_OK)
    assert subprocess.run([BASH, "-n", str(SCRIPT)]).returncode == 0


def test_fails_cleanly_without_required_env():
    out = run({})
    assert out.returncode != 0
    assert "ERROR:" in out.stderr and "FREESPACE_BACKUP_DIR" in out.stderr


def test_requires_an_off_host_destination(valid_env, stub_bin):
    out = run(valid_env, path=str(stub_bin))
    assert out.returncode != 0
    assert "off-host" in out.stderr


def test_refuses_pgbouncer_port(valid_env, stub_bin):
    out = run(
        {**valid_env, "PGPORT": "6432", "FREESPACE_BACKUP_ALLOW_LOCAL_ONLY": "true"}
    )
    assert out.returncode != 0 and "PgBouncer" in out.stderr


def test_rejects_bad_retention(valid_env):
    out = run({**valid_env, "FREESPACE_BACKUP_RETENTION_DAYS": "abc"})
    assert out.returncode != 0 and "RETENTION_DAYS" in out.stderr


def test_local_only_run_writes_a_dump_and_prunes_old_ones(
    valid_env, stub_bin, tmp_path
):
    backups = Path(valid_env["FREESPACE_BACKUP_DIR"])
    backups.mkdir()
    old = backups / "freespace_freespace_20200101T000000Z.dump"
    old.write_text("old")
    os.utime(old, (1_000_000_000, 1_000_000_000))
    out = run(
        {**valid_env, "FREESPACE_BACKUP_ALLOW_LOCAL_ONLY": "true"},
        path=str(stub_bin),
    )
    assert out.returncode == 0, out.stderr
    dumps = sorted(p.name for p in backups.glob("freespace_*.dump"))
    assert len(dumps) == 1 and dumps[0] != old.name
    assert not list(backups.glob("*.partial"))


def test_pg_dump_failure_exits_nonzero_and_logs(valid_env, tmp_path):
    bin_dir = tmp_path / "failbin"
    bin_dir.mkdir()
    pg_dump = bin_dir / "pg_dump"
    pg_dump.write_text("#!/bin/sh\nexit 3\n")
    pg_dump.chmod(0o755)
    for tool in ("find", "date", "wc", "mkdir", "mv", "rm", "basename"):
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    out = run(
        {**valid_env, "FREESPACE_BACKUP_ALLOW_LOCAL_ONLY": "true"}, path=str(bin_dir)
    )
    assert out.returncode != 0
    assert "ERROR:" in out.stderr
