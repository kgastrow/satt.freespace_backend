#!/bin/bash

# Parse command line arguments
REGENERATE_TYPES=false
for arg in "$@"; do
    case $arg in
        --regenerate-types)
            REGENERATE_TYPES=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --regenerate-types  Regenerate TypeScript API types from backend OpenAPI schema"
            echo "  --help, -h          Show this help message"
            exit 0
            ;;
    esac
done

# Source port configuration if exists
[ -f ".ports.env" ] && source .ports.env

# Determine project root early for config.json lookup
_SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
_PROJECT_ROOT="$( dirname "$_SCRIPT_DIR" )"

# Port configuration with fallbacks (used for killing existing processes)
# Read backend port from config.json if BACKEND_PORT is not set
if [ -z "$BACKEND_PORT" ] && [ -f "$_PROJECT_ROOT/app/backend/config.json" ]; then
    if [[ "$(uname)" == "Darwin" ]]; then
        CONFIG_PORT=$(sed -n 's/.*"port"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' "$_PROJECT_ROOT/app/backend/config.json" | head -1)
    else
        CONFIG_PORT=$(grep -oP '"port"\s*:\s*\K[0-9]+' "$_PROJECT_ROOT/app/backend/config.json" | head -1)
    fi
fi
SERVER_PORT=${BACKEND_PORT:-${CONFIG_PORT:-8000}}
CLIENT_PORT=${FRONTEND_PORT:-5173}

# Temp files to capture server output for port detection
BACKEND_LOG=$(mktemp)
FRONTEND_LOG=$(mktemp)
WORKER_LOG=$(mktemp)

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting AYZER Webapp Template...${NC}"
if [ "$REGENERATE_TYPES" = true ] || [ -n "$WORKTREE_ID" ]; then
    echo -e "${BLUE}(API types will be regenerated)${NC}"
fi

# Get the script's directory (needed early for worktree detection)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

# Extract worktree identifier if running in an isolated worktree (e.g., "20261107085112-e609bd351caf"; older
# ones have 8 hex digits)
WORKTREE_ID=""
if [[ "$PROJECT_ROOT" =~ trees/([0-9]{14}-[a-f0-9]{8,12})(/|$) ]]; then
    WORKTREE_ID="${BASH_REMATCH[1]}"
    echo -e "${BLUE}Detected isolated worktree: $WORKTREE_ID${NC}"
fi

# How long to wait for each server. Several worktrees starting at once (ADW workflows) make the backend slow to
# come up, so these are generous; set them lower for quick local feedback.
BACKEND_START_TIMEOUT=${BACKEND_START_TIMEOUT:-120}
FRONTEND_START_TIMEOUT=${FRONTEND_START_TIMEOUT:-90}

# This checkout's ARQ worker(s) (its own venv's arq), never another checkout's or worktree's
ARQ_PATTERN="${PROJECT_ROOT}/app/backend/.venv/bin/arq src.workers.worker.WorkerSettings"

# Function to gracefully kill processes on a port
# Uses SIGTERM first for graceful shutdown, then SIGKILL as fallback
kill_port() {
    local port=$1
    local process_name=$2

    # Find ALL processes using the port (lsof can return multiple PIDs)
    local pids=$(lsof -ti:$port 2>/dev/null)

    if [ -n "$pids" ]; then
        echo -e "${YELLOW}Found $process_name on port $port (PIDs: $pids). Stopping gracefully...${NC}"

        # Send SIGTERM first for graceful shutdown
        echo "$pids" | xargs kill 2>/dev/null

        # Wait up to 5 seconds for graceful shutdown
        local waited=0
        while [ $waited -lt 5 ]; do
            sleep 1
            waited=$((waited + 1))
            pids=$(lsof -ti:$port 2>/dev/null)
            if [ -z "$pids" ]; then
                echo -e "${GREEN}$process_name on port $port stopped gracefully.${NC}"
                return 0
            fi
        done

        # Fallback to SIGKILL if still running
        pids=$(lsof -ti:$port 2>/dev/null)
        if [ -n "$pids" ]; then
            echo -e "${YELLOW}Graceful shutdown timed out, forcing kill...${NC}"
            echo "$pids" | xargs kill -9 2>/dev/null
            sleep 1
        fi

        echo -e "${GREEN}$process_name on port $port has been terminated.${NC}"
    fi
}

