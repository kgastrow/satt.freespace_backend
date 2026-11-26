"""System information collector for command center heartbeat payloads.

Uses psutil to gather CPU and memory usage metrics.
Falls back gracefully if psutil is not available.
"""

import platform
from typing import Dict, Any


def get_system_load() -> Dict[str, Any]:
    """Get current CPU and memory usage percentages.

    Returns:
        Dictionary with cpu_percent and memory_percent keys.
        Returns -1 for values that cannot be determined.
    """
    try:
        import psutil

        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
        }
    except ImportError:
        return {
            "cpu_percent": -1,
            "memory_percent": -1,
        }


def get_system_info() -> Dict[str, Any]:
    """Get static system information for registration payload.

    Returns:
        Dictionary with os, arch, and platform details.
    """
    return {
        "os": platform.system(),
        "arch": platform.machine(),
        "platform": platform.platform(),
    }
