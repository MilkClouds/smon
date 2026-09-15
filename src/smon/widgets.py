"""Custom widgets for smon dashboard."""

from typing import Any

from rich.syntax import Syntax
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import RichLog, Static


class StatusBar(Static):
    """Status bar widget displaying messages."""

    message = reactive("Ready")

    def watch_message(self, value: str) -> None:
        # Messages may embed error text with brackets; never treat them as markup.
        self.update(Text(value, style="bold"))


class SyntaxViewer(Static):
    """Widget for displaying syntax-highlighted code."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._code: str = ""
        self._language: str = "bash"

    def set_code(self, code: str, language: str = "bash") -> None:
        """Set the code content with syntax highlighting."""
        self._code = code
        self._language = language
        self._render_code()

    def _render_code(self) -> None:
        """Render the code with current theme."""
        if not self._code.strip():
            self.update("No content to display")
            return
        theme = "monokai" if self.app.current_theme.dark else "github-light"
        self.update(Syntax(self._code, self._language, theme=theme, line_numbers=True))

    def on_app_theme_changed(self) -> None:
        if self._code:
            self._render_code()


class LogViewer(RichLog):
    """Scrollable viewer for a job's stdout/stderr tail.

    Content is plain text (ANSI colours honoured, markup never interpreted).
    Re-setting identical content is a no-op so periodic refreshes do not
    disturb a reader who has scrolled up.
    """

    def __init__(self, placeholder: str = "", **kwargs: Any) -> None:
        super().__init__(wrap=True, markup=False, highlight=False, auto_scroll=True, max_lines=1000, **kwargs)
        self._placeholder = placeholder
        self._content: str | None = None

    def on_mount(self) -> None:
        if self._content is None:
            self.set_content("")

    def set_content(self, content: str) -> None:
        """Replace the whole content; scrolls to the end when it changed."""
        if content == self._content:
            return
        self._content = content
        self.clear()
        if content:
            self.write(Text.from_ansi(content), scroll_end=True)
        elif self._placeholder:
            self.write(Text(self._placeholder, style="dim"))


class GpustatViewer(Static):
    """Widget for displaying gpustat-web content with auto-refresh."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__("[dim]Connecting to gpustat-web...[/dim]", *args, **kwargs)

    def set_content(self, content: str) -> None:
        """Set the content from gpustat-web (already markup-escaped by the client)."""
        self.update(content)

    def set_error(self, message: str) -> None:
        self.update(Text(message, style="red"))

    def set_disconnected(self) -> None:
        self.update(Text("gpustat-web not configured", style="dim"))


class Filter:
    """Filter for jobs and nodes data."""

    def __init__(self) -> None:
        self.job_text: str = ""
        self.node_text: str = ""
        self.user: str | None = None
        self.partition: str | None = None
        self.state: str | None = None

    @staticmethod
    def _text_match(rows: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
        pat = text.lower()
        return [r for r in rows if any(pat in str(v).lower() for v in r.values())]

    def apply_jobs(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply filter to jobs list."""
        res = rows
        if self.user:
            res = [r for r in res if (r.get("USERNAME", "") or r.get("USER", "")).lower() == self.user.lower()]
        if self.partition:
            res = [r for r in res if self.partition.lower() in r.get("PARTITION", "").lower()]
        if self.state:
            res = [r for r in res if self.state.lower() in r.get("STATE", "").lower()]
        if self.job_text:
            res = self._text_match(res, self.job_text)
        return res

    def apply_nodes(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply filter to nodes list."""
        res = rows
        if self.partition:
            res = [r for r in res if self.partition.lower() in r.get("PARTITION", "").lower()]
        if self.node_text:
            res = self._text_match(res, self.node_text)
        return res
