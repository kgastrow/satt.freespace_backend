"""What workflows inherit (ADW_PASS_ENV), and stopping a worktree's processes by their working directory."""

import logging
import os
import subprocess
import sys
import time

import pytest

from adw_modules import utils, worktree_ops


def test_pass_env_adds_the_named_variables(monkeypatch):
    monkeypatch.setenv("APP_FILE_KEY", "k1:abc")
    monkeypatch.setenv("APP_OTHER", "x")
    monkeypatch.setenv("APP_UNNAMED", "y")
    monkeypatch.setenv("ADW_PASS_ENV", "APP_FILE_KEY, APP_OTHER APP_MISSING")
    monkeypatch.delenv("APP_MISSING", raising=False)
    env = utils.get_safe_subprocess_env()
    assert env["APP_FILE_KEY"] == "k1:abc" and env["APP_OTHER"] == "x"
    assert "APP_UNNAMED" not in env and "APP_MISSING" not in env
    assert env["ADW_PASS_ENV"] == "APP_FILE_KEY, APP_OTHER APP_MISSING"


def test_without_pass_env_nothing_extra(monkeypatch):
    monkeypatch.delenv("ADW_PASS_ENV", raising=False)
    monkeypatch.setenv("APP_FILE_KEY", "k1:abc")
    env = utils.get_safe_subprocess_env()
    assert "APP_FILE_KEY" not in env and "ADW_PASS_ENV" not in env


def test_pass_env_cannot_replace_the_listed_values(monkeypatch):
    monkeypatch.setenv("ADW_PASS_ENV", "PYTHONUNBUFFERED")
    monkeypatch.setenv("PYTHONUNBUFFERED", "0")
    assert utils.get_safe_subprocess_env()["PYTHONUNBUFFERED"] == "1"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX processes")
def test_a_process_whose_only_link_to_the_worktree_is_its_cwd_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(worktree_ops, "_get_project_root", lambda: str(tmp_path))
    backend = tmp_path / "trees" / "abc12345" / "app" / "backend"
    backend.mkdir(parents=True)
    other = tmp_path / "trees" / "abc123456" / "app"          # a sibling worktree whose name starts the same
    other.mkdir(parents=True)
    # like `python main.py`: nothing on the command line names the worktree
    mine = subprocess.Popen(["sleep", "300"], cwd=backend)
    theirs = subprocess.Popen(["sleep", "300"], cwd=other)
    try:
        time.sleep(0.2)
        found = worktree_ops._pids_with_cwd_in(str(tmp_path / "trees" / "abc12345"), logging.getLogger("t"))
        assert mine.pid in found and theirs.pid not in found and os.getpid() not in found
        worktree_ops._kill_worktree_processes("abc12345", logging.getLogger("t"))
        assert mine.wait(timeout=10) != 0
        assert theirs.poll() is None
    finally:
        for p in (mine, theirs):
            if p.poll() is None:
                p.kill()
                p.wait()


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl")
def test_worktree_creation_waits_out_a_held_git_config_lock(tmp_path, monkeypatch):
    """Several workflows start together: one's `git worktree add` found .git/config locked by another's and the
    workflow failed at Setup. Now it tries again, and the branch doesn't write .git/config (no upstream yet)."""
    import threading

    def git(cwd, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                       capture_output=True)
    origin, root = tmp_path / "origin.git", tmp_path / "repo"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(root))
    (root / "README.md").write_text("x\n")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    git(root, "push", "-q", "origin", "HEAD:main")
    monkeypatch.setattr(worktree_ops, "_get_project_root", lambda: str(root))

    lock = root / ".git" / "config.lock"
    lock.write_text("")                                         # another git command is writing the config
    threading.Timer(0.5, lock.unlink).start()
    path, branch, err = worktree_ops.create_worktree("20261106133011-27137099917a", "feature-issue-33",
                                                     logging.getLogger("t"))
    assert err is None and branch == "feature-issue-33"
    assert (root / "trees" / "20261106133011-27137099917a" / "README.md").exists()
    config = (root / ".git" / "config").read_text()
    assert "feature-issue-33" not in config                     # no upstream until it's pushed


def test_git_lock_errors_are_recognised():
    assert worktree_ops.is_git_lock_error("error: could not lock config file .git/config: File exists")
    assert worktree_ops.is_git_lock_error("fatal: Unable to create '/r/.git/index.lock': File exists.")
    assert not worktree_ops.is_git_lock_error("fatal: invalid reference: origin/main")
