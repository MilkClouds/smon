"""Main Slurm Dashboard application."""

import asyncio
import contextlib
import datetime
from typing import Any, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static, TabbedContent, TabPane

from .modals import OutputModal, ScriptModal
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
        Binding("f", "filter_dialog", "Filter"),
        Binding("s", "show_script", "Script Modal"),
        Binding("o", "show_output", "Output Modal"),
        Binding("ctrl+r", "refresh_output", "Refresh Output"),
        Binding("t", "toggle_realtime", "Toggle Real-time", show=True),
        Binding("d", "debug_test", "Debug Test", show=False),
    ]

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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield self.status
        with TabbedContent():
            with TabPane("Jobs", id="tab_jobs"):
                with Horizontal(id="jobs_split", classes="split-container"):
                    # Left panel: Job list
                    with Vertical(id="jobs_list_pane", classes="list-pane"):
                        yield Input(placeholder="/ Search in jobs", id="job_search")
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

    async def on_mount(self) -> None:
        jobs_table: DataTable = self.query_one("#jobs_table", DataTable)
        jobs_table.cursor_type = "row"
        jobs_table.zebra_stripes = True
        jobs_table.focus()

        nodes_table: DataTable = self.query_one("#nodes_table", DataTable)
        nodes_table.cursor_type = "row"
        nodes_table.zebra_stripes = True

        await self.refresh_data()
        self.set_interval(self.refresh_sec, self._schedule_refresh)
        self.set_interval(2.0, self._schedule_output_refresh)

    def _schedule_refresh(self) -> None:
        self.run_worker(self.refresh_data(), group="refresh", exclusive=True, exit_on_error=False)

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

    async def action_filter_dialog(self) -> None:
        """Show filter status and provide quick filter options."""
        focused_widget = self.focused
        widget_info = f"{type(focused_widget).__name__}" if focused_widget else "None"

        filter_info = []
        if self.filter.user:
            filter_info.append(f"User: {self.filter.user}")
        if self.filter.partition:
            filter_info.append(f"Partition: {self.filter.partition}")
        if self.filter.state:
            filter_info.append(f"State: {self.filter.state}")
        if self.filter.text:
            filter_info.append(f"Text: {self.filter.text}")

        if filter_info:
            self.status.message = f"🔍 Active filters: {', '.join(filter_info)} (Focus: {widget_info})"
        else:
            self.status.message = f"🔍 No active filters. Use search '/' to filter (Focus: {widget_info})"

        await self.refresh_data()

    async def action_show_script(self) -> None:
        """Open script in a modal window."""
        table: DataTable = self.query_one("#jobs_table", DataTable)
        if not table.row_count or table.cursor_coordinate is None:
            self.status.message = "No job selected"
            return
        row = table.get_row_at(table.cursor_coordinate.row)
        if not row:
            return
        jobid = row[0]

        self.status.message = f"Loading script for job {jobid}..."
        script_text = await self.client.get_job_script(str(jobid))

        modal = ScriptModal(str(jobid), script_text)
        self.push_screen(modal)
        self.status.message = f"Script modal opened for job {jobid} (Press Escape to close)"

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

        self.status.message = f"Loading output for job {jobid}..."
        stdout, stderr = await self.client.get_job_output(str(jobid))

        modal = OutputModal(str(jobid), stdout, stderr, self.client)
        self.push_screen(modal)
        self.status.message = f"Output modal opened for job {jobid} (Press Escape to close, 'r' to refresh)"

    async def action_refresh_output(self) -> None:
        """Refresh the output in the existing Output tab."""
        table: DataTable = self.query_one("#jobs_table", DataTable)
        if not table.row_count or table.cursor_coordinate is None:
            self.status.message = "No job selected for output refresh"
            return
        row = table.get_row_at(table.cursor_coordinate.row)
        if not row:
            return
        jobid = row[0]

        self.status.message = f"Refreshing output for job {jobid}..."
        stdout, stderr = await self.client.get_job_output(str(jobid))

        refresh_time = datetime.datetime.now().strftime("%H:%M:%S")
        self.query_one("#stdout_viewer", LogViewer).set_content(stdout or "No stdout available")
        self.query_one("#stderr_viewer", LogViewer).set_content(stderr or "No stderr available")
        self.status.message = f"Output refreshed for job {jobid} at {refresh_time}"

    def action_toggle_realtime(self) -> None:
        """Toggle real-time output refresh."""
        self.user_wants_realtime = not self.user_wants_realtime
        toggle_state = "ON" if self.user_wants_realtime else "OFF"
        focused_widget = self.focused
        widget_info = f"{type(focused_widget).__name__}" if focused_widget else "None"
        self.status.message = f"🔄 Real-time toggle pressed! Setting to: {toggle_state} (Focus: {widget_info})"

        self._update_realtime_state()

    def _update_realtime_state(self) -> None:
        """Update real-time refresh state based on current job and user preference."""
        if not self.current_jobid:
            self.output_refresh_enabled = False
            self._update_realtime_status_message("no current job")
            return

        try:
            table: DataTable = self.query_one("#jobs_table", DataTable)
            if table.cursor_coordinate is None:
                self.output_refresh_enabled = False
                self._update_realtime_status_message("no job selected")
                return

            row = table.get_row_at(table.cursor_coordinate.row)
            if not row or len(row) <= 2:
                self.output_refresh_enabled = False
                self._update_realtime_status_message("no job data")
                return

            job_state = row[2]
            can_refresh = job_state.upper() in ["RUNNING", "PENDING"]
            self.output_refresh_enabled = self.user_wants_realtime and can_refresh

            if self.user_wants_realtime:
                if can_refresh:
                    final_msg = f"✅ Real-time refresh: ON (job is {job_state})"
                else:
                    final_msg = f"⚠️ Real-time refresh: ON but job is {job_state} (not active)"
            else:
                final_msg = "❌ Real-time refresh: OFF"

            self.status.message = final_msg
            self._update_output_info_realtime_status()

        except Exception as e:
            self.output_refresh_enabled = False
            self.status.message = f"❌ Real-time toggle error: {e}"

    def _update_realtime_status_message(self, reason: str) -> None:
        """Update status message for real-time state."""
        toggle_state = "ON" if self.user_wants_realtime else "OFF"
        self.status.message = f"⚠️ Real-time refresh: {toggle_state} ({reason})"

    def _update_output_info_realtime_status(self) -> None:
        """Update status bar with real-time refresh status."""
        if not self.current_jobid:
            return
        if self.user_wants_realtime and self.output_refresh_enabled:
            refresh_status = "🔄 Real-time ON"
        elif self.user_wants_realtime:
            refresh_status = "⏸️ Real-time ON (job not active)"
        else:
            refresh_status = "⏹️ Real-time OFF"
        self.status.message = f"Job {self.current_jobid} | {refresh_status}"

    def action_debug_test(self) -> None:
        """Debug action to test keybindings."""
        focused_widget = self.focused
        widget_info = f"{type(focused_widget).__name__}" if focused_widget else "None"
        self.status.message = f"🐛 DEBUG: Keybinding works! Focused widget: {widget_info}"

    async def refresh_data(self) -> None:
        """Refresh jobs and nodes data."""
        self.status.message = "Refreshing…"
        try:
            jobs, nodes = await asyncio.gather(self.client.get_jobs(), self.client.get_nodes())
            jobs_f = self.filter.apply_jobs(jobs)
            nodes_f = self.filter.apply_nodes(nodes)
            self._populate_jobs(jobs_f)
            self._populate_nodes(nodes_f)
            self.status.message = f"Updated. Jobs: {len(jobs_f)} | Nodes: {len(nodes_f)}"
        except Exception as e:
            self.status.message = f"Error: {e}"

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
            table.add_columns(*columns)
            for j in jobs:
                gpu_display = j.get("GPU_COUNT", "0")
                cpus = self.client.extract_cpus_from_tres(j.get("TRES", ""))
                mem = self.client.extract_mem_from_tres(j.get("TRES", ""))
                node_count = self.client.count_nodes_from_nodelist(j.get("NodeList", ""))
                nodelist_display = self.client.combine_nodelist_reason(j.get("NodeList", ""), j.get("Reason", ""))
                table.add_row(
                    j.get("JOBID", ""),
                    j.get("USERNAME", j.get("USER", "")),
                    j.get("STATE", ""),
                    j.get("PARTITION", ""),
                    cpus,
                    mem,
                    gpu_display,
                    j.get("TimeUsed", j.get("TIME", "")),
                    j.get("TimeLimit", ""),
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
            table.add_columns(*columns)
            for j in jobs:
                node_count = self.client.count_nodes_from_nodelist(j.get("NODELIST(REASON)", ""))
                table.add_row(
                    j.get("JOBID", ""),
                    j.get("USER", ""),
                    j.get("STATE", ""),
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

    def _populate_nodes(self, nodes: List[Dict[str, Any]]) -> None:
        """Populate the nodes table with data."""
        table: DataTable = self.query_one("#nodes_table", DataTable)
        table.clear(columns=True)

        columns = ["NODE", "STATE", "AVAIL", "GPUs", "CPUS", "MEM", "PARTITION"]
        table.add_columns(*columns)
        for n in nodes:
            gpu_display = self.client.parse_node_gpu_info(n.get("GRES", ""))
            table.add_row(
                n.get("NODE", ""),
                n.get("STATE", ""),
                n.get("AVAIL", ""),
                gpu_display,
                n.get("CPUS", ""),
                n.get("MEM", ""),
                n.get("PARTITION", ""),
            )

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in the jobs table."""
        try:
            if event.data_table.id != "jobs_table":
                return
            row_key = event.row_key
            if row_key is None:
                return
            row = event.data_table.get_row(row_key)
            if not row:
                return
            jobid = row[0]

            self.current_jobid = str(jobid)
            job_state = row[2]
            can_refresh = job_state.upper() in ["RUNNING", "PENDING"]
            self.output_refresh_enabled = self.user_wants_realtime and can_refresh

            detail = await self.client.get_job_detail(str(jobid))
            self.query_one("#job_detail", Static).update(f"[b]Job {jobid}[/b]\n{detail}")

            script_text = await self.client.get_job_script(str(jobid))
            self.query_one("#script_viewer", SyntaxViewer).set_code(script_text, "bash")

            stdout, stderr = await self.client.get_job_output(str(jobid))
            self._update_output_display(jobid, stdout, stderr, can_refresh)

        except Exception as e:
            self.status.message = f"Row select error: {e}"

    def _update_output_display(self, jobid: str, stdout: str, stderr: str, can_refresh: bool) -> None:
        """Update output display panels."""
        self.query_one("#stdout_viewer", LogViewer).set_content(stdout or "No stdout available")
        self.query_one("#stderr_viewer", LogViewer).set_content(stderr or "No stderr available")

        # Update status with refresh info
        if self.user_wants_realtime and can_refresh:
            self.status.message = f"Job {jobid} selected | 🔄 Real-time ON"
        else:
            self.status.message = f"Job {jobid} selected | Press 't' to enable real-time"

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission."""
        text = event.value.strip()
        if event.input.id in ("job_search", "node_search"):
            self.filter.text = text
            await self.refresh_data()
