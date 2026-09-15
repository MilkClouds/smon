"""Utility functions for smon."""

import asyncio
import contextlib
import os
import signal
from collections.abc import Sequence


def which(cmd: str) -> str | None:
    """Find the full path of a command in PATH (absolute paths are checked directly)."""
    if os.sep in cmd:
        return cmd if os.path.isfile(cmd) and os.access(cmd, os.X_OK) else None
    for path in os.environ.get("PATH", "").split(os.pathsep):
        full = os.path.join(path, cmd)
        if os.path.isfile(full) and os.access(full, os.X_OK):
            return full
    return None


async def run_cmd(argv: Sequence[str], timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a command (argv list, no shell) with a timeout.

    The child runs in its own process group and the whole group is killed on
    timeout or cancellation, so a slow `squeue` (or anything it spawned) cannot
    pile up behind the dashboard.

    Returns:
        Tuple of (return_code, stdout, stderr). Timeout yields rc=124.
    """
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (TimeoutError, asyncio.CancelledError):
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        with contextlib.suppress(Exception):
            await proc.wait()
        raise
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def run_cmd_safe(argv: Sequence[str], timeout: float = 10.0) -> tuple[int, str, str]:
    """Like run_cmd, but reports timeout / missing binary as an rc instead of raising."""
    try:
        return await run_cmd(argv, timeout=timeout)
    except TimeoutError:
        return 124, "", f"Timeout after {timeout:g}s: {' '.join(argv)}"
    except FileNotFoundError as e:
        return 127, "", str(e)
