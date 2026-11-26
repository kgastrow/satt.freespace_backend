"""Scripted worktree environment setup: what /install_worktree and /prepare_app ask an LLM to do, done by code.

Used by adw_orchestrated_sdlc_iso.py. Each function logs, returns a short note for the step record, and raises
SetupError when the worktree can't be used.

- install_dependencies(): app/backend/.venv and app/frontend/node_modules, cloned from the main checkout when it
  has them (APFS clones with `cp -c` on macOS, so it is fast and takes no extra space), then synced with
  `uv pip install` / `npm ci` as needed. A cloned venv is relocated (its scripts name the venv's absolute path)
  and checked; if anything is off it falls back to a fresh install.
- configure_worktree(): .env, app/backend/.env and app/backend/config.json for this worktree's ports, isolated
  database and Redis database (the same settings /install_worktree describes), and app/frontend/.env
  (copy_frontend_env: the main checkout's, with the worktree's own backend URLs).
- ensure_browser(): the Chromium the frontend's Playwright needs for screenshots, downloaded once per Playwright
  version into the machine's shared cache.
- run_migrations(), start_app(), ensure_app() (restarts the app when a server is down), stop_app().
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from typing import Optional

from adw_modules.database_ops import update_worktree_database_config


START_TIMEOUT = int(os.getenv("ADW_APP_START_TIMEOUT", "300") or 300)   # per start of the app, in seconds


class SetupError(RuntimeError):
    """The worktree environment couldn't be set up."""


