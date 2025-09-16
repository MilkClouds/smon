#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "textual",
#     "rich",
# ]
# ///
"""
Slurm Dashboard (Textual) - DGX H100 Cluster Edition

Terminal UI for monitoring Slurm queues and nodes using Textual.
Optimized for DGX H100 clusters with intuitive GPU usage display.

Features:
- Job and node monitoring with real-time updates
- Intuitive GPU usage display (e.g., "4×H100", "2×A100")
- Uses squeue_ alias format for comprehensive job information
- Modal windows for script and output viewing (press 's'/'o', close with Escape)
- Script viewing with bash syntax highlighting in modal windows
- Real-time stdout/stderr tracking with refresh capability in modals
- Enhanced UI with multiple tabs for better organization
- Keyboard shortcuts for quick navigation

GPU Display:
- Jobs table shows GPU count clearly (GPUs column shows just the number)
- Nodes table shows available GPU count per node
- Partition indicates GPU type (a100/h100), so no need to show type in GPU column
- Clean display: "4" instead of "4×H100" since partition already indicates type

Updates:
- Enhanced squeue format matching squeue_ alias
- Added intuitive GPU count and type parsing
- Added dedicated Script tab with syntax highlighting
- Added Output tab with real-time stdout/stderr tracking
- Improved job selection with auto-loading of script and output
- Added toggle for real-time output refresh (press 't')
- Enhanced keybindings: 's' (script), 'o' (output), 't' (toggle real-time)
"""

import argparse
import asyncio
import contextlib
import os
import shlex
import signal
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.syntax import Syntax
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, Static, TabbedContent, TabPane

# ------------------------------ Utilities ------------------------------


def which(cmd: str) -> Optional[str]:
    for path in os.environ.get("PATH", "").split(os.pathsep):
        full = os.path.join(path, cmd)
        if os.path.isfile(full) and os.access(full, os.X_OK):
            return full
    return None