# Function to clean up processes associated with this worktree
# This catches multiprocessing children that may not be listening on ports
cleanup_worktree_processes() {
    local worktree_id="$1"

    if [ -z "$worktree_id" ]; then
        return 0
    fi

    echo -e "${YELLOW}Cleaning up processes for worktree $worktree_id...${NC}"

    # Find and gracefully stop Python processes from this worktree's venv
    local python_pids=$(pgrep -f "trees/${worktree_id}/app/backend/.venv" 2>/dev/null)
    if [ -n "$python_pids" ]; then
        echo -e "${YELLOW}  Stopping Python processes: $python_pids${NC}"
        echo "$python_pids" | xargs kill 2>/dev/null
        sleep 2

        # Force kill any remaining
        python_pids=$(pgrep -f "trees/${worktree_id}/app/backend/.venv" 2>/dev/null)
        if [ -n "$python_pids" ]; then
            echo -e "${YELLOW}  Force killing remaining Python processes: $python_pids${NC}"
            echo "$python_pids" | xargs kill -9 2>/dev/null
        fi
    fi

    # Find and stop Node processes from this worktree
    local node_pids=$(pgrep -f "trees/${worktree_id}/app/frontend/node_modules" 2>/dev/null)
    if [ -n "$node_pids" ]; then
        echo -e "${YELLOW}  Stopping Node processes: $node_pids${NC}"
        echo "$node_pids" | xargs kill 2>/dev/null
        sleep 1

        # Force kill any remaining
        node_pids=$(pgrep -f "trees/${worktree_id}/app/frontend/node_modules" 2>/dev/null)
        if [ -n "$node_pids" ]; then
            echo "$node_pids" | xargs kill -9 2>/dev/null
        fi
    fi
}

# First clean up any orphaned processes from this worktree (if in isolated mode)
if [ -n "$WORKTREE_ID" ]; then
    cleanup_worktree_processes "$WORKTREE_ID"
fi

# Kill any existing processes on our ports
kill_port $SERVER_PORT "backend server"
kill_port $CLIENT_PORT "frontend server"

# Verify ports are free before proceeding
for port in $SERVER_PORT $CLIENT_PORT; do
    if lsof -ti:$port >/dev/null 2>&1; then
        echo -e "${RED}ERROR: Port $port is still in use after cleanup!${NC}"
        lsof -i:$port
        exit 1
    fi
done

# Check if config.json exists in backend directory
if [ ! -f "$PROJECT_ROOT/app/backend/config.json" ]; then
    echo -e "${RED}Warning: No config.json file found in app/backend/.${NC}"
    echo "Please:"
    echo "  1. cd app/backend"
    echo "  2. cp config.json.example config.json"
    echo "  3. Edit config.json as required"
    exit 1
fi

# Function to cleanup on exit
cleanup() {
    echo -e "\n${BLUE}Shutting down services...${NC}"

    # First, gracefully stop ARQ worker and its children
    # ARQ spawns multiprocessing children that need explicit cleanup
    if [ -n "$WORKER_PID" ] && kill -0 $WORKER_PID 2>/dev/null; then
        echo -e "${YELLOW}Stopping ARQ worker and children...${NC}"
        # Try killing the process group first (works when setsid was used),
        # fall back to killing the process directly
        kill -- -$WORKER_PID 2>/dev/null || kill $WORKER_PID 2>/dev/null
        sleep 1
    fi

    # Also kill this checkout's remaining arq worker processes (catches cases where PID tracking was lost)
    local arq_pids=$(pgrep -f "$ARQ_PATTERN" 2>/dev/null)
    if [ -n "$arq_pids" ]; then
        echo -e "${YELLOW}Stopping remaining ARQ processes: $arq_pids${NC}"
        echo "$arq_pids" | xargs kill 2>/dev/null
        sleep 1
        arq_pids=$(pgrep -f "$ARQ_PATTERN" 2>/dev/null)
        if [ -n "$arq_pids" ]; then
            echo "$arq_pids" | xargs kill -9 2>/dev/null
        fi
    fi

    # Clean up any remaining multiprocessing children from this worktree
    if [ -n "$WORKTREE_ID" ]; then
        local arq_children=$(pgrep -f "trees/${WORKTREE_ID}/app/backend/.venv.*multiprocessing" 2>/dev/null)
        if [ -n "$arq_children" ]; then
            echo -e "${YELLOW}Cleaning up ARQ multiprocessing children: $arq_children${NC}"
            echo "$arq_children" | xargs kill 2>/dev/null
            sleep 1
            # Force kill any remaining
            arq_children=$(pgrep -f "trees/${WORKTREE_ID}/app/backend/.venv.*multiprocessing" 2>/dev/null)
            if [ -n "$arq_children" ]; then
                echo "$arq_children" | xargs kill -9 2>/dev/null
            fi
        fi
    fi

    # Kill all remaining child processes
    jobs -p | xargs -r kill 2>/dev/null

    # The servers themselves: killing a `python main.py | tee` job can leave the server (and its workers) running
    if [ "$STARTED" = true ]; then
        kill_port $SERVER_PORT "backend server"
        kill_port $CLIENT_PORT "frontend server"
    fi

    # Wait for processes to terminate
    wait

    # Clean up temp files
    rm -f "$BACKEND_LOG" "$FRONTEND_LOG" "$WORKER_LOG"

    echo -e "${GREEN}Services stopped successfully.${NC}"
    exit 0
}

