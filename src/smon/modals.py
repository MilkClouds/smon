"""Modal screens for smon dashboard."""

from typing import Any

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmModal(ModalScreen[bool]):
    """Yes/No confirmation. `y`/Enter confirms, `n`/Escape aborts."""

    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    #confirm_box {
        width: auto; max-width: 80%; height: auto;
        background: $surface; border: thick $warning; padding: 1 2;
    }
    #confirm_msg { width: auto; margin-bottom: 1; }
    #confirm_buttons { width: auto; height: auto; }
    #confirm_buttons Button { margin-right: 1; }
    """

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("enter", "confirm", "Yes", show=False),
        Binding("n", "abort", "No"),
        Binding("escape", "abort", "No", show=False),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm_box"):
            yield Static(Text(self.message), id="confirm_msg")
            with Horizontal(id="confirm_buttons"):
                yield Button("Yes (y)", variant="error", id="yes")
                yield Button("No (n)", id="no")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_abort(self) -> None:
        self.dismiss(False)


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

    def __init__(self, node_name: str, jobs: list[dict[str, Any]]) -> None:
        super().__init__()
        self.node_name = node_name
        self.jobs = jobs

    def compose(self) -> ComposeResult:
        with Vertical(id="node_jobs_modal_container"):
            job_count = len(self.jobs)
            header = Text.assemble(
                (f"🖥️ Jobs on {self.node_name} ", "bold bright_cyan"),
                (f"({job_count} job{'s' if job_count != 1 else ''})\n", "dim"),
                ("Press Escape or q to close", "dim"),
            )
            yield Static(header, id="node_jobs_header")
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

        state_colors = {"RUNNING": "green", "PENDING": "yellow", "COMPLETING": "cyan"}

        for job in self.jobs:
            state = job.get("STATE", "")
            table.add_row(
                job.get("JOBID", ""),
                job.get("USER", job.get("USERNAME", "")),
                Text(state, style=state_colors.get(state, "white")),
                Text(job.get("NAME", "")),
                job.get("CPUS", ""),
                job.get("GPU_COUNT", "0"),
                job.get("TIME", ""),
            )

        if not self.jobs:
            table.add_row(Text("No jobs running on this node", style="dim"), "", "", "", "", "", "")

        return table
