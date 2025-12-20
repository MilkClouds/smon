"""Main Slurm Dashboard application."""

import asyncio
import contextlib
import datetime
import subprocess
from typing import Any, Dict, List, Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Select, Static, TabbedContent, TabPane

from .modals import OutputModal
from .slurm_client import SlurmClient
from .styles import APP_CSS
from .widgets import Filter, LogViewer, StatusBar, SyntaxViewer


class SlurmDashboard(App):
    """Slurm Dashboard application for monitoring jobs and nodes."""

    CSS = APP_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "focus_search", "Search"),
        Binding("o", "show_output", "Output Modal"),
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

    def __init__(
        self,
        *,
        refresh_sec: float = 5.0,
        user: Optional[str] = None,
        partition: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.refresh_sec = refresh_sec
        self.client = SlurmClient()
        self.filter = Filter()
        self.filter.user = user
        self.filter.partition = partition
        self.status = StatusBar(classes="bar")
        self.current_jobid: Optional[str] = None
        self.output_refresh_enabled = False
        self.user_wants_realtime = True
        self.last_refresh_time: Optional[datetime.datetime] = None
        self._pending_cancel_jobid: Optional[str] = None
        self._sort_column: Optional[str] = None
        self._sort_reverse: bool = False

    # State filter options
    STATE_OPTIONS = [
        ("All States", ""),
        ("Running", "RUNNING"),
        ("Pending", "PENDING"),
        ("Completed", "COMPLETED"),
        ("Failed", "FAILED"),
        ("Cancelled", "CANCELLED"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield self.status
        with TabbedContent():
            with TabPane("Jobs", id="tab_jobs"):
                with Horizontal(id="jobs_split", classes="split-container"):
                    # Left panel: Job list
                    with Vertical(id="jobs_list_pane", classes="list-pane"):
                        with Horizontal(classes="filter-bar"):
                            yield Input(placeholder="/ Search", id="job_search", classes="search-input")
                            yield Select(
                                self.STATE_OPTIONS,
                                value="",
                                id="state_filter",
                                classes="state-select",
                            )
                        with ScrollableContainer(id="jobs_table_container", classes="table-container"):
                            yield DataTable(id="jobs_table")
                    # Right panel: Job details + Script + Output
                    with Vertical(id="jobs_detail_pane", classes="detail-pane"):
                        # Job detail section
                        with ScrollableContainer(id="job_detail_container", classes="detail-section"):
                            yield Static("Select a job to see details.", id="job_detail")
                        # Script section
                        with Vertical(id="script_section", classes="script-section"):
                            yield Static("[bold cyan]📄 Script[/bold cyan]", classes="section-header")
                            with ScrollableContainer(classes="script-scroll"):
                                yield SyntaxViewer("Select a job to view script", id="script_viewer")
                        # Output section (STDOUT + STDERR side by side)
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
                with Vertical(id="nodes_pane", classes="pane"):
                    yield Input(placeholder="/ Search in nodes", id="node_search")
                    with ScrollableContainer(id="nodes_table_container", classes="table-container"):
                        yield DataTable(id="nodes_table")
        yield Footer()

    async def on_key(self, event) -> None:
        """Handle key events for cancel confirmation."""
        if self._pending_cancel_jobid is not None:
            if event.key == "c":
                # Confirm cancellation
                jobid = self._pending_cancel_jobid
                self._pending_cancel_jobid = None
                success, msg = await self.client.cancel_job(jobid)
                if success:
                    self.status.message = f"✅ {msg}"
                    await self.refresh_data()
                else:
                    self.status.message = f"❌ Failed to cancel job {jobid}: {msg}"
            else:
                # Abort cancellation
                self._pending_cancel_jobid = None
                self.status.message = "Cancellation aborted"
            event.stop()

    async def on_mount(self) -> None:
        jobs_table: DataTable = self.query_one("#jobs_table", DataTable)
        jobs_table.cursor_type = "row"
        jobs_table.zebra_stripes = True
        jobs_table.focus()

        nodes_table: DataTable = self.query_one("#nodes_table", DataTable)
        nodes_table.cursor_type = "row"
        nodes_table.zebra_stripes = True

        await self.refresh_data()
        self._refresh_timer = self.set_interval(self.refresh_sec, self._schedule_refresh)
        self.set_interval(5.0, self._schedule_output_refresh)  # Output refresh every 5s

    def _schedule_refresh(self) -> None:
        self.run_worker(self.refresh_data(), group="refresh", exclusive=True, exit_on_error=False)

    def _update_refresh_timer(self) -> None:
        """Update refresh timer with new interval."""
        if hasattr(self, "_refresh_timer") and self._refresh_timer:
            self._refresh_timer.stop()
        self._refresh_timer = self.set_interval(self.refresh_sec, self._schedule_refresh)

    def _schedule_output_refresh(self) -> None:
        """Schedule output refresh for the currently selected job."""
        if self.output_refresh_enabled and self.current_jobid:
            self.run_worker(
                self._refresh_current_output(),
                group="output_refresh",
                exclusive=True,
                exit_on_error=False,
            )

    async def _refresh_current_output(self) -> None:
        """Refresh output for the currently selected job."""
        if not self.current_jobid:
            return
        try:
            stdout, stderr = await self.client.get_job_output(self.current_jobid)
            self.query_one("#stdout_viewer", LogViewer).set_content(stdout or "No stdout available")
            self.query_one("#stderr_viewer", LogViewer).set_content(stderr or "No stderr available")
        except Exception:
            pass

    async def action_refresh(self) -> None:
        await self.refresh_data()

    def action_focus_search(self) -> None:
        """Focus the search input in the current tab."""
        try:
            tabbed_content = self.query_one("TabbedContent")
            active_tab = getattr(tabbed_content, "active", None)

            if active_tab == "tab_jobs":
                self.query_one("#job_search", Input).focus()
                self.status.message = "Search jobs (press Enter to apply filter)"
            elif active_tab == "tab_nodes":
                self.query_one("#node_search", Input).focus()
                self.status.message = "Search nodes (press Enter to apply filter)"
            else:
                self.status.message = "Search not available in this tab"
        except Exception as e:
            self.status.message = f"Search focus error: {e}"

    async def action_show_output(self) -> None:
        """Open output in a modal window."""
        table: DataTable = self.query_one("#jobs_table", DataTable)
        if not table.row_count or table.cursor_coordinate is None:
            self.status.message = "No job selected"
            return
        row = table.get_row_at(table.cursor_coordinate.row)
        if not row:
            return
        jobid = row[0]

        self.status.message = f"Loading full output for job {jobid}..."
        stdout, stderr = await self.client.get_job_output(str(jobid), full=True)

        modal = OutputModal(str(jobid), stdout, stderr, self.client)
        self.push_screen(modal)
        self.status.message = f"Output modal opened for job {jobid} (Esc to close, 'r' to refresh)"

    def action_toggle_realtime(self) -> None:
        """Toggle real-time output refresh."""
        self.user_wants_realtime = not self.user_wants_realtime
        if self.user_wants_realtime:
            self.output_refresh_enabled = self.current_jobid is not None
            self.status.message = "🔄 Real-time refresh: ON"
        else:
            self.output_refresh_enabled = False
            self.status.message = "⏹️ Real-time refresh: OFF"

    def action_goto_jobs(self) -> None:
        """Switch to Jobs tab."""
        try:
            tabbed_content = self.query_one("TabbedContent", TabbedContent)
            tabbed_content.active = "tab_jobs"
            self.status.message = "Switched to Jobs tab"
        except Exception:
            pass

    def action_goto_nodes(self) -> None:
        """Switch to Nodes tab."""
        try:
            tabbed_content = self.query_one("TabbedContent", TabbedContent)
            tabbed_content.active = "tab_nodes"
            self.status.message = "Switched to Nodes tab"
        except Exception:
            pass

    async def action_cancel_job(self) -> None:
        """Cancel the selected job."""
        table: DataTable = self.query_one("#jobs_table", DataTable)
        if not table.row_count or table.cursor_coordinate is None:
            self.status.message = "No job selected"
            return

        row_idx = table.cursor_coordinate.row
        row_data = table.get_row_at(row_idx)
        jobid = row_data[0] if row_data else None
        if not jobid:
            self.status.message = "Could not get job ID"
            return

        # Confirm cancellation
        self.status.message = f"⚠️ Cancel job {jobid}? Press 'c' again to confirm, any other key to abort"
        self._pending_cancel_jobid = str(jobid)

    def action_copy_jobid(self) -> None:
        """Copy selected job ID to clipboard."""
        table: DataTable = self.query_one("#jobs_table", DataTable)
        if not table.row_count or table.cursor_coordinate is None:
            self.status.message = "No job selected"
            return

        row_idx = table.cursor_coordinate.row
        row_data = table.get_row_at(row_idx)
        jobid = row_data[0] if row_data else None
        if not jobid:
            self.status.message = "Could not get job ID"
            return

        try:
            # Try using xclip, xsel, or pbcopy
            jobid_str = str(jobid)
            for cmd in ["xclip -selection clipboard", "xsel --clipboard --input", "pbcopy"]:
                try:
                    process = subprocess.Popen(
                        cmd.split(),
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    process.communicate(input=jobid_str.encode())
                    if process.returncode == 0:
                        self.status.message = f"📋 Copied job ID: {jobid}"
                        return
                except FileNotFoundError:
                    continue
            self.status.message = f"📋 Job ID: {jobid} (clipboard not available)"
        except Exception as e:
            self.status.message = f"Copy error: {e}"

    def action_increase_refresh(self) -> None:
        """Increase refresh interval by 1 second."""
        self.refresh_sec = min(60.0, self.refresh_sec + 1.0)
        self._update_refresh_timer()
        self.status.message = f"Refresh interval: {self.refresh_sec:.0f}s"

    def action_decrease_refresh(self) -> None:
        """Decrease refresh interval by 1 second."""
        self.refresh_sec = max(1.0, self.refresh_sec - 1.0)
        self._update_refresh_timer()
        self.status.message = f"Refresh interval: {self.refresh_sec:.0f}s"

    def action_toggle_theme(self) -> None:
        """Toggle between dark and light themes."""
        self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"
        theme_name = "light" if self.theme == "textual-light" else "dark"
        self.status.message = f"Theme: {theme_name}"
        # Update syntax viewer theme
        try:
            self.query_one("#script_viewer", SyntaxViewer)._render_code()
        except Exception:
            pass

    async def refresh_data(self) -> None:
        """Refresh jobs and nodes data."""
        self.status.message = "Refreshing…"
        try:
            jobs, nodes = await asyncio.gather(self.client.get_jobs(), self.client.get_nodes())
            jobs_f = self.filter.apply_jobs(jobs)
            nodes_f = self.filter.apply_nodes(nodes)
            self._populate_jobs(jobs_f)
            self._populate_nodes(nodes_f)
            # Re-apply sorting if active
            if self._sort_column:
                self._apply_current_sort()
            self.last_refresh_time = datetime.datetime.now()
            refresh_time = self.last_refresh_time.strftime("%H:%M:%S")
            self.status.message = f"Updated @ {refresh_time} | Jobs: {len(jobs_f)} | Nodes: {len(nodes_f)} | Interval: {self.refresh_sec:.0f}s"
        except Exception as e:
            self.status.message = f"Error: {e}"

    def _format_state(self, state: str, is_node: bool = False) -> Text:
        """Format state with color."""
        colors = self.NODE_STATE_COLORS if is_node else self.JOB_STATE_COLORS
        # Handle states like "idle*" or "RUNNING+"
        base_state = state.rstrip("*+~#")
        color = colors.get(base_state, "white")
        return Text(state, style=color)

    def _format_time_with_ratio(self, time_used: str, time_limit: str) -> Text:
        """Format time used with color based on ratio to limit."""
        ratio = self.client.calculate_time_ratio(time_used, time_limit)
        if ratio < 0:
            return Text(time_used)
        elif ratio >= 0.95:
            return Text(time_used, style="bold red")
        elif ratio >= 0.80:
            return Text(time_used, style="yellow")
        else:
            return Text(time_used, style="green")

    def _get_column_label(self, col: str) -> str:
        """Get column label with sort indicator if applicable."""
        if self._sort_column == col:
            arrow = "▼" if self._sort_reverse else "▲"
            return f"{col} {arrow}"
        return col

    def _apply_current_sort(self) -> None:
        """Apply current sort to jobs table."""
        if not self._sort_column:
            return
        try:
            table = self.query_one("#jobs_table", DataTable)
            table.sort(self._sort_column, key=self._sort_key, reverse=self._sort_reverse)
        except Exception:
            pass

    def _populate_jobs(self, jobs: List[Dict[str, Any]]) -> None:
        """Populate the jobs table with data."""
        table: DataTable = self.query_one("#jobs_table", DataTable)

        saved_cursor_row = None
        if table.cursor_coordinate is not None:
            saved_cursor_row = table.cursor_coordinate.row

        table.clear(columns=True)

        if jobs and "TRES" in jobs[0]:
            columns = [
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
            ]
            # Add columns with sort indicator
            for col in columns:
                table.add_column(self._get_column_label(col), key=col)
            for j in jobs:
                gpu_display = j.get("GPU_COUNT", "0")
                cpus = self.client.extract_cpus_from_tres(j.get("TRES", ""))
                mem = self.client.extract_mem_from_tres(j.get("TRES", ""))
                node_count = self.client.count_nodes_from_nodelist(j.get("NodeList", ""))
                nodelist_display = self.client.combine_nodelist_reason(j.get("NodeList", ""), j.get("Reason", ""))
                state = j.get("STATE", "")
                time_used = j.get("TimeUsed", j.get("TIME", ""))
                time_limit = j.get("TimeLimit", "")
                table.add_row(
                    j.get("JOBID", ""),
                    j.get("USERNAME", j.get("USER", "")),
                    self._format_state(state),
                    j.get("PARTITION", ""),
                    cpus,
                    mem,
                    gpu_display,
                    self._format_time_with_ratio(time_used, time_limit),
                    time_limit,
                    j.get("NAME", "")[:30],
                    j.get("ReqNodes", ""),
                    node_count,
                    nodelist_display,
                )
        else:
            columns = [
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
            ]
            for col in columns:
                table.add_column(self._get_column_label(col), key=col)
            for j in jobs:
                state = j.get("STATE", "")
                node_count = self.client.count_nodes_from_nodelist(j.get("NODELIST(REASON)", ""))
                table.add_row(
                    j.get("JOBID", ""),
                    j.get("USER", ""),
                    self._format_state(state),
                    j.get("PARTITION", ""),
                    j.get("CPUS", ""),
                    j.get("MEM", ""),
                    j.get("TIME", ""),
                    j.get("NAME", ""),
                    node_count,
                    j.get("NODELIST(REASON)", ""),
                )

        if table.row_count:
            with contextlib.suppress(Exception):
                if saved_cursor_row is not None and saved_cursor_row < table.row_count:
                    table.move_cursor(row=saved_cursor_row)
                elif table.cursor_coordinate is None:
                    table.move_cursor(row=0)

    def _parse_gpu_count(self, gres_str: str) -> int:
        """Parse GPU count from GRES string. Handles formats like:
        - gpu:h100:8
        - gpu:8
        - gpu:h100:4(IDX:0-3)
        """
        if not gres_str or gres_str in ("(null)", "-", "N/A"):
            return 0
        try:
            # Remove parenthetical info like (IDX:0-3)
            clean = gres_str.split("(")[0]
            parts = clean.split(":")
            # Find the last numeric part
            for part in reversed(parts):
                if part.isdigit():
                    return int(part)
        except (ValueError, IndexError):
            pass
        return 0

    def _format_gpu_bar(self, gres: str, gres_used: str = "") -> Text:
        """Format GPU info as a visual progress bar."""
        gpu_info = self.client.parse_node_gpu_info(gres)
        if not gpu_info or gpu_info == "-":
            return Text("-", style="dim")

        total = self._parse_gpu_count(gres)
        used = self._parse_gpu_count(gres_used)

        if total == 0:
            return Text(gpu_info)

        # If GRES_USED is not available (null), show total only with all green
        if gres_used in ("(null)", "", "-", "N/A") or used == 0:
            bar = "░" * total
            text = Text()
            text.append(bar, style="green")
            text.append(f" {total}", style="cyan")
            return text

        # Ensure used doesn't exceed total
        used = min(used, total)
        avail = total - used

        # Create visual bar
        bar_used = "█" * used
        bar_avail = "░" * avail
        text = Text()
        text.append(bar_used, style="red")
        text.append(bar_avail, style="green")
        text.append(f" {used}/{total}", style="cyan")
        return text

    def _populate_nodes(self, nodes: List[Dict[str, Any]]) -> None:
        """Populate the nodes table with data."""
        table: DataTable = self.query_one("#nodes_table", DataTable)
        table.clear(columns=True)

        columns = ["NODE", "STATE", "AVAIL", "GPUs", "CPUS", "MEM", "PARTITION"]
        table.add_columns(*columns)
        for n in nodes:
            state = n.get("STATE", "")
            gpu_display = self._format_gpu_bar(n.get("GRES", ""), n.get("GRES_USED", ""))
            table.add_row(
                n.get("NODE", ""),
                self._format_state(state, is_node=True),
                n.get("AVAIL", ""),
                gpu_display,
                n.get("CPUS", ""),
                n.get("MEM", ""),
                n.get("PARTITION", ""),
            )

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in the jobs table."""
        if event.data_table.id != "jobs_table":
            return
        row_key = event.row_key
        if row_key is None:
            return
        row = event.data_table.get_row(row_key)
        if not row:
            return
        jobid = str(row[0])

        self.current_jobid = jobid
        job_state = row[2]
        # Handle both plain string and Rich Text objects
        state_str = job_state.plain if hasattr(job_state, "plain") else str(job_state)
        can_refresh = state_str.upper() in ["RUNNING", "PENDING"]
        self.output_refresh_enabled = self.user_wants_realtime and can_refresh

        # Show loading indicators immediately
        self.query_one("#job_detail", Static).update(f"[b]Job {jobid}[/b]\nLoading...")
        self.query_one("#script_viewer", SyntaxViewer).set_code("# Loading...", "bash")
        self.query_one("#stdout_viewer", LogViewer).set_content("Loading...")
        self.query_one("#stderr_viewer", LogViewer).set_content("Loading...")

        # Load data asynchronously using worker (exclusive to cancel previous loads)
        self.run_worker(
            self._load_job_details(jobid, can_refresh),
            group="job_details",
            exclusive=True,
            exit_on_error=False,
        )

    async def _load_job_details(self, jobid: str, can_refresh: bool) -> None:
        """Load job details, script, and output asynchronously."""
        try:
            # Load detail and script in parallel first
            detail, script_text = await asyncio.gather(
                self.client.get_job_detail(jobid),
                self.client.get_job_script(jobid),
            )

            # Check if still relevant before continuing
            if self.current_jobid != jobid:
                return

            # Update detail and script immediately
            self.query_one("#job_detail", Static).update(f"[b]Job {jobid}[/b]\n{detail}")
            self.query_one("#script_viewer", SyntaxViewer).set_code(script_text, "bash")

            # Load output using the already-fetched detail (avoids duplicate scontrol call)
            stdout, stderr = await self.client.get_job_output(jobid, detail=detail)

            if self.current_jobid != jobid:
                return

            self._update_output_display(jobid, stdout, stderr, can_refresh)

        except Exception as e:
            if self.current_jobid == jobid:
                self.status.message = f"Load error: {e}"

    def _update_output_display(self, jobid: str, stdout: str, stderr: str, can_refresh: bool) -> None:
        """Update output display panels."""
        self.query_one("#stdout_viewer", LogViewer).set_content(stdout or "No stdout available")
        self.query_one("#stderr_viewer", LogViewer).set_content(stderr or "No stderr available")

        # Update status with refresh info
        if self.user_wants_realtime and can_refresh:
            self.status.message = f"Job {jobid} selected | 🔄 Real-time ON"
        else:
            self.status.message = f"Job {jobid} selected | Press 't' to enable real-time"

    def _sort_key(self, value: Any) -> str:
        """Extract sortable string from a cell value (handles Rich Text)."""
        if hasattr(value, "plain"):
            return value.plain.lower()
        return str(value).lower()

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Handle header click for sorting."""
        if event.data_table.id != "jobs_table":
            return

        column_key = event.column_key
        # Extract actual column name from ColumnKey object
        column_name = column_key.value if hasattr(column_key, "value") else str(column_key)

        # Toggle sort direction if same column
        if self._sort_column == column_name:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column_name
            self._sort_reverse = False

        # Sort the table
        table = event.data_table
        try:
            table.sort(column_key, key=self._sort_key, reverse=self._sort_reverse)
            self._update_column_headers(table)
            arrow = "▼" if self._sort_reverse else "▲"
            self.status.message = f"Sorted by {column_name} {arrow}"
        except Exception as e:
            self.status.message = f"Sort error: {e}"

    def _update_column_headers(self, table: DataTable) -> None:
        """Update column headers to reflect current sort state."""
        for col_key in table.columns:
            col = table.columns[col_key]
            # Extract actual column name from ColumnKey object
            base_name = col_key.value if hasattr(col_key, "value") else str(col_key)
            if base_name is None:
                continue
            if self._sort_column == base_name:
                arrow = "▼" if self._sort_reverse else "▲"
                col.label = Text(f"{base_name} {arrow}")
            else:
                col.label = Text(base_name)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission."""
        text = event.value.strip()
        if event.input.id in ("job_search", "node_search"):
            self.filter.text = text
            await self.refresh_data()

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Handle state filter selection change."""
        if event.select.id == "state_filter":
            value = event.value
            self.filter.state = str(value) if value else None
            await self.refresh_data()
