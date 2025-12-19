"""Custom widgets for smon dashboard."""

from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.syntax import Syntax
from textual.reactive import reactive
from textual.widgets import Static


class StatusBar(Static):
    """Status bar widget displaying messages."""

    message = reactive("Ready")

    def watch_message(self, value: str) -> None:
        self.update(f"[b]{value}[/b]")


class SyntaxViewer(Static):
    """Widget for displaying syntax-highlighted code."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.console = Console()

    def set_code(self, code: str, language: str = "bash") -> None:
        """Set the code content with syntax highlighting."""
        if not code.strip():
            self.update("No content to display")
            return

        try:
            syntax = Syntax(code, language, theme="monokai", line_numbers=True)
            self.update(syntax)
        except Exception:
            self.update(f"```{language}\n{code}\n```")


class LogViewer(Static):
    """Widget for displaying log content with auto-scroll."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._content = ""
        self._max_lines = 1000

    def append_content(self, content: str) -> None:
        """Append new content to the log viewer."""
        if content:
            self._content += content
            lines = self._content.split("\n")
            if len(lines) > self._max_lines:
                lines = lines[-self._max_lines :]
                self._content = "\n".join(lines)
            self.update(self._content)
            self.scroll_end()

    def set_content(self, content: str) -> None:
        """Set the entire content of the log viewer."""
        self._content = content
        lines = content.split("\n")
        if len(lines) > self._max_lines:
            lines = lines[-self._max_lines :]
            self._content = "\n".join(lines)
        self.update(self._content)
        self.scroll_end()

    def clear(self) -> None:
        """Clear the log viewer content."""
        self._content = ""
        self.update("")


class Filter:
    """Filter for jobs and nodes data."""

    def __init__(self) -> None:
        self.text: str = ""
        self.user: Optional[str] = None
        self.partition: Optional[str] = None
        self.state: Optional[str] = None

    def apply_jobs(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply filter to jobs list."""
        res = rows
        if self.user:
            res = [
                r
                for r in res
                if (r.get("USERNAME", "") or r.get("USER", "")).lower() == self.user.lower()
            ]
        if self.partition:
            res = [r for r in res if self.partition.lower() in r.get("PARTITION", "").lower()]
        if self.state:
            res = [r for r in res if self.state.lower() in r.get("STATE", "").lower()]
        if self.text:
            pat = self.text.lower()
            res = [r for r in res if any(pat in str(v).lower() for v in r.values())]
        return res

    def apply_nodes(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply filter to nodes list."""
        res = rows
        if self.partition:
            res = [r for r in res if self.partition.lower() in r.get("PARTITION", "").lower()]
        if self.state:
            res = [r for r in res if self.state.lower() in r.get("STATE", "").lower()]
        if self.text:
            pat = self.text.lower()
            res = [r for r in res if any(pat in str(v).lower() for v in r.values())]
        return res

