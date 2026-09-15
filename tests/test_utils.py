"""Tests for smon.utils module."""

import sys

import pytest

from smon.utils import which


class TestWhich:
    """Tests for the which function."""

    def test_which_finds_existing_command(self) -> None:
        """Test that which finds common system commands."""
        if sys.platform == "win32":
            # 'cmd' should exist on all Windows systems
            result = which("cmd")
            assert result is not None
            assert "cmd" in result.lower()
        else:
            # 'ls' should exist on all Unix systems
            result = which("ls")
            assert result is not None
            assert "ls" in result

    def test_which_returns_none_for_nonexistent(self) -> None:
        """Test that which returns None for non-existent commands."""
        result = which("nonexistent_command_xyz123")
        assert result is None

    def test_which_finds_python(self) -> None:
        """Test that which can find python."""
        # sys.executable gives us the running Python interpreter path
        # Just verify which() works by finding it via the full path
        result = which(sys.executable)
        assert result is not None


class TestRunCmd:
    """run_cmd must never leave a child process behind."""

    async def test_success(self) -> None:
        from smon.utils import run_cmd

        rc, out, err = await run_cmd(["sh", "-c", "echo hi; echo oops >&2"])
        assert (rc, out, err) == (0, "hi\n", "oops\n")

    async def test_nonzero_rc(self) -> None:
        from smon.utils import run_cmd

        rc, _, _ = await run_cmd(["sh", "-c", "exit 3"])
        assert rc == 3

    async def test_timeout_kills_child(self) -> None:

        from smon.utils import run_cmd, run_cmd_safe

        rc, _, err = await run_cmd_safe(["sh", "-c", "echo $$ > /dev/stderr; sleep 30"], timeout=0.3)
        assert rc == 124
        with pytest.raises(TimeoutError):
            await run_cmd(["sleep", "30"], timeout=0.2)

    async def test_cancel_kills_child(self, tmp_path) -> None:
        import asyncio
        import os

        from smon.utils import run_cmd

        pid_file = tmp_path / "pid"
        task = asyncio.create_task(run_cmd(["sh", "-c", f"echo $$ > {pid_file}; sleep 30"], timeout=30))
        while not pid_file.exists() or not pid_file.read_text().strip():
            await asyncio.sleep(0.02)
        pid = int(pid_file.read_text())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)  # child must be gone (killed and reaped)

    async def test_missing_binary(self) -> None:
        from smon.utils import run_cmd_safe

        rc, _, err = await run_cmd_safe(["/nonexistent/bin/xyz"])
        assert rc == 127 and "xyz" in err
