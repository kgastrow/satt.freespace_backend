"""Shared workflow control operations for ADW system.

Provides stop/resume functionality used by both the webhook trigger
and the command center agent. Extracted from trigger_webhook.py to
avoid import side effects (FastAPI app creation, load_dotenv, etc.).
"""

import logging
import os
import signal
from typing import Tuple

from adw_modules.state import ADWState

logger = logging.getLogger(__name__)


def stop_workflow(adw_id: str) -> Tuple[bool, str]:
    """Stop a running workflow by killing its process group.

    Args:
        adw_id: The ADW ID of the workflow to stop

    Returns:
        Tuple of (success, message)
    """
    state = ADWState.load(adw_id)
    if not state:
        return False, f"No state found for ADW ID `{adw_id}`"

    workflow_pid = state.get("workflow_pid")
    workflow_pgid = state.get("workflow_pgid")

    if not workflow_pid and not workflow_pgid:
        return False, f"No running process found for ADW ID `{adw_id}`"

    killed_processes = []
    errors = []

    # Try to kill the process group first (kills all child processes)
    if workflow_pgid:
        try:
            os.killpg(workflow_pgid, signal.SIGTERM)
            killed_processes.append(f"process group {workflow_pgid}")
        except ProcessLookupError:
            pass
        except PermissionError as e:
            errors.append(f"Permission denied killing process group: {e}")
        except Exception as e:
            errors.append(f"Error killing process group: {e}")

    # Also try to kill the main PID directly as backup
    if workflow_pid:
        try:
            os.kill(workflow_pid, signal.SIGTERM)
            killed_processes.append(f"PID {workflow_pid}")
        except ProcessLookupError:
            pass
        except PermissionError as e:
            errors.append(f"Permission denied killing PID: {e}")
        except Exception as e:
            errors.append(f"Error killing PID: {e}")

    # Update state to indicate workflow was stopped
    state.update(workflow_stage="stopped", workflow_pid=None, workflow_pgid=None)
    state.save("workflow_stop")

    if killed_processes:
        return True, f"Stopped {', '.join(killed_processes)}"
    elif errors:
        return False, f"Failed to stop: {'; '.join(errors)}"
    else:
        return True, "Workflow was not running (already stopped or completed)"


def is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is still running.

    Args:
        pid: Process ID to check

    Returns:
        True if the process exists and is running
    """
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
