"""Headless integration tests for the dashboard (mock mode)."""

from rich.text import Text
from textual.widgets import DataTable, Input
from textual.widgets._data_table import ColumnKey

from smon.app import SlurmDashboard
from smon.modals import ConfirmModal, NodeJobsModal
from smon.widgets import LogViewer


async def test_tables_populate_and_cursor_survives_refresh() -> None:
    app = SlurmDashboard(mock_mode=True, refresh_sec=0.2)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause(0.3)
        jobs = app.query_one("#jobs_table", DataTable)
        assert jobs.row_count == 3
        assert app.query_one("#nodes_table", DataTable).row_count == 2
        await pilot.press("down")
        await pilot.pause(0.5)  # at least one periodic refresh
        assert jobs.cursor_coordinate.row == 1


async def test_select_job_loads_details() -> None:
    app = SlurmDashboard(mock_mode=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert app.current_jobid == "12345"
        assert app.query_one("#stdout_viewer", LogViewer).lines


async def test_live_search_and_escape() -> None:
    app = SlurmDashboard(mock_mode=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause(0.3)
        jobs = app.query_one("#jobs_table", DataTable)
        await pilot.press("/", *"bert")
        await pilot.pause(0.2)
        assert jobs.row_count == 1
        await pilot.press("escape")
        assert app.focused is jobs
        app.query_one("#job_search", Input).value = ""
        await pilot.pause(0.2)
        assert jobs.row_count == 3


async def test_sort_persists_across_refresh() -> None:
    app = SlurmDashboard(mock_mode=True, refresh_sec=0.2)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause(0.3)
        jobs = app.query_one("#jobs_table", DataTable)
        app.on_data_table_header_selected(DataTable.HeaderSelected(jobs, ColumnKey("GPUs"), 6, Text("GPUs")))
        await pilot.pause(0.5)
        assert [jobs.get_row_at(i)[6] for i in range(jobs.row_count)] == ["4", "2", "0"]
        assert str(jobs.columns[ColumnKey("GPUs")].label) == "GPUs ▼"


async def test_cancel_confirmation_modal() -> None:
    app = SlurmDashboard(mock_mode=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("c")
        assert isinstance(app.screen, ConfirmModal)
        await pilot.press("n")
        await pilot.pause(0.1)
        assert not isinstance(app.screen, ConfirmModal)


async def test_node_jobs_modal() -> None:
    app = SlurmDashboard(mock_mode=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("2", "enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, NodeJobsModal)