# Trap EXIT, INT, and TERM signals
STARTED=true          # from here on the ports are ours: cleanup stops what listens on them
trap cleanup EXIT INT TERM

# Start backend
echo -e "${GREEN}Starting backend server...${NC}"
cd "$PROJECT_ROOT/app/backend"
# Local dev runs over plain HTTP, so the browser drops Secure-flagged cookies.
# Override here only — config.json keeps secure: true for prod.
export COOKIE_SECURE=false
source .venv/bin/activate && python main.py 2>&1 | tee "$BACKEND_LOG" &
BACKEND_PID=$!

# Wait for backend to be healthy (poll every 0.5s, up to BACKEND_START_TIMEOUT seconds)
echo "Waiting for backend to start (up to ${BACKEND_START_TIMEOUT}s)..."
BACKEND_READY=false
for i in $(seq 1 $((BACKEND_START_TIMEOUT * 2))); do
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${RED}Backend failed to start!${NC}"
        exit 1
    fi
    if curl -s --fail "http://localhost:${SERVER_PORT}/health" > /dev/null 2>&1; then
        BACKEND_READY=true
        break
    fi
    sleep 0.5
done

if [ "$BACKEND_READY" = false ]; then
    echo -e "${RED}Backend did not become healthy within ${BACKEND_START_TIMEOUT} seconds!${NC}"
    exit 1
fi

# Regenerate API types if requested or running in a worktree.
# Types are gitignored, so worktrees won't have them. APIs may also change
# as agents work, so always regenerate on every backend start in worktrees.
if [ "$REGENERATE_TYPES" = true ] || [ -n "$WORKTREE_ID" ]; then
    echo -e "${GREEN}Regenerating API types from backend...${NC}"
    cd "$PROJECT_ROOT/app/frontend"
    if npm run generate:types; then
        echo -e "${GREEN}API types regenerated successfully.${NC}"
    else
        echo -e "${YELLOW}Warning: Failed to regenerate API types. Continuing anyway...${NC}"
    fi
fi

# Start ARQ worker for background jobs in its own process group
# setsid ensures all child processes (multiprocessing workers) are in the same group,
# but it's not available on all systems (e.g., macOS without util-linux).
# Fall back to plain background process if setsid is not found.
echo -e "${GREEN}Starting ARQ background worker...${NC}"
cd "$PROJECT_ROOT/app/backend"
if command -v setsid &> /dev/null; then
    setsid bash -c 'source .venv/bin/activate && exec arq src.workers.worker.WorkerSettings' > "$WORKER_LOG" 2>&1 &
else
    bash -c 'source .venv/bin/activate && exec arq src.workers.worker.WorkerSettings' > "$WORKER_LOG" 2>&1 &
fi
WORKER_PID=$!

# Brief wait for worker to initialize
sleep 2

# Check if worker is running using both PID check and process search
# setsid on macOS may cause the original PID to exit while the worker runs in a new session
WORKER_RUNNING=false
if kill -0 $WORKER_PID 2>/dev/null; then
    WORKER_RUNNING=true
