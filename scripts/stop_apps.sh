#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Stopping Freespace Webapp..."

# Function to gracefully stop processes matching a pattern
# Uses SIGTERM first, then SIGKILL as fallback
graceful_pkill() {
    local pattern="$1"
    local description="$2"

    local pids=$(pgrep -f "$pattern" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}Stopping $description (PIDs: $pids)...${NC}"

        # Send SIGTERM for graceful shutdown
        pkill -f "$pattern" 2>/dev/null

        # Wait up to 3 seconds for graceful shutdown
        sleep 3

        # Force kill any remaining
        pids=$(pgrep -f "$pattern" 2>/dev/null)
        if [ -n "$pids" ]; then
            echo -e "${YELLOW}  Force killing remaining: $pids${NC}"
            pkill -9 -f "$pattern" 2>/dev/null
        fi
    fi
}

# Function to gracefully stop processes on a port
graceful_kill_port() {
    local port=$1

    local pids=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}  Stopping processes on port $port (PIDs: $pids)...${NC}"

        # Send SIGTERM for graceful shutdown
        echo "$pids" | xargs kill 2>/dev/null

        # Wait for graceful shutdown
        sleep 2

        # Force kill any remaining
        pids=$(lsof -ti:$port 2>/dev/null)
        if [ -n "$pids" ]; then
            echo "$pids" | xargs kill -9 2>/dev/null
        fi
    fi
}

# Stop start.sh processes gracefully
graceful_pkill "start.sh" "start.sh processes"

# Stop webhook server
graceful_pkill "trigger_webhook.py" "webhook server"

# Stop processes on main ports gracefully
echo -e "${GREEN}Stopping processes on main ports (5173, 8000, 8001)...${NC}"
for port in 5173 8000 8001; do
    graceful_kill_port $port
done

# Stop processes on isolated ADW backend ports
echo -e "${GREEN}Stopping processes on isolated ADW backend ports (9100-9114)...${NC}"
for port in {9100..9114}; do
    graceful_kill_port $port
done

# Stop processes on isolated ADW frontend ports
echo -e "${GREEN}Stopping processes on isolated ADW frontend ports (9200-9214)...${NC}"
for port in {9200..9214}; do
    graceful_kill_port $port
done

# BUG-030 fix: Clean up uvicorn/vite processes with project-specific patterns
# Include project path in pattern to avoid killing processes from other projects
graceful_pkill "bitbox.webapp.template.*uvicorn" "remaining uvicorn processes"
graceful_pkill "bitbox.webapp.template.*vite" "remaining vite processes"
# Also catch processes in trees/ worktrees
graceful_pkill "trees/[0-9]*.*uvicorn" "worktree uvicorn processes"
graceful_pkill "trees/[0-9]*.*vite" "worktree vite processes"

# Clean up ARQ workers and their multiprocessing children
echo -e "${GREEN}Cleaning up ARQ workers and multiprocessing children...${NC}"
graceful_pkill "arq src.workers" "ARQ workers"
graceful_pkill "multiprocessing.spawn" "multiprocessing spawn workers"
graceful_pkill "multiprocessing.resource_tracker" "multiprocessing resource trackers"

# Also clean up orphaned Python multiprocessing children from worktrees
echo -e "${GREEN}Cleaning up orphaned worktree processes...${NC}"
for worktree_pattern in "trees/[0-9]*-[a-f0-9]*/app/backend/.venv" "trees/[0-9]*-[a-f0-9]*/app/frontend/node_modules"; do
    graceful_pkill "$worktree_pattern" "worktree processes ($worktree_pattern)"
done

echo -e "${GREEN}✓ All services stopped successfully!${NC}"