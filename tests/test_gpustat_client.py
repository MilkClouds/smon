"""Tests for smon.gpustat_client module."""

from textual.content import Content

from smon.gpustat_client import GpustatClient


class TestGpustatParsing:
    def test_ws_url(self) -> None:
        assert GpustatClient._http_to_ws_url("http://10.0.0.1:48109/") == "ws://10.0.0.1:48109/ws"
        assert GpustatClient._http_to_ws_url("https://host/") == "wss://host/ws"

    def test_parse_html_keeps_colors_and_escapes_brackets(self) -> None:
        client = GpustatClient("http://x:1/")
        html = (
            "<html><style>a{}</style><script>x()</script>"
            '<pre>\n<span class="ansi32 ansi1">[0] NVIDIA A100</span> | 45&#39;C'
            " | user:python/1(2G) [/x]\n\n</pre></html>"
        )
        text = client._parse_html_to_text(html)
        assert text.startswith("[green bold][0] NVIDIA A100[/green bold]")
        # Must render without MarkupError and preserve the literal brackets.
        assert Content.from_markup(text).plain == "[0] NVIDIA A100 | 45'C | user:python/1(2G) [/x]"
