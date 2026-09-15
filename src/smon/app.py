"""Main Slurm Dashboard application."""

import asyncio
import datetime
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Sequence
from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Select, Static, TabbedContent, TabPane
from textual.worker import Worker

from .gpustat_client import GpustatClient
from .modals import ConfirmModal, NodeJobsModal
from .slurm_client import SlurmClient
from .styles import APP_CSS
from .widgets import Filter, GpustatViewer, LogViewer, StatusBar, SyntaxViewer

# Sorting constants
_MEM_UNITS = {"K": 1, "M": 1024, "G": 1024**2, "T": 1024**3}
_MEM_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)\s*([KMGT])?", re.IGNORECASE)
_INT_COLUMNS = frozenset({"GPUs", "CPUS", "Nodes", "JOBID"})
_MEM_COLUMNS = frozenset({"MEM"})

_JOB_COLUMNS_FULL = (
    "JOBID",
    "USERNAME",
    "STATE",
    "PARTITION",
    "CPUS",
    "MEM",
    "GPUs",
    "TimeUsed",
    "TimeLimit",
    "NAME",
    "ReqNodes",
    "Nodes",
    "NodeList",
)
_JOB_COLUMNS_BASIC = (
    "JOBID",
    "USER",
    "STATE",
    "PARTITION",
    "CPUS",
    "MEM",
    "TIME",
    "NAME",
    "Nodes",
    "NODELIST(REASON)",
)
_NODE_COLUMNS = ("NODE", "STATE", "AVAIL", "GPUs", "CPUS", "MEM", "PARTITION")

Row = tuple[str, tuple[Any, ...]]  # (row key, cells)


