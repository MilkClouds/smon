"""Modal screens for smon dashboard.

Note: These modals are currently not used in the main application.
- ScriptModal: Script is now displayed inline in the split view.
- OutputModal: Output is now viewed via external pager (bat/less) with 'o' key.

These classes are kept for potential future use or as reference.
"""

import datetime
from typing import TYPE_CHECKING, Any, Dict, List

from rich.syntax import Syntax
from rich.table import Table
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


class NodeJobsModal(ModalScreen[None]):
    """Modal screen for displaying jobs running on a specific node."""

    CSS = """
    NodeJobsModal {
        align: center middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    def __init__(self, node_name: str, jobs: List[Dict[str, Any]]) -> None:
        super().__init__()
        self.node_name = node_name
        self.jobs = jobs

    def compose(self) -> ComposeResult:
        with Vertical(id="node_jobs_modal_container"):
            job_count = len(self.jobs)
            yield Static(
                f"[bold bright_cyan]🖥️ Jobs on {self.node_name}[/bold bright_cyan] "
                f"[dim]({job_count} job{'s' if job_count != 1 else ''})[/dim]\n"
                f"[dim]Press [bold]Escape[/bold] or [bold]q[/bold] to close[/dim]",
                id="node_jobs_header",
            )
            with ScrollableContainer(id="node_jobs_content"):
                yield Static(self._build_jobs_table(), id="node_jobs_table")

    def _build_jobs_table(self) -> Table:
        """Build a Rich table showing jobs on this node."""
        table = Table(box=None, expand=True, show_header=True, header_style="bold")
        table.add_column("JOBID", style="cyan")
        table.add_column("USER", style="green")
        table.add_column("STATE")
        table.add_column("NAME")
        table.add_column("CPUS", justify="right")
        table.add_column("GPUs", justify="right")
        table.add_column("TIME")

        state_colors = {
            "RUNNING": "green",
            "PENDING": "yellow",
            "COMPLETING": "cyan",
        }

        for job in self.jobs:
            state = job.get("STATE", "")
            state_color = state_colors.get(state, "white")
            table.add_row(
                job.get("JOBID", ""),
                job.get("USER", job.get("USERNAME", "")),
                f"[{state_color}]{state}[/{state_color}]",
                job.get("NAME", ""),
                job.get("CPUS", ""),
                job.get("GPU_COUNT", "0"),
                job.get("TIME", ""),
            )

        if not self.jobs:
            table.add_row("[dim]No jobs running on this node[/dim]", "", "", "", "", "", "")

        return table

    async def action_dismiss(self, result: None = None) -> None:
        """Close the modal."""
        self.dismiss(result)
