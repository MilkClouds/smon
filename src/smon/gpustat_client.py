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
                            message = await asyncio.wait_for(ws.recv(), timeout=10.0)
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
        # Remove script tags and their content
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove style tags
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Extract content from pre tags (gpustat output is usually in pre)
        pre_match = re.search(r"<pre[^>]*>(.*?)</pre>", html, flags=re.DOTALL | re.IGNORECASE)
        if pre_match:
            html = pre_match.group(1)

        # Convert common ANSI color classes to Rich markup
        color_map = {
            "ansi32": "green",  # Green (OK status)
            "ansi31": "red",  # Red (error/high temp)
            "ansi33": "yellow",  # Yellow (warning)
            "ansi34": "blue",  # Blue
            "ansi35": "magenta",  # Magenta
            "ansi36": "cyan",  # Cyan
            "ansi1": "bold",  # Bold
            "ansi2": "dim",  # Dim
        }

        # Replace span tags with Rich markup
        def replace_span(match):
            classes = match.group(1)
            content = match.group(2)
            styles = []
            for cls, style in color_map.items():
                if cls in classes:
                    styles.append(style)
            if styles:
                style_str = " ".join(styles)
                return f"[{style_str}]{content}[/{style_str}]"
            return content

        html = re.sub(r'<span[^>]*class="([^"]*)"[^>]*>(.*?)</span>', replace_span, html, flags=re.DOTALL)

        # Remove remaining HTML tags
        html = re.sub(r"<[^>]+>", "", html)

        # Unescape HTML entities
        html = unescape(html)

        # Clean up whitespace
        lines = [line.rstrip() for line in html.split("\n")]
        # Remove empty lines at start and end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        return "\n".join(lines)
