"""Tests for smon.utils module."""

import sys

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
