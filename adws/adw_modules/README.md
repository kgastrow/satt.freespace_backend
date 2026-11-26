# ADW Modules

Shared Python modules used by the Agentic Developer Workflow (ADW) system. These modules are imported by workflow orchestrators (`adws/adw_*_iso.py`) and trigger entry points (`adws/adw_triggers/`).

## Module Index

### Core ADW Infrastructure

| Module | Purpose |
|---|---|
| `agent.py` | Claude Code CLI execution. Builds prompts, selects models, injects context preambles, handles retries (usage limits, server errors, timeouts). Entry points: `execute_template()`, `prompt_claude_code_with_retry()`. |
| `state.py` | Persistent ADW state via `agents/{adw_id}/adw_state.json`. Atomic writes with file locking (`fcntl`). Class: `ADWState` with `load()`, `save()`, `update()`, `from_stdin()`, `to_stdout()`. |
| `data_types.py` | Pydantic models for the entire ADW system: `ADWStateData`, `AgentPromptRequest/Response`, `AgentTemplateRequest`, `ClaudeCodeResultMessage`, test result types, review types, smoke test types, consistency review types. Also defines `SlashCommand`, `ModelSet`, `ADWWorkflow` literals. |
| `utils.py` | Shared utilities: `make_adw_id()` (timestamp-UUID format), `setup_logger()` (rotating file + console), `get_safe_subprocess_env()` (filtered env for subprocesses), `parse_json()` (handles markdown code blocks), `check_env_vars()`. |
| `workflow_ops.py` | Workflow orchestration helpers: `AVAILABLE_ADW_WORKFLOWS` list, `extract_adw_info()` (classify issue text into workflow), `find_latest_adw_for_issue()`, agent name constants. |
| `workflow_control.py` | Shared stop/resume operations: `stop_workflow(adw_id)` kills the process group via SIGTERM, `is_process_running(pid)` checks liveness. Used by both `trigger_webhook.py` and the command center agent. |

### Git & GitHub

| Module | Purpose |
|---|---|
| `github.py` | GitHub CLI (`gh`) operations: `check_gh_auth()`, `make_issue_comment()` (with retry, truncation, bot identifier), `fetch_issue()`, `fetch_open_issues()`, `poll_for_comment_response_with_status()`. |
| `git_ops.py` | Git operations: branch creation, commit, push, PR creation. Builds on `github.py`. |
| `github_data_provider.py` | Fetches issues/PRs/commits via `gh` CLI for relay to the command center. `fetch_github_data(data_type, filters, cwd)` returns structured data. `fetch_pr_for_branch(branch, cwd)` looks up PR numbers. |

### Isolation & Infrastructure