else
    # Fallback: check if this checkout's arq worker process exists (setsid may have re-parented it)
    if pgrep -f "${PROJECT_ROOT}/app/backend/.venv/bin/arq src.workers.worker.WorkerSettings" > /dev/null 2>&1; then
        WORKER_PID=$(pgrep -f "${PROJECT_ROOT}/app/backend/.venv/bin/arq src.workers.worker.WorkerSettings" | head -1)
        WORKER_RUNNING=true
    fi
fi

if [ "$WORKER_RUNNING" = true ]; then
    echo -e "${GREEN}ARQ worker started (PID: $WORKER_PID)${NC}"
else
    echo -e "${YELLOW}Warning: ARQ worker failed to start. Background jobs will not be processed.${NC}"
    if [ -s "$WORKER_LOG" ]; then
        echo -e "${YELLOW}Worker output:${NC}"
        cat "$WORKER_LOG"
    fi
fi

# Start frontend
echo -e "${GREEN}Starting frontend server...${NC}"
cd "$PROJECT_ROOT/app/frontend"
# Relative URL routes requests through the Vite dev proxy so the browser sees
# them as same-origin (avoids cross-site cookie issues at 127.0.0.1 vs localhost).
# Vite reads BACKEND_PORT to point the proxy at the right backend port.
export VITE_API_URL="/api/v1"
export BACKEND_PORT="${SERVER_PORT}"
npm run dev 2>&1 | tee "$FRONTEND_LOG" &
FRONTEND_PID=$!

# Wait for the frontend to listen on its port (up to FRONTEND_START_TIMEOUT seconds)
echo "Waiting for frontend to start (up to ${FRONTEND_START_TIMEOUT}s)..."
FRONTEND_READY=false
for i in $(seq 1 $((FRONTEND_START_TIMEOUT * 2))); do
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        break
    fi
    if lsof -nP -iTCP:$CLIENT_PORT -sTCP:LISTEN >/dev/null 2>&1; then
        FRONTEND_READY=true
        break
    fi
    sleep 0.5
done

if [ "$FRONTEND_READY" = false ]; then
    echo -e "${RED}Frontend failed to start: nothing listens on port $CLIENT_PORT after ${FRONTEND_START_TIMEOUT}s!${NC}"
    tail -20 "$FRONTEND_LOG"
    exit 1
fi

# Detect actual backend port from Uvicorn output
if [[ "$(uname)" == "Darwin" ]]; then
    ACTUAL_BACKEND_PORT=$(sed -n 's/.*Uvicorn running on http:\/\/[^:]*:\([0-9]*\).*/\1/p' "$BACKEND_LOG" 2>/dev/null | head -1)
else
    ACTUAL_BACKEND_PORT=$(grep -oP 'Uvicorn running on http://[^:]+:\K[0-9]+' "$BACKEND_LOG" 2>/dev/null | head -1)
fi
if [ -z "$ACTUAL_BACKEND_PORT" ]; then
    ACTUAL_BACKEND_PORT=$SERVER_PORT
fi

# Detect actual frontend port from Vite output
if [[ "$(uname)" == "Darwin" ]]; then
    ACTUAL_FRONTEND_PORT=$(sed -n 's/.*Local:[[:space:]]*http:\/\/localhost:\([0-9]*\).*/\1/p' "$FRONTEND_LOG" 2>/dev/null | head -1)
else
    ACTUAL_FRONTEND_PORT=$(grep -oP 'Local:\s+http://localhost:\K[0-9]+' "$FRONTEND_LOG" 2>/dev/null | head -1)
fi
if [ -z "$ACTUAL_FRONTEND_PORT" ]; then
    ACTUAL_FRONTEND_PORT=$CLIENT_PORT
fi

echo -e "${GREEN}✓ Services started successfully!${NC}"
echo -e "${BLUE}Frontend: http://localhost:$ACTUAL_FRONTEND_PORT${NC}"
echo -e "${BLUE}Backend:  http://localhost:$ACTUAL_BACKEND_PORT${NC}"
echo -e "${BLUE}API Docs: http://localhost:$ACTUAL_BACKEND_PORT/docs${NC}"
echo -e "${BLUE}Worker:   ARQ background job processor${NC}"
echo ""
echo "Press Ctrl+C to stop all services..."

# Wait for user to press Ctrl+C
wait