class SlurmDashboard(App):
    """Slurm Dashboard application for monitoring jobs and nodes."""

    TITLE = "smon"
    CSS = APP_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "focus_search", "Search"),
        Binding("escape", "focus_table", "Back to table", show=False),
        Binding("o", "show_output", "Output"),
        Binding("t", "toggle_realtime", "Real-time"),
        Binding("1", "goto_jobs", "Jobs", key_display="1"),
        Binding("2", "goto_nodes", "Nodes", key_display="2"),
        Binding("c", "cancel_job", "Cancel"),
        Binding("y", "copy_jobid", "Copy ID"),
        Binding("plus", "increase_refresh", "+Refresh", show=False),
        Binding("minus", "decrease_refresh", "-Refresh", show=False),
        Binding("T", "toggle_theme", "Theme"),
    ]

    # State color mappings
    JOB_STATE_COLORS = {
        "RUNNING": "green",
        "PENDING": "yellow",
        "COMPLETED": "dim",
        "COMPLETING": "cyan",
        "FAILED": "red",
        "CANCELLED": "red",
        "TIMEOUT": "red",
        "NODE_FAIL": "red",
        "OUT_OF_MEMORY": "red",
        "PREEMPTED": "magenta",
        "SUSPENDED": "magenta",
    }

    NODE_STATE_COLORS = {
        "idle": "green",
        "mixed": "yellow",
        "allocated": "yellow",
        "alloc": "yellow",
        "down": "red",
        "drain": "red",
        "draining": "magenta",
        "drained": "magenta",
        "reserved": "cyan",
    }

    # State filter options
    STATE_OPTIONS = [
        ("All States", ""),
        ("Running", "RUNNING"),
        ("Pending", "PENDING"),
        ("Completed", "COMPLETED"),
        ("Failed", "FAILED"),
        ("Cancelled", "CANCELLED"),
    ]

    def __init__(
        self,
        *,
        refresh_sec: float = 5.0,
        user: str | None = None,
        partition: str | None = None,
        state: str | None = None,
        gpustat_web_url: str | None = None,
        mock_mode: bool = False,
        theme: str = "dark",
    ) -> None:
        super().__init__()
        self.theme = "textual-light" if theme == "light" else "textual-dark"
        self.refresh_sec = refresh_sec
        self.client = SlurmClient(mock_mode=mock_mode)
        self.filter = Filter()
        self.filter.user = user
        self.filter.partition = partition
        self.filter.state = state or None
        self.status = StatusBar(classes="bar")
        self.current_jobid: str | None = None
        self.output_refresh_enabled = False
        self.user_wants_realtime = True
        self.last_refresh_time: datetime.datetime | None = None
        self._sort_column: str | None = None
        self._sort_reverse: bool = False
        self._jobs_raw: list[dict[str, Any]] = []
        self._nodes_raw: list[dict[str, Any]] = []
        self._jobs_shown = 0
        self._nodes_shown = 0
        self._refresh_worker: Worker[None] | None = None
        self._refresh_timer = None
        # gpustat-web integration
        self.gpustat_web_url = gpustat_web_url
        self._gpustat_client: GpustatClient | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield self.status
        with TabbedContent():
            with TabPane("Jobs", id="tab_jobs"):
                with Horizontal(id="jobs_split", classes="split-container"):
                    with Vertical(id="jobs_list_pane", classes="list-pane"):
                        with Horizontal(classes="filter-bar"):
                            yield Input(placeholder="/ Search", id="job_search", classes="search-input")
                            yield Select(
                                self.STATE_OPTIONS,
                                value=self.filter.state or "",
                                allow_blank=False,
                                id="state_filter",
                                classes="state-select",
                            )
                        yield DataTable(id="jobs_table", classes="data-table")
                    with Vertical(id="jobs_detail_pane", classes="detail-pane"):
                        with ScrollableContainer(id="job_detail_container", classes="detail-section"):
                            yield Static("Select a job to see details.", id="job_detail")
                        with Vertical(id="script_section", classes="script-section"):
                            yield Static("[bold cyan]📄 Script[/bold cyan]", classes="section-header")
                            with ScrollableContainer(classes="script-scroll"):
                                yield SyntaxViewer("Select a job to view script", id="script_viewer")
                        with Vertical(id="output_section", classes="output-section"):
                            yield Static("[bold green]📊 Output[/bold green]", classes="section-header")
                            with Horizontal(classes="output-split"):
                                with Vertical(classes="output-half"):
                                    yield Static("[dim]STDOUT[/dim]", classes="output-label")
                                    yield LogViewer("No stdout", id="stdout_viewer", classes="output-viewer")
                                with Vertical(classes="output-half"):
                                    yield Static("[dim]STDERR[/dim]", classes="output-label")
                                    yield LogViewer("No stderr", id="stderr_viewer", classes="output-viewer")
            with TabPane("Nodes", id="tab_nodes"):
                with Horizontal(id="nodes_split", classes="split-container"):
                    with Vertical(id="nodes_list_pane", classes="nodes-list-pane"):
                        yield Input(placeholder="/ Search in nodes", id="node_search")
                        yield DataTable(id="nodes_table", classes="data-table")
                    with Vertical(id="gpustat_pane", classes="gpustat-pane"):
                        yield Static("[bold cyan]🖥️ GPU Status[/bold cyan]", classes="section-header")
                        with ScrollableContainer(id="gpustat_container", classes="gpustat-container"):
                            yield GpustatViewer(id="gpustat_viewer")
        yield Footer()

    async def on_mount(self) -> None:
        for table_id in ("#jobs_table", "#nodes_table"):
            table = self.query_one(table_id, DataTable)
            table.cursor_type = "row"
            table.zebra_stripes = True
        self.query_one("#jobs_table", DataTable).focus()

        # Never await Slurm calls on the app's message loop: a slow squeue would freeze the UI.
        self._schedule_refresh()
        self._refresh_timer = self.set_interval(self.refresh_sec, self._schedule_refresh)
        self.set_interval(5.0, self._schedule_output_refresh)
        self._start_gpustat_connection()

    # ------------------------------------------------------------------ gpustat
    def _start_gpustat_connection(self) -> None:
        """Start gpustat-web WebSocket connection."""
        gpustat_viewer = self.query_one("#gpustat_viewer", GpustatViewer)

        if not self.gpustat_web_url:
            gpustat_viewer.set_disconnected()
            return

        if not GpustatClient.is_available():
            gpustat_viewer.set_error("websockets library not installed")
            return

        self._gpustat_client = GpustatClient(self.gpustat_web_url)

        def on_gpustat_message(content: str) -> None:
            self.call_later(gpustat_viewer.set_content, content)

        self.run_worker(
            self._gpustat_client.connect(on_gpustat_message),
            group="gpustat",
            exclusive=True,
            exit_on_error=False,
        )

    # ------------------------------------------------------------------ refresh
    def _schedule_refresh(self) -> None:
        """Run a refresh in a worker; skip the tick if the previous one is still running."""
        if self._refresh_worker is not None and self._refresh_worker.is_running:
            return
        self._refresh_worker = self.run_worker(self.refresh_data(), group="refresh", exit_on_error=False)

    def _update_refresh_timer(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
        self._refresh_timer = self.set_interval(self.refresh_sec, self._schedule_refresh)

    def _schedule_output_refresh(self) -> None:
        if self.output_refresh_enabled and self.current_jobid:
            self.run_worker(
                self._refresh_current_output(),
                group="output_refresh",
                exclusive=True,
                exit_on_error=False,
            )

    async def _refresh_current_output(self) -> None:
        jobid = self.current_jobid
        if not jobid:
            return
        try:
            stdout, stderr = await self.client.get_job_output(jobid)
        except Exception:
            return
        if self.current_jobid == jobid:
            self.query_one("#stdout_viewer", LogViewer).set_content(stdout)
            self.query_one("#stderr_viewer", LogViewer).set_content(stderr)

    async def refresh_data(self) -> None:
        """Fetch jobs and nodes from Slurm and redraw the tables."""
        self.status.message = "Refreshing…"
        try:
            self._jobs_raw, self._nodes_raw = await asyncio.gather(self.client.get_jobs(), self.client.get_nodes())
        except Exception as e:
            self.status.message = f"Error: {e}"
            self.notify(str(e), title="Refresh failed", severity="error", timeout=10)
            return
        self.last_refresh_time = datetime.datetime.now()
        self._render_tables()

    def _render_tables(self, force: bool = False) -> None:
        """Apply filters/sort to the cached data and update both tables in place."""
        jobs = self.filter.apply_jobs(self._jobs_raw)
        nodes = self.filter.apply_nodes(self._nodes_raw)
        self._jobs_shown, self._nodes_shown = len(jobs), len(nodes)
        self._populate_jobs(jobs, force=force)
        self._populate_nodes(nodes, force=force)
        self._apply_current_sort()
        self._set_status_summary()

    def _set_status_summary(self) -> None:
        when = self.last_refresh_time.strftime("%H:%M:%S") if self.last_refresh_time else "--:--:--"
        self.status.message = (
            f"Updated @ {when} | Jobs: {self._jobs_shown} | Nodes: {self._nodes_shown} | "
            f"Interval: {self.refresh_sec:.0f}s"
        )

    # ------------------------------------------------------------------ actions
    def action_refresh(self) -> None:
        self._schedule_refresh()

    def _active_tab(self) -> str | None:
        return self.query_one(TabbedContent).active

    def action_focus_search(self) -> None:
        """Focus the search input in the current tab."""
        if self._active_tab() == "tab_nodes":
            self.query_one("#node_search", Input).focus()
        else:
            self.query_one("#job_search", Input).focus()

    def action_focus_table(self) -> None:
        """Return focus to the table of the current tab (Escape from the search box)."""
        if self._active_tab() == "tab_nodes":
            self.query_one("#nodes_table", DataTable).focus()
        else:
            self.query_one("#jobs_table", DataTable).focus()

    def _selected_jobid(self) -> str | None:
        table = self.query_one("#jobs_table", DataTable)
        if not table.row_count:
            return None
        row = table.get_row_at(table.cursor_coordinate.row)
        return str(row[0]) if row else None

    async def action_show_output(self) -> None:
        """Open output files in an external pager (bat/less)."""
        jobid = self._selected_jobid()
        if jobid is None:
            self.notify("No job selected", severity="warning")
            return

        stdout_path, stderr_path = await self.client.get_job_output_paths(jobid)
        files = [f for f in dict.fromkeys([stdout_path, stderr_path]) if f and os.path.exists(f)]
        if not files:
            self.notify("Output files not found on disk", severity="warning")
            return

        pager = self._find_pager()
        files_str = " ".join(shlex.quote(f) for f in files)
        # Strip \r (tqdm progress bars), keep ANSI colours (-R), start at the end (+G).
        if "bat" in pager:
            shell_cmd = (
                f"cat {files_str} | sed 's/\\r//g' | {pager} --paging=always --style=plain --pager='less -R +G'"
            )
        else:
            shell_cmd = f"cat {files_str} | sed 's/\\r//g' | {pager} -R +G"

        with self.suspend():
            subprocess.run(shell_cmd, shell=True)

    @staticmethod
    def _find_pager() -> str:
        for candidate in ("bat", "batcat", "less"):
            if shutil.which(candidate):
                return candidate
        return os.environ.get("PAGER", "cat")

    def action_toggle_realtime(self) -> None:
        self.user_wants_realtime = not self.user_wants_realtime
        if self.user_wants_realtime:
            self.output_refresh_enabled = self.current_jobid is not None
            self.notify("Real-time output refresh: ON")
        else:
            self.output_refresh_enabled = False
            self.notify("Real-time output refresh: OFF")

    def action_goto_jobs(self) -> None:
        self.query_one(TabbedContent).active = "tab_jobs"
        self.query_one("#jobs_table", DataTable).focus()

    def action_goto_nodes(self) -> None:
        self.query_one(TabbedContent).active = "tab_nodes"
        self.query_one("#nodes_table", DataTable).focus()

    def action_cancel_job(self) -> None:
        """Cancel the selected job after confirmation."""
        jobid = self._selected_jobid()
        if jobid is None:
            self.notify("No job selected", severity="warning")
            return

        def on_confirm(confirmed: bool | None) -> None:
            if confirmed:
                self.run_worker(self._cancel_job(jobid), group="cancel", exit_on_error=False)
            else:
                self.notify("Cancellation aborted")

        self.push_screen(ConfirmModal(f"Cancel job {jobid}?"), on_confirm)

    async def _cancel_job(self, jobid: str) -> None:
        success, msg = await self.client.cancel_job(jobid)
        if success:
            self.notify(msg)
            self._schedule_refresh()
        else:
            self.notify(f"Failed to cancel job {jobid}: {msg}", severity="error", timeout=10)

    def action_copy_jobid(self) -> None:
        jobid = self._selected_jobid()
        if jobid is None:
            self.notify("No job selected", severity="warning")
            return
        self.copy_to_clipboard(jobid)
        self.notify(f"Copied job ID {jobid} to clipboard")

    def action_increase_refresh(self) -> None:
        self.refresh_sec = min(60.0, self.refresh_sec + 1.0)
        self._update_refresh_timer()
        self._set_status_summary()

    def action_decrease_refresh(self) -> None:
        self.refresh_sec = max(1.0, self.refresh_sec - 1.0)
        self._update_refresh_timer()
        self._set_status_summary()

    def action_toggle_theme(self) -> None:
        self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"
        self.query_one("#script_viewer", SyntaxViewer)._render_code()

    # ------------------------------------------------------------------ formatting
    def _format_state(self, state: str, is_node: bool = False) -> Text:
        colors = self.NODE_STATE_COLORS if is_node else self.JOB_STATE_COLORS
        base_state = state.rstrip("*+~#")  # e.g. "idle*", "RUNNING+"
        return Text(state, style=colors.get(base_state, "white"))

    def _format_time_with_ratio(self, time_used: str, time_limit: str) -> Text:
        ratio = self.client.calculate_time_ratio(time_used, time_limit)
        if ratio < 0:
            return Text(time_used)
        if ratio >= 0.95:
            return Text(time_used, style="bold red")
        if ratio >= 0.80:
            return Text(time_used, style="yellow")
        return Text(time_used, style="green")

    def _column_label(self, col: str) -> str:
        if self._sort_column == col:
            return f"{col} {'▼' if self._sort_reverse else '▲'}"
        return col

    # Regex for parsing GPU GRES strings
    _GPU_GRES_PATTERN = re.compile(r"\((?:IDX|S):[^)]*\)")

    def _parse_gpu_count(self, gres_str: str) -> int:
        """GPU count from GRES strings like gpu:h100:8, gpu:8(S:0-1), gpu:(null):8(IDX:0-7)."""
        if not gres_str or gres_str in ("(null)", "-", "N/A"):
            return 0
        clean = self._GPU_GRES_PATTERN.sub("", gres_str)
        for part in reversed(clean.split(":")):
            if part.isdigit():
                return int(part)
        return 0

    def _format_gpu_bar(self, gres: str, gres_used: str = "") -> Text:
        """Format GPU info as a visual progress bar."""
        total = self._parse_gpu_count(gres)
        if total == 0:
            return Text("-", style="dim")
        used = min(self._parse_gpu_count(gres_used), total)
        avail = total - used
        text = Text()
        if used > 0:
            text.append("█" * used, style="dark_orange")
        if avail > 0:
            text.append("░" * avail, style="grey50")
        text.append(f" {used}/{total}", style="cyan")
        return text

    def _format_cpu_usage(self, cpus_state: str) -> Text:
        """Format CPU usage from CPUsState field (Alloc/Idle/Other/Total)."""
        if not cpus_state:
            return Text("-", style="dim")
        parts = cpus_state.split("/")
        if len(parts) >= 4 and parts[0].isdigit() and parts[3].isdigit():
            return Text(f"{parts[0]}/{parts[3]}", style="cyan")
        return Text(cpus_state)

    def _format_mem_usage(self, alloc_mem: str, total_mem: str) -> Text:
        """Format memory usage as alloc/total in GB (sinfo reports MB)."""
        if not total_mem:
            return Text("-", style="dim")
        try:
            alloc_mb = int(alloc_mem) if alloc_mem else 0
            total_mb = int(total_mem)
        except ValueError:
            return Text(f"{alloc_mem}/{total_mem}" if alloc_mem else total_mem)
        if total_mb == 0:
            return Text("-", style="dim")
        return Text(f"{alloc_mb / 1024:.0f}/{total_mb / 1024:.0f}G", style="cyan")

    # ------------------------------------------------------------------ tables
    def _populate_jobs(self, jobs: list[dict[str, Any]], force: bool = False) -> None:
        table = self.query_one("#jobs_table", DataTable)
        if jobs and "TRES" in jobs[0]:
            columns: Sequence[str] = _JOB_COLUMNS_FULL
            rows: list[Row] = []
            for j in jobs:
                tres = j.get("TRES", "")
                time_used = j.get("TimeUsed", j.get("TIME", ""))
                time_limit = j.get("TimeLimit", "")
                jobid = j.get("JOBID", "")
                rows.append(
                    (
                        jobid,
                        (
                            jobid,
                            j.get("USERNAME", j.get("USER", "")),
                            self._format_state(j.get("STATE", "")),
                            j.get("PARTITION", ""),
                            self.client.extract_cpus_from_tres(tres),
                            self.client.extract_mem_from_tres(tres),
                            j.get("GPU_COUNT", "0"),
                            self._format_time_with_ratio(time_used, time_limit),
                            time_limit,
                            Text(j.get("NAME", "")[:30]),
                            j.get("ReqNodes", ""),
                            self.client.count_nodes_from_nodelist(j.get("NodeList", "")),
                            self.client.combine_nodelist_reason(j.get("NodeList", ""), j.get("Reason", "")),
                        ),
                    )
                )
        else:
            columns = _JOB_COLUMNS_BASIC
            rows = []
            for j in jobs:
                jobid = j.get("JOBID", "")
                rows.append(
                    (
                        jobid,
                        (
                            jobid,
                            j.get("USER", ""),
                            self._format_state(j.get("STATE", "")),
                            j.get("PARTITION", ""),
                            j.get("CPUS", ""),
                            j.get("MEM", ""),
                            j.get("TIME", ""),
                            Text(j.get("NAME", "")),
                            self.client.count_nodes_from_nodelist(j.get("NODELIST(REASON)", "")),
                            j.get("NODELIST(REASON)", ""),
                        ),
                    )
                )
        self._sync_table(table, columns, rows, force=force, sortable=True)

    def _populate_nodes(self, nodes: list[dict[str, Any]], force: bool = False) -> None:
        table = self.query_one("#nodes_table", DataTable)
        rows: list[Row] = []
        for n in nodes:
            node, partition = n.get("NODE", ""), n.get("PARTITION", "")
            rows.append(
                (
                    f"{node}|{partition}",  # sinfo -N lists a node once per partition
                    (
                        node,
                        self._format_state(n.get("STATE", ""), is_node=True),
                        n.get("AVAIL", ""),
                        self._format_gpu_bar(n.get("GRES", ""), n.get("GRES_USED", "")),
                        self._format_cpu_usage(n.get("CPUS_STATE", "")),
                        self._format_mem_usage(n.get("ALLOC_MEM", ""), n.get("MEM", "")),
                        partition,
                    ),
                )
            )
        self._sync_table(table, _NODE_COLUMNS, rows, force=force)

    @staticmethod
    def _cursor_row_key(table: DataTable) -> str | None:
        if not table.row_count:
            return None
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value

    @staticmethod
    def _restore_cursor(table: DataTable, row_key: str | None) -> None:
        if row_key is None or row_key not in table.rows:
            return
        index = table.get_row_index(row_key)
        if index != table.cursor_coordinate.row:
            table.move_cursor(row=index, scroll=False)

    def _sync_table(
        self, table: DataTable, columns: Sequence[str], rows: list[Row], *, force: bool = False, sortable: bool = False
    ) -> None:
        """Bring `table` in line with `rows` without rebuilding it.

        Updating cells in place (rather than clear + re-add) keeps the scroll
        offset and the selected row across periodic refreshes. A full rebuild
        happens only when the column set changes or `force` is set.
        """
        cursor_key = self._cursor_row_key(table)
        current_columns = [key.value for key in table.columns]
        if force or current_columns != list(columns):
            table.clear(columns=True)
            for col in columns:
                table.add_column(self._column_label(col) if sortable else col, key=col)
            for key, cells in rows:
                table.add_row(*cells, key=key)
            self._restore_cursor(table, cursor_key)
            return

        seen: set[str] = set()
        for key, cells in rows:
            seen.add(key)
            if key in table.rows:
                for col, value in zip(columns, cells, strict=True):
                    if table.get_cell(key, col) != value:
                        table.update_cell(key, col, value, update_width=True)
            else:
                table.add_row(*cells, key=key)
        for row_key in [k for k in table.rows if k.value not in seen]:
            table.remove_row(row_key)
        self._restore_cursor(table, cursor_key)

    # ------------------------------------------------------------------ sorting
    def _sort_key(self, value: Any) -> tuple:
        """Sort key for the active column: numeric for count/memory columns, text otherwise."""
        text = (value.plain if isinstance(value, Text) else str(value)).strip()
        col = self._sort_column

        if col in _INT_COLUMNS:
            return (0, int(text)) if text.isdigit() else (1, text.lower())

        if col in _MEM_COLUMNS:
            match = _MEM_PATTERN.match(text)
            if match:
                num_str, unit = match.groups()
                mult = _MEM_UNITS.get(unit.upper(), 1) if unit else 1
                return (0, int(float(num_str) * mult))
            return (1, text.lower())

        return (0, text.lower())

    def _apply_current_sort(self) -> None:
        if not self._sort_column:
            return
        table = self.query_one("#jobs_table", DataTable)
        if self._sort_column not in table.columns:
            return
        cursor_key = self._cursor_row_key(table)
        table.sort(self._sort_column, key=self._sort_key, reverse=self._sort_reverse)
        self._restore_cursor(table, cursor_key)

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Click a jobs-table header to sort by it; click again to flip direction."""
        if event.data_table.id != "jobs_table":
            return
        column_name = event.column_key.value
        if not column_name:
            return

        if self._sort_column == column_name:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column_name
            # Numeric columns start descending (largest first)
            self._sort_reverse = column_name in _INT_COLUMNS or column_name in _MEM_COLUMNS

        self._render_tables(force=True)  # rebuild so header labels carry the sort arrow

    # ------------------------------------------------------------------ selection
    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table_id = event.data_table.id
        if table_id == "nodes_table":
            self._handle_node_selected(event)
            return
        if table_id != "jobs_table" or event.row_key is None:
            return

        row = event.data_table.get_row(event.row_key)
        if not row:
            return
        jobid = str(row[0])
        state = row[2]
        state_str = state.plain if isinstance(state, Text) else str(state)
        can_refresh = state_str.upper() in ("RUNNING", "PENDING")

        self.current_jobid = jobid
        self.output_refresh_enabled = self.user_wants_realtime and can_refresh

        self.query_one("#job_detail", Static).update(Text.assemble((f"Job {jobid}", "bold"), "\nLoading..."))
        self.query_one("#script_viewer", SyntaxViewer).set_code("# Loading...", "bash")
        self.query_one("#stdout_viewer", LogViewer).set_content("Loading...")
        self.query_one("#stderr_viewer", LogViewer).set_content("Loading...")

        self.run_worker(
            self._load_job_details(jobid, can_refresh),
            group="job_details",
            exclusive=True,
            exit_on_error=False,
        )

    def _handle_node_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None:
            return
        row = event.data_table.get_row(event.row_key)
        if not row:
            return
        node_name = row[0].plain if isinstance(row[0], Text) else str(row[0])
        self.run_worker(self._fetch_and_show_node_jobs(node_name), group="node_jobs", exclusive=True)

    async def _fetch_and_show_node_jobs(self, node_name: str) -> None:
        node_jobs = await self.client.get_jobs_on_node(node_name)
        self.push_screen(NodeJobsModal(node_name, node_jobs))

    async def _load_job_details(self, jobid: str, can_refresh: bool) -> None:
        """Load job details, script, and output asynchronously."""
        try:
            detail, script_text = await asyncio.gather(
                self.client.get_job_detail(jobid),
                self.client.get_job_script(jobid),
            )
            if self.current_jobid != jobid:
                return

            self.query_one("#job_detail", Static).update(Text.assemble((f"Job {jobid}", "bold"), "\n", detail))
            self.query_one("#script_viewer", SyntaxViewer).set_code(script_text, "bash")

            stdout, stderr = await self.client.get_job_output(jobid, detail=detail)
            if self.current_jobid != jobid:
                return

            self.query_one("#stdout_viewer", LogViewer).set_content(stdout)
            self.query_one("#stderr_viewer", LogViewer).set_content(stderr)
        except Exception as e:
            if self.current_jobid == jobid:
                self.notify(f"Failed to load job {jobid}: {e}", severity="error", timeout=10)

    # ------------------------------------------------------------------ filters
    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter as you type; data is cached so no Slurm call is needed."""
        text = event.value.strip()
        if event.input.id == "job_search":
            self.filter.job_text = text
        elif event.input.id == "node_search":
            self.filter.node_text = text
        else:
            return
        self._render_tables()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in ("job_search", "node_search"):
            self.action_focus_table()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "state_filter":
            self.filter.state = str(event.value) if event.value else None
            self._render_tables()
