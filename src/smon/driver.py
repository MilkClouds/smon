"""Terminal driver tweaks.

Textual (8.x) negotiates in-band window resize (DECSET 2048) and, when the
terminal supports it, switches mouse reporting to pixel coordinates (1016).
Some multiplexers answer "supported" and send resize reports with pixel
sizes, yet keep forwarding *cell* coordinates for mouse events. Textual then
divides every coordinate by the cell size, so every click lands in the
top-left cell (the Header icon, which opens the command palette).
Seen with herdr <= 0.9.0: https://github.com/herdrdev/herdr/issues/3295

smon gains nothing from sub-cell precision, so it opts out of that
negotiation unless SMON_PIXEL_MOUSE=1 is set.
"""

import os
import sys

PIXEL_MOUSE_ENV = "SMON_PIXEL_MOUSE"


def pixel_mouse_requested() -> bool:
    return os.environ.get(PIXEL_MOUSE_ENV, "") == "1"


def get_driver_class():
    """Return the cell-coordinate driver, or None to keep Textual's own selection.

    Only Textual's default Linux driver is replaced: Windows, an explicit
    TEXTUAL_DRIVER, or SMON_PIXEL_MOUSE=1 all fall through to Textual.
    """
    if sys.platform == "win32" or os.environ.get("TEXTUAL_DRIVER") or pixel_mouse_requested():
        return None

    from textual.drivers.linux_driver import LinuxDriver

    class CellMouseLinuxDriver(LinuxDriver):
        """LinuxDriver that never asks for in-band resize or pixel mouse reports."""

        def _query_in_band_window_resize(self) -> None:  # no DECRQM 2048 -> no pixel mode
            pass

        def _enable_in_band_window_resize(self) -> None:
            pass

        def _enable_mouse_pixels(self) -> None:
            pass

    return CellMouseLinuxDriver
