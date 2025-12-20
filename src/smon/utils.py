"""Utility functions for smon."""

import asyncio
import contextlib
import os
import signal
from typing import Optional, Tuple


def which(cmd: str) -> Optional[str]:
    """Find the full path of a command in PATH."""
    for path in os.environ.get("PATH", "").split(os.pathsep):
        full = os.path.join(path, cmd)
        if os.path.isfile(full) and os.access(full, os.X_OK):
            return full
    return None


async def run_cmd(cmd: str, timeout: float = 10.0) -> Tuple[int, str, str]:
    """Run a shell command asynchronously with timeout.

    Args:
        cmd: Shell command to execute
        timeout: Timeout in seconds

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        executable=os.environ.get("SHELL", "/bin/bash"),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.send_signal(signal.SIGINT)
        return 124, "", f"Timeout after {timeout}s for: {cmd}"
    return proc.returncode or 0, stdout.decode(errors="ignore"), stderr.decode(errors="ignore")
