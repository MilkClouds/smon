"""Modal screens for smon dashboard.

Note: These modals are currently not used in the main application.
- ScriptModal: Script is now displayed inline in the split view.
- OutputModal: Output is now viewed via external pager (bat/less) with 'o' key.

These classes are kept for potential future use or as reference.
"""

import datetime
from typing import TYPE_CHECKING

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from .widgets import LogViewer

if TYPE_CHECKING:
    from .slurm_client import SlurmClient


class ScriptModal(ModalScreen):
    """Modal screen for displaying job scripts with syntax highlighting."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    def __init__(self, jobid: str, script_content: str) -> None:
        super().__init__()
        self.jobid = jobid
        self.script_content = script_content

    def compose(self) -> ComposeResult:
        with Vertical(id="script_modal_container"):
            yield Static(
                f"[bold bright_cyan]📄 Slurm Script - Job {self.jobid}[/bold bright_cyan]\n"
                f"[dim]Press [bold]Escape[/bold] or [bold]q[/bold] to close[/dim]",
                id="script_header",
                classes="script-header",
            )
            syntax = Syntax(
                self.script_content,
                "bash",
                theme="monokai",
                line_numbers=True,
                word_wrap=False,
                background_color="default",
            )
            yield Static(syntax, id="script_content", classes="script-content")

    async def action_dismiss(self, result=None) -> None:
        """Close the modal."""
        self.dismiss(result)


class OutputModal(ModalScreen):
    """Modal screen for displaying job output."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("r", "refresh_output", "Refresh"),
    ]

    def __init__(self, jobid: str, stdout: str, stderr: str, client: "SlurmClient") -> None:
        super().__init__()
        self.jobid = jobid
        self.stdout = stdout
        self.stderr = stderr
        self.client = client

    def compose(self) -> ComposeResult:
        with Vertical(id="output_modal_container"):
            yield Static(
                f"[bold bright_green]📊 Job Output - Job {self.jobid}[/bold bright_green]\n"
                f"[dim]Press [bold]Escape[/bold]/[bold]q[/bold] to close, "
                f"[bold]r[/bold] to refresh[/dim]",
                id="output_header",
                classes="output-header",
            )
            with Vertical(classes="output-content"):
                yield Static(
                    "[bold bright_blue]📤 STDOUT[/bold bright_blue]",
                    classes="output-section-header",
                )
                with ScrollableContainer(classes="output-scroll-container"):
                    yield LogViewer(
                        self.stdout or "[dim]No stdout available[/dim]",
                        id="modal_stdout_viewer",
                        classes="output-log-viewer",
                    )
                yield Static(
                    "[bold bright_red]📥 STDERR[/bold bright_red]",
                    classes="output-section-header",
                )
                with ScrollableContainer(classes="output-scroll-container"):
                    yield LogViewer(
                        self.stderr or "[dim]No stderr available[/dim]",
                        id="modal_stderr_viewer",
                        classes="output-log-viewer",
                    )

    async def action_dismiss(self, result=None) -> None:
        """Close the modal."""
        self.dismiss(result)

    async def action_refresh_output(self) -> None:
        """Refresh the output content."""
        try:
            stdout, stderr = await self.client.get_job_output(self.jobid, full=True)

            stdout_viewer = self.query_one("#modal_stdout_viewer", LogViewer)
            stdout_viewer.set_content(stdout or "No stdout available")

            stderr_viewer = self.query_one("#modal_stderr_viewer", LogViewer)
            stderr_viewer.set_content(stderr or "No stderr available")

            refresh_time = datetime.datetime.now().strftime("%H:%M:%S")
            header = self.query_one("#output_header", Static)
            header.update(
                f"[bold bright_green]📊 Job Output - Job {self.jobid}[/bold bright_green]\n"
                f"[dim]Last refreshed: {refresh_time} | "
                f"Press [bold]Escape[/bold]/[bold]q[/bold] to close, "
                f"[bold]r[/bold] to refresh[/dim]"
            )
        except Exception as e:
            header = self.query_one("#output_header", Static)
            header.update(
                f"[bold bright_green]📊 Job Output - Job {self.jobid}[/bold bright_green]\n"
                f"[bold red]Refresh error: {e}[/bold red]"
            )