| Module | Purpose |
|---|---|
| `resources.py` | Machine-wide resource registry shared by every codebase on the machine (`~/.adw/resources.json`, fcntl-locked): leases (port pair, Redis database, DB name) keyed by adw_id, `workflow` / `full_suite` slots (`ADW_MAX_WORKFLOWS`, `ADW_MAX_FULL_SUITES`), automatic reclaim of stale entries. CLI: `adws/adw_resources.py`. |
| `worktree_ops.py` | Git worktree and port management for isolated ADW execution. Ports come from the `resources.py` lease (9100-9199 backend, 9200-9299 frontend); `ADW_RESOURCES=static` uses the old `ADW_CODEBASE_INDEX` / `ADW_MAX_CODEBASES` partitioning (9100-9114, 9200-9214). |
| `database_ops.py` | Isolated PostgreSQL database and Redis DB management per ADW. `create_isolated_database()`, `drop_isolated_database()`, `flush_redis_db_for_adw()`. |
| `r2_uploader.py` | Cloudflare R2 uploader for smoke test and review screenshots. |
| `image_upload.py` | Screenshot upload for the orchestrated workflow (`adw_report.py image`): R2 when configured, else an orphan `adw-screenshots` branch in the repo. |
| `messages.py` | Files between the Ore trigger, an orchestrated workflow and its orchestrator: `inbox.jsonl` (Ore's messages, answers), `outbox.jsonl` (replies, questions), `usage.json` (cost, tokens, rate limits from the stream), `images.jsonl` (screenshots). |

### Testing & Review

| Module | Purpose |
|---|---|
| `test_ops.py` | Shared test execution: scoped test running, result parsing, failure detection. |
| `multi_phase_ops.py` | Multi-phase workflow operations: plan parsing, phase state management, dependency tracking. |
| `rescue_state.py` | Extended state management for the Vibe Code Rescue workflow. |

### Command Center Agent

These modules implement the client-side agent that connects a codebase to the centralized Ayzer Command Center. See `specs/command_center_client.md` for the full specification.

| Module | Purpose |
|---|---|
| `command_center_client.py` | Core WebSocket client. Manages the outbound connection, authentication, heartbeat, message routing, event replay, and orchestrates the file watcher + log streamer. |
| `file_watcher.py` | Watches `agents/*/adw_state.json` for changes using `watchdog` (FSEvents on macOS, inotify on Linux). Debounces events (500ms) to handle atomic-rename write patterns. |
| `log_streamer.py` | Tails `raw_output.jsonl` files for active ADWs. Always streams to the command center for server-side storage. Rate limited (50 lines/sec/ADW) with backpressure (pauses at 5000 pending messages). |
| `system_info.py` | System metrics via `psutil`: `get_system_load()` (CPU/memory %) and `get_system_info()` (OS/arch/platform). |

---

## Command Center Agent

The command center agent is a lightweight WebSocket client that connects each codebase to a centralized dashboard. It runs as a long-lived process alongside the existing webhook and cron triggers.

### Architecture

```
                    Command Center (Server)
                           |
                     WSS connection
                           |
    trigger_command_center.py  (entry point)
              |
    CommandCenterClient  (command_center_client.py)
         /         \
   ADWFileWatcher   LogStreamer
 (file_watcher.py) (log_streamer.py)
         |                |
  agents/*/           agents/*/
  adw_state.json      */raw_output.jsonl
```

### Entry Point

```
adws/adw_triggers/trigger_command_center.py
```

Run with: `uv run adws/adw_triggers/trigger_command_center.py`

PEP 723 inline dependencies: `websockets`, `watchdog`, `psutil`, `python-dotenv`, `pydantic`

### Configuration

Set in `.env` (all optional -- if `COMMAND_CENTER_URL` is unset, the agent does not start):

```bash
COMMAND_CENTER_URL=wss://agent-bridge.ayzer.ai/ws/agent
COMMAND_CENTER_API_KEY=<per-codebase-key>
CODEBASE_NAME=my-project
MACHINE_NAME=macmini-01
CC_AGENT_HEALTH_PORT=       # optional local health endpoint
```

### Connection Lifecycle

1. **Connect** to `COMMAND_CENTER_URL` via WebSocket
2. **Authenticate** with first-message API key + protocol version
3. **Register** with codebase metadata (name, repo URL, template version, available ADWs, active ADWs, system info)
4. **Replay** any events buffered during disconnection
5. **Run** three concurrent loops: receive commands, send queued messages, heartbeat (30s)
6. **On disconnect**, exponential backoff reconnect (1s -> 2s -> 4s -> ... -> 60s cap, resets after 60s connected)

### Message Types

**Agent sends:**

| Type | When | Content |
|---|---|---|
| `auth` | On connect | API key + protocol version |
| `register` | After auth | Codebase metadata, active ADWs, system info |
| `heartbeat` | Every 30s | Active ADW IDs, CPU/memory |
| `adw_status` | On `adw_state.json` change | ADW ID, status, workflow stage, issue number |
| `adw_complete` | On terminal state | Status, error summary, duration, PR number |
| `log_line` | Continuously for active ADWs | Agent name, JSONL content, timestamp |
| `response` | After server request | Success/failure + request-specific data |

**Agent receives:**

| Type | Action |
|---|---|
| `trigger_adw` | Create GitHub issue (if needed), launch workflow subprocess |
| `control_adw` | Cancel (SIGTERM) or resume (re-launch with `--resume`) |
| `request_status` | Return current state snapshot |
| `request_logs` | Return historical JSONL tail |
| `request_github_data` | Fetch issues/PRs/commits via `gh` CLI |
| `apply_patch` | Apply template drift patch via `git apply` |

### Key Design Decisions

- **Thread safety**: The file watcher and log streamer run in background threads. All message enqueueing uses `loop.call_soon_threadsafe()` to safely interact with the asyncio event loop.
- **Backpressure**: The log streamer pauses tailing when the send queue exceeds 5000 messages and resumes at 2500.
- **Rate limiting**: Log lines are capped at 50/sec per ADW (25 per 0.5s poll cycle).
- **Event replay**: Status and completion events are buffered (max 500) during disconnection and replayed on reconnect. Log lines are not buffered (too large).
- **Graceful degradation**: If `COMMAND_CENTER_URL` is not set, the agent does not start. All existing ADW triggers continue to work independently.
- **Lockfile**: Prevents duplicate agent instances per codebase via `/tmp/cc-agent-{name}.lock`.
- **No pause**: Only cancel and resume are supported. SIGSTOP is unreliable for process groups with active I/O.

### Deployment (Multi-Codebase)

Multiple codebases can run on the same Mac Mini. Each gets its own service instance, namespaced by `CODEBASE_NAME` to avoid conflicts:

| Resource | Pattern |
|---|---|
| launchd plist | `com.ayzer.cc-agent.{codebase-name}.plist` |
| Log file | `/tmp/cc-agent-{codebase-name}.log` |
| Lockfile | `/tmp/cc-agent-{codebase-name}.lock` |

**macOS (launchd) -- run once per codebase:**

```bash
cd /path/to/project
./scripts/install_command_center_agent_macos.sh
```

The script reads `CODEBASE_NAME` from `.env`, generates a namespaced plist, injects all env vars, and loads it. Re-run to update config.

```bash
# Uninstall this codebase's agent
./scripts/uninstall_command_center_agent_macos.sh

# Uninstall ALL agents on this machine
./scripts/uninstall_command_center_agent_macos.sh --all

# List all agents on this machine
launchctl list | grep cc-agent

# View logs for a specific codebase
tail -f /tmp/cc-agent-client-alpha.log
```

**Linux (systemd) -- one unit per codebase:**

```bash
CODEBASE=client-alpha
PROJECT_DIR=/home/user/projects/$CODEBASE

cat > /etc/systemd/system/cc-agent-${CODEBASE}.service << EOF
[Unit]
Description=Ayzer CC Agent - ${CODEBASE}
After=network-online.target
[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}/adws/adw_triggers
ExecStart=/usr/bin/uv run trigger_command_center.py
Restart=always
RestartSec=5
EnvironmentFile=${PROJECT_DIR}/.env
[Install]
WantedBy=multi-user.target
EOF

systemctl enable --now cc-agent-${CODEBASE}
```

### Health Check

When `CC_AGENT_HEALTH_PORT` is set, the agent exposes a local HTTP endpoint:

```bash
curl http://127.0.0.1:${CC_AGENT_HEALTH_PORT}/health
```

```json
{
  "status": "connected",
  "codebase": "my-project",
  "machine": "macmini-01",
  "active_adws": 2,
  "last_heartbeat": "2026-04-11T10:00:30Z"
}
```

### Relationship to Other Triggers

The command center agent coexists with the existing triggers:

| Trigger | Port | Entry |
|---|---|---|
| `trigger_webhook.py` | 8001 | GitHub webhook events |
| `trigger_cron.py` | N/A | Polls GitHub issues every 20s |
| `trigger_command_center.py` | N/A (WSS outbound) | Commands from command center |

All three can run simultaneously. Each launches ADW workflows via `subprocess.Popen()` using the same isolation infrastructure (worktrees, port allocation, database isolation).

The command center enforces 1 ADW per codebase for command center-originated work. It has no control over webhook/cron-triggered ADWs, but reports all ADWs (regardless of origin) for visibility.