def project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _sha(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def _env() -> dict:
    env = dict(os.environ)
    if sys.platform == "darwin":                # pg_config for psycopg2, as /install_worktree does
        env["PATH"] = "/opt/homebrew/opt/postgresql@15/bin:" + env.get("PATH", "")
    env.pop("VIRTUAL_ENV", None)                # the workflow's own uv environment must not leak into the app's
    return env


def _run(cmd, cwd: str, logger: logging.Logger, timeout: int = 900) -> subprocess.CompletedProcess:
    logger.info(f"$ {' '.join(cmd)}  (in {cwd})")
    proc = subprocess.run(cmd, cwd=cwd, env=_env(), capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        logger.warning(f"exit {proc.returncode}: {(proc.stderr or proc.stdout)[-1500:]}")
    return proc


def clone_tree(src: str, dst: str, logger: logging.Logger) -> bool:
    """Copy a directory tree, symlinks kept. On macOS an APFS clone (`cp -c -R`): near instant, no extra space."""
    if os.path.lexists(dst):
        shutil.rmtree(dst, ignore_errors=True)
    if sys.platform == "darwin":
        proc = subprocess.run(["cp", "-c", "-R", src, dst], capture_output=True, text=True, timeout=900)
        if proc.returncode == 0:
            return True
        logger.warning(f"cp -c failed ({proc.stderr.strip()[:300]}); copying normally")
        shutil.rmtree(dst, ignore_errors=True)
    try:
        shutil.copytree(src, dst, symlinks=True)
        return True
    except (OSError, shutil.Error) as e:
        logger.warning(f"Copying {src} failed: {e}")
        shutil.rmtree(dst, ignore_errors=True)
        return False


def relocate_venv(venv: str, old: str, logger: logging.Logger) -> int:
    """A venv's scripts (shebangs, activate) and .pth files name its absolute path: point them at `venv`.
    Returns how many files were rewritten."""
    old_b, new_b = os.path.abspath(old).encode(), os.path.abspath(venv).encode()
    if old_b == new_b:
        return 0
    targets = []
    bindir = os.path.join(venv, "bin" if os.name != "nt" else "Scripts")
    if os.path.isdir(bindir):
        targets += [os.path.join(bindir, n) for n in os.listdir(bindir)]
    for root, _dirs, files in os.walk(os.path.join(venv, "lib")):
        targets += [os.path.join(root, n) for n in files if n.endswith((".pth", "direct_url.json"))]
        if root.count(os.sep) - venv.count(os.sep) > 3:     # lib/pythonX.Y/site-packages is deep enough
            _dirs[:] = []
    changed = 0
    for path in targets:
        try:
            if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > 2_000_000:
                continue
            with open(path, "rb") as f:
                data = f.read()
            if old_b in data:
                with open(path, "wb") as f:
                    f.write(data.replace(old_b, new_b))
                changed += 1
        except OSError as e:
            logger.debug(f"relocate {path}: {e}")
    return changed


def _venv_ok(venv: str, logger: logging.Logger) -> bool:
    py = os.path.join(venv, "bin", "python")
    try:
        out = subprocess.run([py, "-c", "import sys; print(sys.prefix)"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning(f"The cloned venv doesn't run: {e}")
        return False
    ok = out.returncode == 0 and os.path.realpath(out.stdout.strip()) == os.path.realpath(venv)
    if not ok:
        logger.warning(f"The cloned venv points elsewhere: {out.stdout.strip() or out.stderr.strip()[:200]}")
    return ok


def install_backend(worktree: str, logger: logging.Logger, main_root: Optional[str] = None) -> str:
    main_root = main_root or project_root()
    backend = os.path.join(worktree, "app", "backend")
    venv, main_venv = os.path.join(backend, ".venv"), os.path.join(main_root, "app", "backend", ".venv")
    how = "fresh venv"
    if os.path.isdir(venv) and _venv_ok(venv, logger):            # a rerun: keep it, just sync below
        how = "existing venv"
    elif os.path.isdir(main_venv) and os.path.realpath(main_venv) != os.path.realpath(venv):
        if clone_tree(main_venv, venv, logger):
            relocate_venv(venv, main_venv, logger)
            if _venv_ok(venv, logger):
                same = _sha(os.path.join(main_root, "app", "backend", "requirements.txt")) == \
                    _sha(os.path.join(backend, "requirements.txt"))
                how = "venv cloned from main checkout" + ("" if same else " (requirements changed: synced)")
            else:
                shutil.rmtree(venv, ignore_errors=True)
    if not os.path.isdir(venv):
        proc = _run(["uv", "venv", "--python", "3.12", ".venv"], backend, logger, timeout=300)
        if proc.returncode != 0:
            raise SetupError(f"uv venv failed: {proc.stderr.strip()[-300:]}")
    # Always sync: a no-op in seconds when the clone already matches requirements.txt
    proc = _run(["uv", "pip", "install", "--python", os.path.join(venv, "bin", "python"), "-r", "requirements.txt"],
                backend, logger, timeout=1200)
    if proc.returncode != 0:
        raise SetupError(f"Backend dependencies failed to install: {proc.stderr.strip()[-300:]}")
    return how


def install_frontend(worktree: str, logger: logging.Logger, main_root: Optional[str] = None) -> str:
    main_root = main_root or project_root()
    frontend = os.path.join(worktree, "app", "frontend")
    mods, main_mods = os.path.join(frontend, "node_modules"), os.path.join(main_root, "app", "frontend", "node_modules")
    lock = _sha(os.path.join(frontend, "package-lock.json"))
    lock_same = lock is not None and lock == _sha(os.path.join(main_root, "app", "frontend", "package-lock.json"))
    if os.path.isdir(os.path.join(mods, ".bin")) and lock_same:     # a rerun: already installed
        return "existing node_modules"
    if lock_same and os.path.isdir(main_mods) and os.path.realpath(main_mods) != os.path.realpath(mods):
        if clone_tree(main_mods, mods, logger):
            return "node_modules cloned from main checkout"
    proc = _run(["npm", "ci", "--no-audit", "--no-fund"], frontend, logger, timeout=1800)
    if proc.returncode != 0:
        proc = _run(["npm", "install", "--no-audit", "--no-fund"], frontend, logger, timeout=1800)
        if proc.returncode != 0:
            raise SetupError(f"Frontend dependencies failed to install: {proc.stderr.strip()[-300:]}")
    return "npm ci" + ("" if lock_same else " (package-lock.json differs from the main checkout)")


def install_dependencies(worktree: str, logger: logging.Logger, main_root: Optional[str] = None) -> str:
    """Backend and frontend dependencies; returns a note like "venv cloned …; node_modules cloned …"."""
    return f"{install_backend(worktree, logger, main_root)}; {install_frontend(worktree, logger, main_root)}"


def ensure_browser(worktree: str, logger: logging.Logger) -> str:
    """Playwright's Chromium for the screenshots. Never fails the setup: a note says what's missing."""
    frontend = os.path.join(worktree, "app", "frontend")
    bin_ = os.path.join(frontend, "node_modules", ".bin", "playwright")
    if not os.path.exists(bin_):
        return "no Playwright in the frontend"
    try:
        proc = _run([bin_, "install", "chromium"], frontend, logger, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Playwright Chromium not installed ({e})"
    if proc.returncode != 0:
        return f"Playwright Chromium not installed: {(proc.stderr or proc.stdout).strip()[-200:]}"
    return "Playwright Chromium installed" if "downloaded to" in (proc.stdout + proc.stderr) else "browser ready"


def _append_ports(path: str, ports_env: str) -> None:
    existing = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = f.read()
    lines = [ln for ln in existing.splitlines()
             if not ln.startswith(("BACKEND_PORT=", "FRONTEND_PORT=", "VITE_API_URL=", "VITE_BACKEND_URL="))]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines + ports_env.strip().splitlines()) + "\n")


FRONTEND_URL_KEYS = ("VITE_API_URL=", "VITE_BACKEND_URL=", "VITE_WS_URL=")


def copy_frontend_env(worktree: str, main_root: str, ports_env: str = "") -> bool:
    """app/frontend/.env from the main checkout (it's gitignored, so a worktree has none): the build-time settings
    the frontend and its tests read, e.g. VITE_ORG_SLUG. Its backend URLs point at the main checkout's backend,
    so they're dropped (the worktree's own come from ports_env). False when the main checkout has none."""
    src = os.path.join(main_root, "app", "frontend", ".env")
    dst = os.path.join(worktree, "app", "frontend", ".env")
    if not os.path.exists(src) or os.path.exists(dst) or not os.path.isdir(os.path.dirname(dst)):
        return os.path.exists(dst)
    with open(src, encoding="utf-8") as f:
        kept = [ln for ln in f.read().splitlines() if not ln.strip().startswith(FRONTEND_URL_KEYS)]
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(kept + [ln for ln in ports_env.strip().splitlines() if ln.startswith("VITE_")]) + "\n")
    return True


def configure_worktree(worktree: str, adw_id: str, backend_port: int, frontend_port: int, db_name: str,
                       logger: logging.Logger, main_root: Optional[str] = None) -> None:
    """Ports, isolated database and Redis database, secrets: .ports.env, .env files and config.json."""
    main_root = main_root or project_root()
    ports_env = (f"BACKEND_PORT={backend_port}\nFRONTEND_PORT={frontend_port}\n"
                 f"VITE_API_URL=http://localhost:{backend_port}/api/v1\nVITE_BACKEND_URL=http://localhost:{backend_port}\n")
    with open(os.path.join(worktree, ".ports.env"), "w", encoding="utf-8") as f:
        f.write(ports_env)
    for rel in (".env", os.path.join("app", "backend", ".env")):
        src, dst = os.path.join(main_root, rel), os.path.join(worktree, rel)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy(src, dst)
        if os.path.exists(dst) or rel == ".env":
            _append_ports(dst, ports_env)
    copy_frontend_env(worktree, main_root, ports_env)
    config = os.path.join(worktree, "app", "backend", "config.json")
    if not os.path.exists(config):
        for src in (os.path.join(main_root, "app", "backend", "config.json"),
                    os.path.join(worktree, "app", "backend", "config.json.example")):
            if os.path.exists(src):
                shutil.copy(src, config)
                break
        else:
            raise SetupError("No app/backend/config.json in the main checkout and no config.json.example")
    with open(config, encoding="utf-8") as f:
        data = json.load(f)
    data["debug"] = True                                      # uvicorn reloads on file changes
    data["port"] = backend_port
    with open(config, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    if not update_worktree_database_config(worktree, db_name, logger, adw_id=adw_id, frontend_port=frontend_port):
        raise SetupError("Couldn't update app/backend/config.json")
    os.makedirs(os.path.join(worktree, "playwright-output"), exist_ok=True)


def run_migrations(worktree: str, logger: logging.Logger) -> str:
    backend = os.path.join(worktree, "app", "backend")
    proc = _run([os.path.join(backend, ".venv", "bin", "alembic"), "upgrade", "head"], backend, logger, timeout=600)
    if proc.returncode != 0:
        raise SetupError(f"Migrations failed: {(proc.stderr or proc.stdout).strip()[-300:]}")
    return "migrations applied"


def _get(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status < 500
    except Exception:  # noqa: BLE001 - not up yet
        return False


def _listening(port: int) -> bool:
    """Something accepts connections on localhost:port (IPv4 or IPv6: Vite may bind either)."""
    import socket
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            continue
    return False


def app_status(backend_port: int, frontend_port: int) -> tuple[bool, bool]:
    """(backend answers, frontend listens)."""
    backend = _get(f"http://localhost:{backend_port}/health") or _get(f"http://localhost:{backend_port}/docs")
    return backend, _listening(frontend_port)


def _log_tail(log_path: str, lines: int = 15) -> str:
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            text = [ln.rstrip() for ln in f.read().splitlines()[-400:] if ln.strip()]
    except OSError:
        return ""
    # start.sh's own messages first (the reason it stopped), then the last lines
    own = [ln for ln in text if not ln.startswith(("INFO", "DEBUG")) and " INFO: " not in ln][-lines:]
    return "\n".join(own or text[-lines:])


def _pgrep(pattern: str) -> set:
    try:
        out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {int(x) for x in out.split() if x.isdigit()}


def _ancestors() -> set:
    pids, pid = set(), os.getpid()
    while pid > 1:
        pids.add(pid)
        try:
            out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
            pid = int(out.stdout.strip() or 0)
        except (OSError, ValueError, subprocess.SubprocessError):
            break
    return pids


def stop_servers(worktree: str, ports: tuple, logger: logging.Logger) -> None:
    """Stop this worktree's dev servers only: its start.sh, what listens on its ports, its ARQ worker and the
    servers' multiprocessing children. Unlike stop_app it leaves the agents working in the worktree (and this
    process) alone, so it is safe while a workflow runs."""
    import signal
    from adw_modules.worktree_ops import _pids_with_cwd_in
    root = os.path.realpath(worktree)
    keep = _ancestors()

    def kill(pids: set, what: str) -> None:
        pids = pids - keep
        if not pids:
            return
        logger.info(f"Stopping {what}: {sorted(pids)}")
        for sig, wait in ((signal.SIGTERM, 8), (signal.SIGKILL, 1)):
            for pid in pids:
                try:
                    os.kill(pid, sig)
                except OSError:
                    pass
            end = time.time() + wait
            while pids and time.time() < end:
                time.sleep(0.5)
                pids = {p for p in pids if _alive(p)}
            if not pids:
                return

    # start.sh first: its exit trap stops what it started, and it must not do that after the next start
    kill(_pgrep(r"^(/bin/)?(ba)?sh (\./)?scripts/start\.sh") & _pids_with_cwd_in(root, logger), "start.sh")
    servers = set()
    for port in ports:
        try:
            out = subprocess.run(["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True,
                                 text=True, timeout=10).stdout
            servers |= {int(x) for x in out.split() if x.isdigit()}
        except (OSError, subprocess.SubprocessError):
            pass
    servers |= _pgrep(f"{root}/app/backend/.venv/bin/arq ")
    servers |= _pgrep(f"{root}/app/backend/.venv/bin/python.* -c from multiprocessing")
    servers |= _pgrep(f"{root}/app/frontend/node_modules/.bin/vite")
    kill(servers, "the dev servers")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


def start_app(worktree: str, backend_port: int, frontend_port: int, logger: logging.Logger, log_path: str,
              timeout: int = START_TIMEOUT, attempts: int = 2) -> str:
    """Start the app with scripts/start.sh (it also regenerates the API types in a worktree) and wait until the
    backend answers, the frontend listens and api-generated.ts exists. start.sh gives up when a server doesn't come
    up in time (several worktrees starting at once make that slow); then the app is stopped and started once more.
    Returns a note; raises SetupError, with the end of the start log, when it never comes up."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    types = os.path.join(worktree, "app", "frontend", "src", "types", "api-generated.ts")
    problem = ""
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            logger.warning(f"The app didn't come up ({problem}); starting it again")
            stop_servers(worktree, (backend_port, frontend_port), logger)
        with open(log_path, "a") as log:
            log.write(f"\n==== start {attempt} ====\n")
            log.flush()
            proc = subprocess.Popen(["bash", "./scripts/start.sh"], cwd=worktree, env=_env(), stdout=log,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        deadline = time.time() + timeout
        backend_up = frontend_up = False
        while time.time() < deadline:
            backend_up, frontend_up = app_status(backend_port, frontend_port)
            if backend_up and frontend_up and os.path.exists(types):
                return f"app on :{backend_port}/:{frontend_port}" + (f" (start {attempt})" if attempt > 1 else "")
            if proc.poll() is not None:                 # start.sh gave up (it stops what it started)
                break
            time.sleep(2)
        if backend_up and frontend_up and proc.poll() is None:
            break                                       # running, only the API types are missing
        problem = ("start.sh stopped: " if proc.poll() is not None else f"not up after {timeout}s: ") + \
            ", ".join(n for n, up in (("backend", backend_up), ("frontend", frontend_up)) if not up) + " not up"
    else:
        stop_servers(worktree, (backend_port, frontend_port), logger)
        tail = _log_tail(log_path)
        raise SetupError(f"The app didn't start ({problem}); see {log_path}" + (f":\n{tail}" if tail else ""))
    proc = _run(["npm", "run", "generate:types"], os.path.join(worktree, "app", "frontend"), logger, timeout=120)
    if proc.returncode != 0:
        main_types = os.path.join(project_root(), "app", "frontend", "src", "types", "api-generated.ts")
        if os.path.exists(main_types):
            shutil.copy(main_types, types)
            return f"app on :{backend_port}/:{frontend_port}; API types copied from main checkout"
        raise SetupError("Couldn't generate the frontend API types")
    return f"app on :{backend_port}/:{frontend_port}"


def ensure_app(worktree: str, backend_port: int, frontend_port: int, logger: logging.Logger, log_path: str) -> str:
    """The app up for the screenshots and the review: a no-op when both servers answer, else restarted (by
    script: agents never start servers themselves). Returns a note; raises SetupError when it can't be started."""
    backend_up, frontend_up = app_status(backend_port, frontend_port)
    if backend_up and frontend_up:
        return f"app running on :{backend_port}/:{frontend_port}"
    down = ", ".join(n for n, up in (("backend", backend_up), ("frontend", frontend_up)) if not up)
    logger.warning(f"The app isn't fully running ({down} down): restarting it")
    stop_servers(worktree, (backend_port, frontend_port), logger)
    return f"{down} was down; restarted: " + start_app(worktree, backend_port, frontend_port, logger, log_path)


def stop_app(adw_id: str, logger: logging.Logger) -> None:
    """Stop this worktree's dev servers (by worktree path, so other ADWs' servers are left alone)."""
    try:
        from adw_modules.worktree_ops import _kill_worktree_processes
        _kill_worktree_processes(adw_id, logger)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Stopping the app failed: {e}")
