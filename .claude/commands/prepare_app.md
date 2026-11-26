# Prepare Application

Setup the application for the review or test.

## Variables

PORT: If `.ports.env` exists, read FRONTEND_PORT from it, otherwise default to 5173
BACKEND_PORT: If `.ports.env` exists, read BACKEND_PORT from it, otherwise default to 8000

## Setup

1. Check if `.ports.env` exists:
   - If it exists, source it and use `FRONTEND_PORT` for the PORT variable and `BACKEND_PORT`
   - If not, use default PORT: 5173, BACKEND_PORT: 8000

2. **Pre-startup cleanup** (CRITICAL - prevents "Address already in use" errors):
   ```bash
   # Kill any processes on the ports we need (use /usr/sbin/lsof for macOS compatibility)
   /usr/sbin/lsof -ti :$BACKEND_PORT | xargs kill -9 2>/dev/null || true
   /usr/sbin/lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
   sleep 2
   ```

3. Start the application:
   - Start using the start script with logs captured:
     ```bash
     nohup sh ./scripts/start.sh > /tmp/app_start_$$.log 2>&1 &
     ```
   - The start.sh script will automatically use ports from `.ports.env` if it exists
   - Use `./scripts/stop_apps.sh` to stop the server and client

4. **Verify the application is running** (wait up to 30 seconds):
   ```bash
   # Wait for startup and check if services are listening
   sleep 15
   curl -s --max-time 5 http://localhost:$BACKEND_PORT/health || curl -s --max-time 5 http://localhost:$BACKEND_PORT/docs
   curl -s --max-time 5 http://localhost:$PORT | head -5
   ```
   - If curl returns content, the app is running
   - If empty/timeout, check logs: `cat /tmp/app_start_*.log | tail -50`

## CRITICAL: Never Manually Start Services

**NEVER attempt to start the backend or frontend manually.** This means:
- ❌ Do NOT run `uvicorn` directly
- ❌ Do NOT run `npm run dev` directly
- ❌ Do NOT try to "debug" by starting services individually
- ❌ Do NOT improvise alternative startup commands

**ALWAYS use `scripts/start.sh`** - it handles:
- Correct working directories
- Proper environment activation
- Correct module paths (e.g., `main:app` not `src.main:app`)
- Port configuration from `.ports.env`

If start.sh fails, **report the failure** and proceed without the running app. Do not attempt workarounds.

## Error Handling: "Address already in use"

If you see "Address already in use" or similar port conflict errors:

1. **Force kill processes on the specific port** (port-based only - safe for parallel worktrees):
   ```bash
   # Find and kill whatever is using the port (by port number only)
   /usr/sbin/lsof -ti :$BACKEND_PORT | xargs kill -9 2>/dev/null || true
   /usr/sbin/lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
   sleep 3
   ```

   **WARNING**: Do NOT use `pkill -f` with process names - this would kill processes from other worktrees!

2. **Retry startup ONCE** using `scripts/start.sh` after killing processes

3. **If still failing after retry**: Report failure and continue without the running app
   - Do NOT keep retrying indefinitely
   - Do NOT try changing ports (this causes state inconsistency)
   - Do NOT try manual startup commands
   - Return/report that app startup failed so the caller can handle gracefully

## Diagnosing Startup Failures

If the app doesn't start, check:
1. **Startup logs**: `cat /tmp/app_start_*.log | tail -100`
2. **Backend logs**: `cat app/backend/app.log | tail -50`
3. **Process status**: `ps aux | grep -E "(uvicorn|vite|node)" | grep -v grep`

Report any errors found, but do NOT attempt to fix them by manually running commands.

Note: Read `scripts/` and `README.md` for more information on how to start, stop and reset the server and client.

