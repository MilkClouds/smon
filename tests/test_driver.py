"""The app must not negotiate pixel-coordinate mouse reporting (see smon/driver.py)."""

import os
import pty
import select
import signal
import sys
import time

import pytest

QUERY_2048 = b"\x1b[?2048$p"
# Sent by LinuxDriver right after the (optional) 2048 query, so seeing it means the decision was made.
BRACKETED_PASTE_ON = b"\x1b[?2004h"


def _capture_startup_bytes(env: dict[str, str], seconds: float = 3.0) -> bytes:
    pid, fd = pty.fork()
    if pid == 0:  # child
        os.environ.update(env)
        os.execv(sys.executable, [sys.executable, "-c", "from smon.main import main; main()", "--mock"])
    out = b""
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            if select.select([fd], [], [], 0.2)[0]:
                try:
                    out += os.read(fd, 65536)
                except OSError:
                    break
                if BRACKETED_PASTE_ON in out:
                    break
    finally:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        os.close(fd)
    return out


@pytest.mark.skipif(sys.platform == "win32", reason="pty")
def test_default_skips_in_band_resize_query() -> None:
    out = _capture_startup_bytes({})
    assert b"\x1b[?1049h" in out  # app actually started (alt screen)
    assert QUERY_2048 not in out
    assert b"\x1b[?1016h" not in out


@pytest.mark.skipif(sys.platform == "win32", reason="pty")
def test_opt_in_restores_textual_default() -> None:
    out = _capture_startup_bytes({"SMON_PIXEL_MOUSE": "1"})
    assert QUERY_2048 in out


def test_explicit_textual_driver_is_honoured(monkeypatch) -> None:
    from smon import driver

    monkeypatch.setenv("TEXTUAL_DRIVER", "textual.drivers.headless_driver:HeadlessDriver")
    assert driver.get_driver_class() is None
    monkeypatch.delenv("TEXTUAL_DRIVER")
    assert driver.get_driver_class() is not None