async def run_cmd(cmd: str, timeout: float = 10.0) -> Tuple[int, str, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        executable=os.environ.get("SHELL", "/bin/bash"),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.send_signal(signal.SIGINT)
        return 124, "", f"Timeout after {timeout}s for: {cmd}"
    return proc.returncode or 0, stdout.decode(errors="ignore"), stderr.decode(errors="ignore")


# ------------------------------ Slurm client ------------------------------


@dataclass
class SlurmCommands:
    squeue: str = "squeue"
    sinfo: str = "sinfo"
    scontrol: str = "scontrol"


class SlurmClient:
    def __init__(self, cmds: Optional[SlurmCommands] = None) -> None:
        self.cmds = cmds or SlurmCommands()
        for name in ("squeue", "sinfo", "scontrol"):
            found = which(getattr(self.cmds, name))
            if found:
                setattr(self.cmds, name, shlex.quote(found))

    async def get_jobs(self) -> List[Dict[str, Any]]:
        if not which("squeue"):
            return self._mock_jobs()

        # Use the enhanced format similar to squeue_ alias for better GPU visibility
        cols = [
            "JOBID",
            "PARTITION",
            "NAME",
            "USERNAME",
            "STATE",
            "TRES",
            "TimeUsed",
            "TimeLimit",
            "ReqNodes",
            "NodeList",
            "Reason",
        ]

        # Enhanced format string matching the squeue_ alias with Reason field
        fmt = "JobID:10,Partition:12,NAME:36,USERNAME:10,STATE:10,TRES:50,TimeUsed:12,TimeLimit:14,ReqNodes,NodeList,Reason"

        rc, out, err = await run_cmd(f"{self.cmds.squeue} -h -O '{fmt}' --states=all", timeout=10)
        if rc != 0:
            # Fallback to basic format if enhanced format fails
            basic_fmt = "%i|%u|%T|%M|%D|%P|%j|%R|%C|%m"
            basic_cols = [
                "JOBID",
                "USER",
                "STATE",
                "TIME",
                "NODES",
                "PARTITION",
                "NAME",
                "NODELIST(REASON)",
                "CPUS",
                "MEM",
            ]
            rc, out, err = await run_cmd(f"{self.cmds.squeue} -h -o '{basic_fmt}' --states=all", timeout=10)
            if rc != 0:
                raise RuntimeError(f"squeue failed: {err.strip() or 'unknown error'}")
            cols = basic_cols

        jobs: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if not line.strip():
                continue

            # Parse the output - squeue -O uses space-separated fields with fixed widths
            if "TRES" in cols:
                # Parse fixed-width format from squeue -O
                parts = self._parse_squeue_output_line(line)
            else:
                # Parse pipe-separated format from basic squeue -o
                parts = [p.strip() for p in line.split("|")]

            if len(parts) < len(cols) - 2:  # Allow some missing fields
                continue

            row = {k: parts[i] if i < len(parts) else "" for i, k in enumerate(cols)}

            # Parse and enhance GPU information from TRES field
            if "TRES" in row:
                row["GPU_COUNT"] = self._parse_gpu_count(row["TRES"])
                row["GPU_TYPE"] = self._parse_gpu_type(row["TRES"])
            else:
                row["GPU_COUNT"] = ""
                row["GPU_TYPE"] = ""

            jobs.append(row)
        return jobs

    async def get_nodes(self) -> List[Dict[str, Any]]:
        if not which("sinfo"):
            return self._mock_nodes()
        cols_primary = ["NODE", "PARTITION", "STATE", "AVAIL", "CPUS", "MEM", "S:C:T", "GRES"]
        cols_fallback = ["NODE", "PARTITION", "STATE", "AVAIL", "CPUS", "MEM", "GRES"]
        cmd_primary = f"{self.cmds.sinfo} -N -h -o '%N|%P|%t|%a|%c|%m|%O|%G'"
        cmd_fallback = f"{self.cmds.sinfo} -N -h -o '%N|%P|%t|%a|%c|%m|%G'"
        rc, out, err = await run_cmd(cmd_primary, timeout=10)
        cols = cols_primary
        if rc != 0:
            rc, out, err = await run_cmd(cmd_fallback, timeout=10)
            cols = cols_fallback
        if rc != 0:
            raise RuntimeError(f"sinfo failed: {err.strip() or 'unknown error'}")
        nodes: List[Dict[str, Any]] = []
        for line in out.splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != len(cols):
                continue
            nodes.append({k: v for k, v in zip(cols, parts)})
        return nodes

    async def get_job_detail(self, jobid: str) -> str:
        if not which("scontrol"):
            return f"Mock details for Job {jobid}\nUser=alice State=RUNNING Nodes=1 CPUS=8 Mem=16G StartTime=now"
        cmd = f"{self.cmds.scontrol} show job {shlex.quote(jobid)}"
        rc, out, err = await run_cmd(cmd, timeout=10)
        if rc != 0:
            return f"Failed to get job detail: {err.strip() or 'unknown error'}"
        return out.strip()

    async def get_job_script(self, jobid: str) -> str:
        if not which("scontrol"):
            return "Slurm scontrol not available; cannot fetch job script."
        cmd_stdout = f"{self.cmds.scontrol} write batch_script {shlex.quote(jobid)} -"
        rc, out, _err = await run_cmd(cmd_stdout, timeout=15)
        if rc == 0 and out.strip():
            return out.rstrip()
        return "(No script stored by controller)"

    async def get_job_output(self, jobid: str) -> Tuple[str, str]:
        """Get stdout and stderr for a job."""
        if not which("scontrol"):
            return "Mock stdout output for testing", "Mock stderr output for testing"

        # Get job details to find output files
        detail = await self.get_job_detail(jobid)
        stdout_file = ""
        stderr_file = ""

        # Parse output file paths from job details
        for line in detail.split("\n"):
            if "StdOut=" in line:
                stdout_file = line.split("StdOut=")[1].split()[0]
            elif "StdErr=" in line:
                stderr_file = line.split("StdErr=")[1].split()[0]

        stdout_content = ""
        stderr_content = ""

        # Read stdout file if it exists
        if stdout_file and stdout_file != "/dev/null":
            try:
                rc, out, err = await run_cmd(f"tail -n 100 {shlex.quote(stdout_file)}", timeout=5)
                if rc == 0:
                    stdout_content = out
                else:
                    stdout_content = f"Could not read stdout file: {err}"
            except Exception as e:
                stdout_content = f"Error reading stdout: {e}"

        # Read stderr file if it exists
        if stderr_file and stderr_file != "/dev/null":
            try:
                rc, out, err = await run_cmd(f"tail -n 100 {shlex.quote(stderr_file)}", timeout=5)
                if rc == 0:
                    stderr_content = out
                else:
                    stderr_content = f"Could not read stderr file: {err}"
            except Exception as e:
                stderr_content = f"Error reading stderr: {e}"

        return stdout_content, stderr_content

    def _parse_squeue_output_line(self, line: str) -> List[str]:
        """Parse fixed-width squeue -O output line into fields."""
        # Field widths based on the format: JobID:10,Partition:12,NAME:36,USERNAME:10,STATE:10,TRES:50,TimeUsed:12,TimeLimit:14,ReqNodes,NodeList,Reason
        widths = [10, 12, 36, 10, 10, 50, 12, 14]  # ReqNodes, NodeList, and Reason are variable width

        parts = []
        pos = 0

        for width in widths:
            if pos >= len(line):
                parts.append("")
                continue

            field = line[pos : pos + width].strip()
            parts.append(field)
            pos += width

        # Handle remaining fields (ReqNodes, NodeList, Reason) - they're space-separated
        remaining = line[pos:].strip()
        if remaining:
            remaining_parts = remaining.split(None, 2)  # Split into at most 3 parts
            parts.extend(remaining_parts)
            # Ensure we have all expected fields
            while len(parts) < 11:
                parts.append("")
        else:
            # Add empty fields for missing ReqNodes, NodeList, and Reason
            parts.extend(["", "", ""])

        return parts

    def _parse_gpu_count(self, tres_field: str) -> str:
        """Parse GPU count from TRES field."""
        if not tres_field or tres_field == "N/A":
            return "0"

        # TRES format examples:
        # "billing=8,cpu=8,gres/gpu=2,mem=32G,node=1"
        # "cpu=16,gres/gpu:h100:4,mem=64G,node=1"
        # "gres/gpu=8"

        import re

        # Look for gres/gpu patterns
        gpu_patterns = [
            r"gres/gpu:[\w\d]+:(\d+)",  # gres/gpu:h100:4
            r"gres/gpu=(\d+)",  # gres/gpu=2
            r"gres/gpu:(\d+)",  # gres/gpu:4
        ]

        for pattern in gpu_patterns:
            match = re.search(pattern, tres_field)
            if match:
                return match.group(1)

        return "0"

    def _parse_gpu_type(self, tres_field: str) -> str:
        """Parse GPU type from TRES field."""
        if not tres_field or tres_field == "N/A":
            return ""

        import re

        # Look for GPU type in patterns like gres/gpu:h100:4
        type_pattern = r"gres/gpu:([\w\d]+):\d+"
        match = re.search(type_pattern, tres_field)
        if match:
            gpu_type = match.group(1).upper()
            # Common GPU type mappings for DGX systems
            if "h100" in gpu_type.lower():
                return "H100"
            elif "a100" in gpu_type.lower():
                return "A100"
            elif "v100" in gpu_type.lower():
                return "V100"
            return gpu_type

        # If no specific type found but GPUs are allocated, assume H100 for DGX-H100 cluster
        if self._parse_gpu_count(tres_field) != "0":
            return "H100"

        return ""

    def _parse_node_gpu_info(self, gres_field: str) -> str:
        """Parse GPU count from node GRES field - just show count since partition indicates type."""
        if not gres_field or gres_field == "(null)" or gres_field == "N/A":
            return "0"

        import re

        # GRES format examples:
        # "gpu:8"
        # "gpu:h100:8"
        # "(null)"

        # Look for GPU patterns in GRES - extract just the count
        gpu_patterns = [
            r"gpu:[\w\d]+:(\d+)",  # gpu:h100:8 -> extract count
            r"gpu:(\d+)",  # gpu:8 -> extract count
        ]

        for pattern in gpu_patterns:
            match = re.search(pattern, gres_field)
            if match:
                return match.group(1)  # Just return the count

        return "0"

    def _extract_cpus_from_tres(self, tres_field: str) -> str:
        """Extract CPU count from TRES field."""
        if not tres_field or tres_field == "N/A":
            return ""

        import re

        # TRES format examples:
        # "billing=8,cpu=16,gres/gpu:h100:4,mem=64G,node=1"
        # "cpu=32,mem=128G,node=1"

        cpu_pattern = r"cpu=(\d+)"
        match = re.search(cpu_pattern, tres_field)
        if match:
            return match.group(1)

        return ""

    def _count_nodes_from_nodelist(self, nodelist: str) -> str:
        """Count the number of nodes from NodeList field."""
        if not nodelist or nodelist.strip() == "":
            return "0"

        # If it contains reason text (like "Dependency"), it's not actual nodes
        if any(
            reason in nodelist
            for reason in ["Dependency", "Resources", "Priority", "QOSMaxJobsPerUserLimit", "AssocMaxJobsLimit"]
        ):
            return "0"

        # Count comma-separated node names (e.g., "node1,node2,node3" -> "3")
        nodes = [n.strip() for n in nodelist.split(",") if n.strip()]
        return str(len(nodes))

    def _combine_nodelist_reason(self, nodelist: str, reason: str) -> str:
        """Combine NodeList and Reason into a single display field."""
        # If we have actual nodes, show them
        if nodelist and nodelist.strip() and not any(r in nodelist for r in ["Dependency", "Resources", "Priority"]):
            return nodelist

        # If we have a reason and no actual nodes, show the reason
        if reason and reason.strip() and reason != "None":
            return reason

        # If NodeList contains reason-like text, show it
        if nodelist and nodelist.strip():
            return nodelist

        return ""

    def _extract_mem_from_tres(self, tres_field: str) -> str:
        """Extract memory from TRES field."""
        if not tres_field or tres_field == "N/A":
            return ""

        import re

        # TRES format examples:
        # "billing=8,cpu=16,gres/gpu:h100:4,mem=64G,node=1"
        # "cpu=32,mem=128G,node=1"

        mem_pattern = r"mem=([0-9]+[KMGT]?)"
        match = re.search(mem_pattern, tres_field)
        if match:
            return match.group(1)

        return ""

    def _mock_jobs(self) -> List[Dict[str, Any]]:
        return [
            {
                "JOBID": "12345",
                "PARTITION": "h100",
                "NAME": "train-resnet-50",
                "USERNAME": "alice",
                "STATE": "RUNNING",
                "TRES": "billing=8,cpu=16,gres/gpu:h100:4,mem=64G,node=1",
                "TimeUsed": "02:15:30",
                "TimeLimit": "24:00:00",
                "ReqNodes": "1",
                "NodeList": "DGX-H100-1",
                "GPU_COUNT": "4",
                "GPU_TYPE": "H100",
            },
            {
                "JOBID": "12346",
                "PARTITION": "a100",
                "NAME": "inference-bert-large",
                "USERNAME": "bob",
                "STATE": "PENDING",
                "TRES": "billing=2,cpu=8,gres/gpu:a100:2,mem=32G,node=1",
                "TimeUsed": "00:00:00",
                "TimeLimit": "12:00:00",
                "ReqNodes": "1",
                "NodeList": "(Resources)",
                "GPU_COUNT": "2",
                "GPU_TYPE": "H100",
            },
            {
                "JOBID": "12347",
                "PARTITION": "cpu",
                "NAME": "data-preprocessing",
                "USERNAME": "charlie",
                "STATE": "RUNNING",
                "TRES": "billing=4,cpu=32,mem=128G,node=1",
                "TimeUsed": "01:45:12",
                "TimeLimit": "06:00:00",
                "ReqNodes": "1",
                "NodeList": "DGX-H100-2",
                "GPU_COUNT": "0",
                "GPU_TYPE": "",
            },
        ]

    def _mock_nodes(self) -> List[Dict[str, Any]]:
        return [
            {
                "NODE": "dgx-h100-01",
                "PARTITION": "gpu",
                "STATE": "idle",
                "AVAIL": "up",
                "CPUS": "240",
                "MEM": "1000G",
                "S:C:T": "2:60:2",
                "GRES": "gpu:h100:8",
            }
        ]


# ------------------------------ Modal Screens ------------------------------


class ScriptModal(ModalScreen):
    """Beautiful modal screen for displaying job scripts with syntax highlighting."""

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
            # Beautiful header with job info
            yield Static(
                f"[bold bright_cyan]📄 Slurm Script - Job {self.jobid}[/bold bright_cyan]\n"
                f"[dim]Press [bold]Escape[/bold] or [bold]q[/bold] to close[/dim]",
                id="script_header",
                classes="script-header",
            )
            # Beautiful syntax-highlighted script content
            from rich.syntax import Syntax

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
    """Beautiful modal screen for displaying job output."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("r", "refresh_output", "Refresh"),
    ]

    def __init__(self, jobid: str, stdout: str, stderr: str, client) -> None:
        super().__init__()
        self.jobid = jobid
        self.stdout = stdout
        self.stderr = stderr
        self.client = client

    def compose(self) -> ComposeResult:
        with Vertical(id="output_modal_container"):
            # Beautiful header
            yield Static(
                f"[bold bright_green]📊 Job Output - Job {self.jobid}[/bold bright_green]\n"
                f"[dim]Press [bold]Escape[/bold]/[bold]q[/bold] to close, [bold]r[/bold] to refresh[/dim]",
                id="output_header",
                classes="output-header",
            )
            with Vertical(classes="output-content"):
                # STDOUT section
                yield Static("[bold bright_blue]📤 STDOUT[/bold bright_blue]", classes="output-section-header")
                yield LogViewer(
                    self.stdout or "[dim]No stdout available[/dim]",
                    id="modal_stdout_viewer",
                    classes="output-log-viewer",
                )
                # STDERR section
                yield Static("[bold bright_red]📥 STDERR[/bold bright_red]", classes="output-section-header")
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
            stdout, stderr = await self.client.get_job_output(self.jobid)

            stdout_viewer = self.query_one("#modal_stdout_viewer", LogViewer)
            stdout_viewer.set_content(stdout or "No stdout available")

            stderr_viewer = self.query_one("#modal_stderr_viewer", LogViewer)
            stderr_viewer.set_content(stderr or "No stderr available")

            # Update the header to show refresh time
            import datetime

            refresh_time = datetime.datetime.now().strftime("%H:%M:%S")
            header = self.query_one(Static)
            header.update(
                f"[bold]Output for Job {self.jobid}[/bold] (Last refreshed: {refresh_time}) (Press Escape/'q' to close, 'r' to refresh)"
            )

        except Exception as e:
            # Show error in header
            header = self.query_one(Static)
            header.update(
                f"[bold]Output for Job {self.jobid}[/bold] (Refresh error: {e}) (Press Escape/'q' to close, 'r' to refresh)"
            )


# ------------------------------ Widgets ------------------------------


class StatusBar(Static):
    message = reactive("Ready")

    def watch_message(self, value: str) -> None:
        self.update(f"[b]{value}[/b]")


class SyntaxViewer(Static):
    """Widget for displaying syntax-highlighted code."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.console = Console()

    def set_code(self, code: str, language: str = "bash") -> None:
        """Set the code content with syntax highlighting."""
        if not code.strip():
            self.update("No content to display")
            return

        try:
            # Create syntax highlighted content
            syntax = Syntax(code, language, theme="monokai", line_numbers=True)
            # Textual can render Rich renderables directly
            self.update(syntax)
        except Exception:
            # Fallback to plain text if syntax highlighting fails
            self.update(f"```{language}\n{code}\n```")


class LogViewer(Static):
    """Widget for displaying log content with auto-scroll."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._content = ""
        self._max_lines = 1000

    def append_content(self, content: str) -> None:
        """Append new content to the log viewer."""
        if content:
            self._content += content
            # Keep only the last max_lines
            lines = self._content.split("\n")
            if len(lines) > self._max_lines:
                lines = lines[-self._max_lines :]
                self._content = "\n".join(lines)
            self.update(self._content)
            # Auto-scroll to bottom
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
    def __init__(self) -> None:
        self.text: str = ""
        self.user: Optional[str] = None
        self.partition: Optional[str] = None
        self.state: Optional[str] = None

    def apply_jobs(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        res = rows
        if self.user:
            # Check both USERNAME (enhanced format) and USER (fallback format)
            res = [r for r in res if (r.get("USERNAME", "") or r.get("USER", "")).lower() == self.user.lower()]
        if self.partition:
            res = [r for r in res if self.partition.lower() in r.get("PARTITION", "").lower()]
        if self.state:
            res = [r for r in res if self.state.lower() in r.get("STATE", "").lower()]
        if self.text:
            pat = self.text.lower()
            res = [r for r in res if any(pat in str(v).lower() for v in r.values())]
        return res

    def apply_nodes(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        res = rows
        if self.partition:
            res = [r for r in res if self.partition.lower() in r.get("PARTITION", "").lower()]
        if self.state:
            res = [r for r in res if self.state.lower() in r.get("STATE", "").lower()]
        if self.text:
            pat = self.text.lower()
            res = [r for r in res if any(pat in str(v).lower() for v in r.values())]
        return res


# ------------------------------ App ------------------------------


class SlurmDashboard(App):
    CSS = """
    Screen { layout: vertical; }
    .bar { height: 1; }
    .pane { height: 1fr; }
    .detail { padding: 1; }
    .detail-container { height: 15; border: round $surface; padding: 1; overflow-y: auto; }
    .script { height: 20; border: round green; padding: 1; overflow-y: auto; }
    .syntax-viewer { height: 1fr; border: round blue; padding: 1; overflow-y: auto; }
    .log-viewer { height: 1fr; border: round yellow; padding: 1; overflow-y: auto; }
    .log-container { height: 1fr; }

    /* Beautiful Modal screen styles */
    ScriptModal {
        align: center middle;
        background: $surface-darken-2 90%;
    }

    #script_modal_container {
        width: 85%;
        height: 80%;
        background: $panel;
        border: thick $accent;
        border-title-color: $accent;
        border-title-background: $panel;
    }

    .script-header {
        height: 3;
        background: $primary-darken-1;
        color: $text;
        text-align: center;
        padding: 1;
        border-bottom: solid $accent;
    }

    .script-content {
        height: 1fr;
        background: $surface;
        padding: 1;
        overflow: auto;
        scrollbar-background: $panel;
        scrollbar-color: $accent;
    }

    OutputModal {
        align: center middle;
        background: $surface-darken-2 90%;
    }

    #output_modal_container {
        width: 95%;
        height: 90%;
        background: $panel;
        border: thick $success;
        border-title-color: $success;
        border-title-background: $panel;
    }

    .output-header {
        height: 3;
        background: $success-darken-1;
        color: $text;
        text-align: center;
        padding: 1;
        border-bottom: solid $success;
    }

    .output-content {
        height: 1fr;
        padding: 1;
    }

    .output-section-header {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding-left: 1;
        margin-top: 1;
    }

    .output-log-viewer {
        height: 1fr;
        background: $surface;
        border: solid $primary;
        margin-bottom: 1;
        padding: 1;
        overflow: auto;
        scrollbar-background: $panel;
        scrollbar-color: $success;
    }
    """

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
        self, *, refresh_sec: float = 5.0, user: Optional[str] = None, partition: Optional[str] = None
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
        self.user_wants_realtime = True  # User preference for real-time refresh

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield self.status
        with TabbedContent():
            with TabPane("Jobs", id="tab_jobs"):
                with Vertical(id="jobs_pane", classes="pane"):
                    yield Input(placeholder="/ Search in jobs", id="job_search")
                    yield DataTable(id="jobs_table")
                    with ScrollableContainer(id="job_detail_container", classes="detail-container"):
                        yield Static("Select a job to see details.", id="job_detail", classes="detail")
            with TabPane("Script", id="tab_script"):
                with Vertical(id="script_pane", classes="pane"):
                    yield Static("Select a job from the Jobs tab to view its script here.", id="script_info")
                    yield SyntaxViewer("No script loaded", id="script_viewer", classes="syntax-viewer")
            with TabPane("Output", id="tab_output"):
                with Vertical(id="output_pane", classes="pane"):
                    yield Static("Select a job from the Jobs tab to view its output here.", id="output_info")
                    with Vertical(classes="log-container"):
                        yield Static("[bold]STDOUT:[/bold]", classes="bar")
                        yield LogViewer("No stdout available", id="stdout_viewer", classes="log-viewer")
                        yield Static("[bold]STDERR:[/bold]", classes="bar")
                        yield LogViewer("No stderr available", id="stderr_viewer", classes="log-viewer")
            with TabPane("Nodes", id="tab_nodes"):
                with Vertical(id="nodes_pane", classes="pane"):
                    yield Input(placeholder="/ Search in nodes", id="node_search")
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
        # Set up real-time output refresh (every 2 seconds when enabled)
        self.set_interval(2.0, self._schedule_output_refresh)

    def _schedule_refresh(self) -> None:
        self.run_worker(self.refresh_data(), group="refresh", exclusive=True, exit_on_error=False)

    def _schedule_output_refresh(self) -> None:
        """Schedule output refresh for the currently selected job."""
        if self.output_refresh_enabled and self.current_jobid:
            self.run_worker(
                self._refresh_current_output(), group="output_refresh", exclusive=True, exit_on_error=False
            )

    async def _refresh_current_output(self) -> None:
        """Refresh output for the currently selected job."""
        if not self.current_jobid:
            return

        try:
            stdout, stderr = await self.client.get_job_output(self.current_jobid)

            stdout_viewer = self.query_one("#stdout_viewer", LogViewer)
            stdout_viewer.set_content(stdout or "No stdout available")

            stderr_viewer = self.query_one("#stderr_viewer", LogViewer)
            stderr_viewer.set_content(stderr or "No stderr available")

        except Exception:
            # Silently fail for background refresh
            pass

    async def action_refresh(self) -> None:
        await self.refresh_data()

    def action_focus_search(self) -> None:
        """Focus the search input in the current tab."""
        try:
            # Get the currently active tab
            tabbed_content = self.query_one("TabbedContent")
            active_tab = getattr(tabbed_content, "active", None)

            if active_tab == "tab_jobs":
                search_input = self.query_one("#job_search", Input)
                search_input.focus()
                self.status.message = "Search jobs (press Enter to apply filter)"
            elif active_tab == "tab_nodes":
                search_input = self.query_one("#node_search", Input)
                search_input.focus()
                self.status.message = "Search nodes (press Enter to apply filter)"
            else:
                self.status.message = "Search not available in this tab"
        except Exception as e:
            self.status.message = f"Search focus error: {e}"

    async def action_filter_dialog(self) -> None:
        """Show filter status and provide quick filter options."""
        # Debug: Show that the action was called
        focused_widget = self.focused
        widget_info = f"{type(focused_widget).__name__}" if focused_widget else "None"

        # For now, show current filter status and provide instructions
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
            current_filters = ", ".join(filter_info)
            self.status.message = f"🔍 Active filters: {current_filters} (Focus: {widget_info})"
        else:
            self.status.message = f"🔍 No active filters. Use search '/' to filter (Focus: {widget_info})"

        # Refresh data to apply any current filters
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

        # Open modal window
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

        # Open modal window
        modal = OutputModal(str(jobid), stdout, stderr, self.client)
        self.push_screen(modal)

        self.status.message = f"Output modal opened for job {jobid} (Press Escape to close, 'r' to refresh)"

    async def action_refresh_output(self) -> None:
        """Refresh the output in the existing Output tab (not modal)."""
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

        # Update the existing output tab (not modal)
        output_info = self.query_one("#output_info", Static)
        import datetime

        refresh_time = datetime.datetime.now().strftime("%H:%M:%S")
        output_info.update(f"[bold]Output for Job {jobid}[/bold] (Refreshed: {refresh_time})")

        stdout_viewer = self.query_one("#stdout_viewer", LogViewer)
        stdout_viewer.set_content(stdout or "No stdout available")

        stderr_viewer = self.query_one("#stderr_viewer", LogViewer)
        stderr_viewer.set_content(stderr or "No stderr available")

        self.status.message = f"Output refreshed for job {jobid} at {refresh_time}"

    def action_toggle_realtime(self) -> None:
        """Toggle real-time output refresh."""
        # Toggle user preference
        self.user_wants_realtime = not self.user_wants_realtime

        # Always show immediate feedback with focus info
        toggle_state = "ON" if self.user_wants_realtime else "OFF"
        focused_widget = self.focused
        widget_info = f"{type(focused_widget).__name__}" if focused_widget else "None"
        self.status.message = f"🔄 Real-time toggle pressed! Setting to: {toggle_state} (Focus: {widget_info})"

        # Update the actual refresh state based on user preference and job state
        if self.current_jobid:
            try:
                # Get current job state to determine if real-time makes sense
                table: DataTable = self.query_one("#jobs_table", DataTable)
                if table.cursor_coordinate is not None:
                    row = table.get_row_at(table.cursor_coordinate.row)
                    if row and len(row) > 2:
                        # STATE column is now at position 2 in both enhanced and fallback formats
                        job_state = row[2]  # STATE column position
                        can_refresh = job_state.upper() in ["RUNNING", "PENDING"]
                        self.output_refresh_enabled = self.user_wants_realtime and can_refresh

                        # More detailed status message
                        if self.user_wants_realtime:
                            if can_refresh:
                                final_msg = f"✅ Real-time refresh: ON (job is {job_state})"
                            else:
                                final_msg = f"⚠️ Real-time refresh: ON but job is {job_state} (not active)"
                        else:
                            final_msg = "❌ Real-time refresh: OFF"
                    else:
                        self.output_refresh_enabled = False
                        final_msg = f"⚠️ Real-time refresh: {toggle_state} (no job data)"
                else:
                    self.output_refresh_enabled = False
                    final_msg = f"⚠️ Real-time refresh: {toggle_state} (no job selected)"
            except Exception as e:
                self.output_refresh_enabled = False
                final_msg = f"❌ Real-time toggle error: {e}"
        else:
            self.output_refresh_enabled = False
            final_msg = f"⚠️ Real-time refresh: {toggle_state} (no current job)"

        # Update status with final message
        self.status.message = final_msg

        # Update the output info to reflect the change
        try:
            if self.current_jobid:
                output_info = self.query_one("#output_info", Static)
                if self.user_wants_realtime and self.output_refresh_enabled:
                    refresh_status = " 🔄 (Real-time ON)"
                elif self.user_wants_realtime:
                    refresh_status = " ⏸️ (Real-time ON, but job not active)"
                else:
                    refresh_status = " ⏹️ (Real-time OFF)"
                output_info.update(
                    f"[bold]Output for Job {self.current_jobid}[/bold] (Press 'o' to refresh){refresh_status}"
                )
        except Exception:
            # Don't let output update errors break the toggle
            pass

    def action_debug_test(self) -> None:
        """Simple debug action to test if keybindings work."""
        focused_widget = self.focused
        widget_info = f"{type(focused_widget).__name__}" if focused_widget else "None"
        self.status.message = f"🐛 DEBUG: Keybinding works! Focused widget: {widget_info}"

    async def refresh_data(self) -> None:
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
        table: DataTable = self.query_one("#jobs_table", DataTable)

        # Save current cursor position before clearing table
        saved_cursor_row = None
        if table.cursor_coordinate is not None:
            saved_cursor_row = table.cursor_coordinate.row

        table.clear(columns=True)

        # Enhanced columns with logical ordering and clear naming
        if jobs and "TRES" in jobs[0]:
            # Use enhanced format with all squeue_ fields plus extracted resources
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
                # Create intuitive GPU display - just show count since partition indicates type
                gpu_count = j.get("GPU_COUNT", "0")
                gpu_display = gpu_count

                # Extract CPUS and MEM from TRES field
                cpus = self.client._extract_cpus_from_tres(j.get("TRES", ""))
                mem = self.client._extract_mem_from_tres(j.get("TRES", ""))

                # Count nodes from NodeList field
                node_count = self.client._count_nodes_from_nodelist(j.get("NodeList", ""))

                # Combine NodeList and Reason for display
                nodelist_display = self.client._combine_nodelist_reason(j.get("NodeList", ""), j.get("Reason", ""))

                table.add_row(
                    j.get("JOBID", ""),
                    j.get("USERNAME", j.get("USER", "")),  # Fallback to USER if USERNAME not available
                    j.get("STATE", ""),
                    j.get("PARTITION", ""),
                    cpus,
                    mem,
                    gpu_display,
                    j.get("TimeUsed", j.get("TIME", "")),  # TimeUsed in enhanced format, TIME in fallback
                    j.get("TimeLimit", ""),
                    j.get("NAME", "")[:30],  # Truncate long names
                    j.get("ReqNodes", ""),  # Requested node names
                    node_count,
                    nodelist_display,  # NodeList shows actual nodes or reason for pending jobs
                )
        else:
            # Fallback to basic format - match enhanced format structure
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
                # Count nodes from NODELIST(REASON) field in fallback format
                node_count = self.client._count_nodes_from_nodelist(j.get("NODELIST(REASON)", ""))

                table.add_row(
                    j.get("JOBID", ""),
                    j.get("USER", ""),
                    j.get("STATE", ""),
                    j.get("PARTITION", ""),
                    j.get("CPUS", ""),
                    j.get("MEM", ""),
                    j.get("TIME", ""),
                    j.get("NAME", ""),
                    node_count,  # Nodes column shows the count
                    j.get("NODELIST(REASON)", ""),
                )

        # Preserve cursor position after refresh (don't jump to top!)
        if table.row_count:
            with contextlib.suppress(Exception):
                if saved_cursor_row is not None and saved_cursor_row < table.row_count:
                    # Restore the saved cursor position
                    table.move_cursor(row=saved_cursor_row)
                elif table.cursor_coordinate is None:
                    # Only set cursor to top if there wasn't one before (first load)
                    table.move_cursor(row=0)

    def _populate_nodes(self, nodes: List[Dict[str, Any]]) -> None:
        table: DataTable = self.query_one("#nodes_table", DataTable)
        table.clear(columns=True)

        # Enhanced columns with better GPU display
        columns = ["NODE", "STATE", "AVAIL", "GPUs", "CPUS", "MEM", "PARTITION"]
        table.add_columns(*columns)
        for n in nodes:
            # Parse GRES field for better GPU display
            gres = n.get("GRES", "")
            gpu_display = self.client._parse_node_gpu_info(gres)

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

            # Set current job for real-time refresh
            self.current_jobid = str(jobid)
            # STATE column is now at position 2 in both enhanced and fallback formats
            job_state = row[2]  # STATE column position
            # Enable real-time refresh based on user preference AND job state
            can_refresh = job_state.upper() in ["RUNNING", "PENDING"]
            self.output_refresh_enabled = self.user_wants_realtime and can_refresh

            # Update job detail panel
            detail = await self.client.get_job_detail(str(jobid))
            panel = self.query_one("#job_detail", Static)
            panel.update(f"[b]Job {jobid}[/b]\n{detail}")

            # Auto-load script in the script tab
            script_text = await self.client.get_job_script(str(jobid))
            script_info = self.query_one("#script_info", Static)
            script_info.update(f"[bold]Script for Job {jobid}[/bold] (Press 's' to view in old panel)")
            script_viewer = self.query_one("#script_viewer", SyntaxViewer)
            script_viewer.set_code(script_text, "bash")

            # Auto-load output in the output tab
            stdout, stderr = await self.client.get_job_output(str(jobid))
            output_info = self.query_one("#output_info", Static)

            # Show appropriate real-time status
            if self.user_wants_realtime and self.output_refresh_enabled:
                refresh_status = " (Real-time refresh ON)"
            elif self.user_wants_realtime and can_refresh:
                refresh_status = " (Real-time refresh ON)"
            elif self.user_wants_realtime:
                refresh_status = " (Real-time refresh ON, but job not active)"
            else:
                refresh_status = " (Real-time refresh OFF - press 't' to enable)"

            output_info.update(f"[bold]Output for Job {jobid}[/bold] (Press 'o' to refresh){refresh_status}")

            stdout_viewer = self.query_one("#stdout_viewer", LogViewer)
            stdout_viewer.set_content(stdout or "No stdout available")

            stderr_viewer = self.query_one("#stderr_viewer", LogViewer)
            stderr_viewer.set_content(stderr or "No stderr available")

        except Exception as e:
            self.status.message = f"Row select error: {e}"

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if event.input.id == "job_search":
            self.filter.text = text
            await self.refresh_data()
        elif event.input.id == "node_search":
            self.filter.text = text
            await self.refresh_data()


# ------------------------------ main ------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Slurm Dashboard (Textual)")
    p.add_argument("--refresh", type=float, default=5.0, help="Auto-refresh interval (s)")
    p.add_argument("--user", type=str, default=None, help="Default user filter")
    p.add_argument("--me", action="store_true", help="Filter jobs for current user (alias for --user $USER)")
    p.add_argument("--partition", "-p", type=str, default=None, help="Default partition filter")
    return p.parse_args(argv)


def main():
    args = parse_args()

    # Handle --me flag
    user_filter = args.user
    if args.me:
        import os

        user_filter = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    app = SlurmDashboard(refresh_sec=args.refresh, user=user_filter, partition=args.partition)
    app.run()


if __name__ == "__main__":
    main()
