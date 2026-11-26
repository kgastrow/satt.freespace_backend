#!/usr/bin/env python3
"""Starting the app for a workflow (adw_modules/env_setup.py): start.sh gives up when the backend is slow (several
workflows starting at once), so start_app retries and checks the frontend too; ensure_app restarts a server that
went down; stop_servers leaves everything but the worktree's servers alone. POSIX only (lsof, pgrep, bash)."""

import logging
import os
import socket
import sys
import textwrap
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adw_modules import env_setup  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="bash, lsof and pgrep")
LOG = logging.getLogger("test_app_start")

SERVE = textwrap.dedent('''
    import http.server, sys
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        def log_message(self, *a):
            pass
    http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
''')

# start.sh's shape: gives up (exit 1) until attempt FAIL_UNTIL, like the real one when the backend is slow
START = textwrap.dedent('''\
    #!/bin/bash
    n=$(( $(cat ../attempts 2>/dev/null || echo 0) + 1 )); echo $n > ../attempts
    if [ $n -lt ${FAIL_UNTIL:-1} ]; then echo "Backend did not become healthy within 120 seconds!"; exit 1; fi
    python3 ../serve.py $BP &
    [ -n "$NO_FRONTEND" ] || python3 ../serve.py $FP &
    mkdir -p app/frontend/src/types && touch app/frontend/src/types/api-generated.ts
    wait
''')


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def app(tmp_path, monkeypatch):
    (tmp_path / "serve.py").write_text(SERVE)
    wt = tmp_path / "wt"
    (wt / "scripts").mkdir(parents=True)
    (wt / "scripts" / "start.sh").write_text(START)
    bp, fp = free_port(), free_port()
    monkeypatch.setenv("BP", str(bp))
    monkeypatch.setenv("FP", str(fp))
    a = type("App", (), {"wt": str(wt), "bp": bp, "fp": fp, "log": str(tmp_path / "start.log"),
                         "attempts": lambda self: int((tmp_path / "attempts").read_text())})()
    yield a
    env_setup.stop_servers(a.wt, (bp, fp), LOG)


def test_a_start_that_gives_up_is_retried_once(app, monkeypatch):
    monkeypatch.setenv("FAIL_UNTIL", "2")
    note = env_setup.start_app(app.wt, app.bp, app.fp, LOG, app.log, timeout=30)
    assert note == f"app on :{app.bp}/:{app.fp} (start 2)" and app.attempts() == 2
    assert env_setup.app_status(app.bp, app.fp) == (True, True)


def test_an_app_that_never_starts_fails_setup_with_the_reason(app, monkeypatch):
    monkeypatch.setenv("FAIL_UNTIL", "9")
    with pytest.raises(env_setup.SetupError) as e:
        env_setup.start_app(app.wt, app.bp, app.fp, LOG, app.log, timeout=30)
    assert "start.sh stopped" in str(e.value) and "Backend did not become healthy" in str(e.value)
    assert app.attempts() == 2


def test_a_missing_frontend_is_not_reported_as_running(app, monkeypatch):
    """Friday's failure: the backend answered, nothing listened on the frontend port, and setup said 'app on'."""
    monkeypatch.setenv("NO_FRONTEND", "1")
    with pytest.raises(env_setup.SetupError, match="frontend not up"):
        env_setup.start_app(app.wt, app.bp, app.fp, LOG, app.log, timeout=4)


def test_ensure_app_restarts_a_server_that_went_down(app):
    env_setup.start_app(app.wt, app.bp, app.fp, LOG, app.log, timeout=30)
    assert env_setup.ensure_app(app.wt, app.bp, app.fp, LOG, app.log) == f"app running on :{app.bp}/:{app.fp}"
    os.system(f"kill $(lsof -nP -t -iTCP:{app.fp} -sTCP:LISTEN)")         # the frontend dies
    deadline = time.time() + 10
    while env_setup.app_status(app.bp, app.fp)[1] and time.time() < deadline:
        time.sleep(0.2)
    note = env_setup.ensure_app(app.wt, app.bp, app.fp, LOG, app.log)
    assert note.startswith("frontend was down; restarted") and app.attempts() == 2
    assert env_setup.app_status(app.bp, app.fp) == (True, True)


def test_setup_installs_playwrights_chromium_and_never_fails_on_it(tmp_path):
    """Screens failed on a machine without Playwright's Chromium: Setup installs it, and only notes a failure."""
    bin_ = tmp_path / "app" / "frontend" / "node_modules" / ".bin"
    assert env_setup.ensure_browser(str(tmp_path), LOG) == "no Playwright in the frontend"
    bin_.mkdir(parents=True)
    pw = bin_ / "playwright"
    pw.write_text('#!/bin/bash\necho "$@" >> ../../calls\n'
                  '[ -f ../../have ] || { touch ../../have; echo "Chromium 145 downloaded to /cache/chromium-1208"; }\n')
    pw.chmod(0o755)
    wt = str(tmp_path)
    assert env_setup.ensure_browser(wt, LOG) == "Playwright Chromium installed"
    assert env_setup.ensure_browser(wt, LOG) == "browser ready"                  # already there: nothing to fetch
    assert (tmp_path / "calls").read_text().split("\n")[0] == "install chromium"
    pw.write_text('#!/bin/bash\necho "Failed to download Chromium: ENOTFOUND" >&2; exit 1\n')
    assert env_setup.ensure_browser(wt, LOG).startswith("Playwright Chromium not installed: Failed to download")
