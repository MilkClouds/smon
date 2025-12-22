"""GPUstat-web client for fetching GPU status via WebSocket."""

import asyncio
import re
from html import unescape
from typing import Callable, Optional
from urllib.parse import urlparse

try:
    from websockets.asyncio.client import connect as ws_connect

    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

# Pre-compiled regex patterns for HTML parsing
_SCRIPT_PATTERN = re.compile(r"<script[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
_STYLE_PATTERN = re.compile(r"<style[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
_PRE_PATTERN = re.compile(r"<pre[^>]*>(.*?)</pre>", re.DOTALL | re.IGNORECASE)
_SPAN_PATTERN = re.compile(r'<span[^>]*class="([^"]*)"[^>]*>(.*?)</span>', re.DOTALL)
_TAG_PATTERN = re.compile(r"<[^>]+>")

# ANSI CSS class to Rich style mapping
_ANSI_COLOR_MAP = {
    "ansi32": "green",  # Green (OK status)
    "ansi31": "red",  # Red (error/high temp)
    "ansi33": "yellow",  # Yellow (warning)
    "ansi34": "blue",  # Blue
    "ansi35": "magenta",  # Magenta
    "ansi36": "cyan",  # Cyan
    "ansi1": "bold",  # Bold
    "ansi2": "dim",  # Dim
}


class GpustatClient:
    """Client for connecting to gpustat-web and receiving GPU status updates."""

    def __init__(self, url: str) -> None:
        """Initialize the client with the gpustat-web URL.

        Args:
            url: The HTTP URL of gpustat-web (e.g., http://10.50.0.111:48109/)
        """
        self.url = url
        self._ws_url = self._http_to_ws_url(url)
        self._ws = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @staticmethod
    def _http_to_ws_url(http_url: str) -> str:
        """Convert HTTP URL to WebSocket URL."""
        parsed = urlparse(http_url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        return f"{ws_scheme}://{parsed.netloc}/ws"

    @staticmethod
    def is_available() -> bool:
        """Check if websockets library is available."""
        return HAS_WEBSOCKETS

    async def connect(self, on_message: Callable[[str], None]) -> None:
        """Connect to gpustat-web WebSocket and receive updates.

        Args:
            on_message: Callback function to handle received messages (parsed text).
        """
        if not HAS_WEBSOCKETS:
            on_message("[dim]websockets library not installed[/dim]")
            return

        self._running = True
        retry_delay = 1.0

        while self._running:
            try:
                async with ws_connect(self._ws_url) as ws:
                    self._ws = ws
                    retry_delay = 1.0  # Reset on successful connection

                    # Send initial query
                    await ws.send('{"message": "query"}')

                    while self._running:
                        try:
                            raw_message = await asyncio.wait_for(ws.recv(), timeout=10.0)
                            if isinstance(raw_message, str):
                                message = raw_message
                            else:
                                message = bytes(raw_message).decode("utf-8", errors="replace")
                            parsed = self._parse_html_to_text(message)
                            on_message(parsed)
                        except asyncio.TimeoutError:
                            # Send ping to keep connection alive
                            await ws.send('{"message": "query"}')

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    on_message(f"[red]Connection error: {e}[/red]\nRetrying in {retry_delay:.0f}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30.0)

    async def disconnect(self) -> None:
        """Disconnect from gpustat-web."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _parse_html_to_text(self, html: str) -> str:
        """Parse HTML content from gpustat-web to displayable text.

        Converts ANSI CSS classes back to Rich markup for terminal display.
        """
        # Remove script and style tags
        html = _SCRIPT_PATTERN.sub("", html)
        html = _STYLE_PATTERN.sub("", html)

        # Extract content from pre tags (gpustat output is usually in pre)
        pre_match = _PRE_PATTERN.search(html)
        if pre_match:
            html = pre_match.group(1)

        # Replace span tags with Rich markup
        def replace_span(match: re.Match[str]) -> str:
            classes = match.group(1)
            content = match.group(2)
            styles = [style for cls, style in _ANSI_COLOR_MAP.items() if cls in classes]
            if styles:
                style_str = " ".join(styles)
                return f"[{style_str}]{content}[/{style_str}]"
            return content

        html = _SPAN_PATTERN.sub(replace_span, html)

        # Remove remaining HTML tags and unescape entities
        html = unescape(_TAG_PATTERN.sub("", html))

        # Clean up whitespace - strip leading/trailing empty lines
        lines = [line.rstrip() for line in html.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        return "\n".join(lines)
