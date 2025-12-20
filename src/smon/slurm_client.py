"""Slurm client for interacting with Slurm commands."""

import asyncio
import re
import shlex
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .utils import run_cmd, which


@dataclass
class SlurmCommands:
    """Paths to Slurm commands."""

    squeue: str = "squeue"
    sinfo: str = "sinfo"
    scontrol: str = "scontrol"


class SlurmClient:
    """Client for interacting with Slurm cluster."""

    # Regex patterns for parsing GPU information
    GPU_COUNT_PATTERNS = [
        re.compile(r"gres/gpu:[\w\d]+:(\d+)"),  # gres/gpu:h100:4
        re.compile(r"gres/gpu=(\d+)"),  # gres/gpu=2
        re.compile(r"gres/gpu:(\d+)"),  # gres/gpu:4
    ]
    GPU_TYPE_PATTERN = re.compile(r"gres/gpu:([\w\d]+):\d+")
    NODE_GPU_PATTERNS = [
        re.compile(r"gpu:[\w\d]+:(\d+)"),  # gpu:h100:8
        re.compile(r"gpu:(\d+)"),  # gpu:8
    ]
    CPU_PATTERN = re.compile(r"cpu=(\d+)")
    MEM_PATTERN = re.compile(r"mem=([0-9]+[KMGT]?)")

    # Reason keywords indicating pending state
    PENDING_REASONS = frozenset(
        [
            "Dependency",
            "Resources",
            "Priority",
            "QOSMaxJobsPerUserLimit",
            "AssocMaxJobsLimit",
        ]
    )

    def __init__(self, cmds: Optional[SlurmCommands] = None) -> None:
        self.cmds = cmds or SlurmCommands()
        for name in ("squeue", "sinfo", "scontrol"):
            found = which(getattr(self.cmds, name))
            if found:
                setattr(self.cmds, name, shlex.quote(found))

    async def get_jobs(self) -> List[Dict[str, Any]]:
        """Get list of jobs from Slurm."""
        if not which("squeue"):
            return self._mock_jobs()

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
        fmt = "JobID:10,Partition:12,NAME:36,USERNAME:10,STATE:10,TRES:50,TimeUsed:12,TimeLimit:14,ReqNodes,NodeList,Reason"

        rc, out, err = await run_cmd(f"{self.cmds.squeue} -h -O '{fmt}' --states=all", timeout=10)
        if rc != 0:
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

            if "TRES" in cols:
                parts = self._parse_squeue_output_line(line)
            else:
                parts = [p.strip() for p in line.split("|")]

            if len(parts) < len(cols) - 2:
                continue

            row = {k: parts[i] if i < len(parts) else "" for i, k in enumerate(cols)}

            if "TRES" in row:
                row["GPU_COUNT"] = self._parse_gpu_count(row["TRES"])
                row["GPU_TYPE"] = self._parse_gpu_type(row["TRES"])
            else:
                row["GPU_COUNT"] = ""
                row["GPU_TYPE"] = ""

            jobs.append(row)
        return jobs

    async def get_nodes(self) -> List[Dict[str, Any]]:
        """Get list of nodes from Slurm."""
        if not which("sinfo"):
            return self._mock_nodes()

        # Use -O (long format) for GresUsed which works better than %b
        cols = ["NODE", "PARTITION", "STATE", "AVAIL", "CPUS", "MEM", "GRES", "GRES_USED"]
        cmd = (
            f"{self.cmds.sinfo} -N -h -O "
            "'NodeList:|,Partition:|,StateLong:|,Available:|,CPUs:|,Memory:|,Gres:|,GresUsed:|'"
        )

        rc, out, err = await run_cmd(cmd, timeout=10)
        if rc != 0:
            raise RuntimeError(f"sinfo failed: {err.strip() or 'unknown error'}")

        nodes: List[Dict[str, Any]] = []
        for line in out.splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < len(cols):
                continue
            nodes.append(dict(zip(cols, parts[: len(cols)])))
        return nodes

    async def get_job_detail(self, jobid: str) -> str:
        """Get detailed information for a specific job."""
        if not which("scontrol"):
            return f"Mock details for Job {jobid}\nUser=alice State=RUNNING Nodes=1 CPUS=8 Mem=16G"
        cmd = f"{self.cmds.scontrol} show job {shlex.quote(jobid)}"
        rc, out, err = await run_cmd(cmd, timeout=10)
        if rc != 0:
            return f"Failed to get job detail: {err.strip() or 'unknown error'}"
        return out.strip()

    async def get_job_script(self, jobid: str) -> str:
        """Get the batch script for a job."""
        if not which("scontrol"):
            return "Slurm scontrol not available; cannot fetch job script."
        cmd = f"{self.cmds.scontrol} write batch_script {shlex.quote(jobid)} -"
        rc, out, _err = await run_cmd(cmd, timeout=15)
        if rc == 0 and out.strip():
            return out.rstrip()
        return "(No script stored by controller)"

    async def get_job_output_paths(self, jobid: str, detail: Optional[str] = None) -> Tuple[str, str]:
        """Get stdout and stderr file paths for a job.

        Args:
            jobid: The job ID to get output paths for.
            detail: Pre-fetched job detail string to avoid duplicate scontrol call.

        Returns:
            Tuple of (stdout_path, stderr_path).
        """
        if not which("scontrol"):
            return "", ""

        if detail is None:
            detail = await self.get_job_detail(jobid)

        stdout_file = ""
        stderr_file = ""

        for line in detail.split("\n"):
            if "StdOut=" in line:
                stdout_file = line.split("StdOut=")[1].split()[0]
            elif "StdErr=" in line:
                stderr_file = line.split("StdErr=")[1].split()[0]

        return stdout_file, stderr_file

    async def get_job_output(self, jobid: str, full: bool = False, detail: Optional[str] = None) -> Tuple[str, str]:
        """Get stdout and stderr for a job.

        Args:
            jobid: The job ID to get output for.
            full: If True, get more lines (100). If False, get preview (20 lines).
            detail: Pre-fetched job detail string to avoid duplicate scontrol call.
        """
        stdout_file, stderr_file = await self.get_job_output_paths(jobid, detail)
        if not stdout_file and not stderr_file:
            return "Mock stdout output for testing", "Mock stderr output for testing"

        lines = 100 if full else 20
        # Read both files in parallel
        stdout_content, stderr_content = await asyncio.gather(
            self._read_output_file(stdout_file, lines),
            self._read_output_file(stderr_file, lines),
        )
        return stdout_content, stderr_content

    async def _read_output_file(self, filepath: str, lines: int = 20) -> str:
        """Read content from an output file.

        Args:
            filepath: Path to the output file.
            lines: Number of lines to read from the end.
        """
        if not filepath or filepath == "/dev/null":
            return ""
        try:
            rc, out, err = await run_cmd(f"tail -n {lines} {shlex.quote(filepath)}", timeout=5)
            if rc == 0:
                return out
            return f"Could not read file: {err}"
        except Exception as e:
            return f"Error reading file: {e}"

    def _parse_squeue_output_line(self, line: str) -> List[str]:
        """Parse fixed-width squeue -O output line into fields."""
        widths = [10, 12, 36, 10, 10, 50, 12, 14]
        parts = []
        pos = 0

        for width in widths:
            if pos >= len(line):
                parts.append("")
                continue
            parts.append(line[pos : pos + width].strip())
            pos += width

        remaining = line[pos:].strip()
        if remaining:
            remaining_parts = remaining.split(None, 2)
            parts.extend(remaining_parts)
            while len(parts) < 11:
                parts.append("")
        else:
            parts.extend(["", "", ""])

        return parts

    def _parse_gpu_count(self, tres_field: str) -> str:
        """Parse GPU count from TRES field."""
        if not tres_field or tres_field == "N/A":
            return "0"
        for pattern in self.GPU_COUNT_PATTERNS:
            match = pattern.search(tres_field)
            if match:
                return match.group(1)
        return "0"

    def _parse_gpu_type(self, tres_field: str) -> str:
        """Parse GPU type from TRES field."""
        if not tres_field or tres_field == "N/A":
            return ""
        match = self.GPU_TYPE_PATTERN.search(tres_field)
        if match:
            gpu_type = match.group(1).upper()
            if "h100" in gpu_type.lower():
                return "H100"
            elif "a100" in gpu_type.lower():
                return "A100"
            elif "v100" in gpu_type.lower():
                return "V100"
            return gpu_type
        if self._parse_gpu_count(tres_field) != "0":
            return "H100"
        return ""

    def parse_node_gpu_info(self, gres_field: str) -> str:
        """Parse GPU count from node GRES field."""
        if not gres_field or gres_field in ("(null)", "N/A"):
            return "0"
        for pattern in self.NODE_GPU_PATTERNS:
            match = pattern.search(gres_field)
            if match:
                return match.group(1)
        return "0"

    def extract_cpus_from_tres(self, tres_field: str) -> str:
        """Extract CPU count from TRES field."""
        if not tres_field or tres_field == "N/A":
            return ""
        match = self.CPU_PATTERN.search(tres_field)
        if match:
            return match.group(1)
        return ""

    def extract_mem_from_tres(self, tres_field: str) -> str:
        """Extract memory from TRES field."""
        if not tres_field or tres_field == "N/A":
            return ""
        match = self.MEM_PATTERN.search(tres_field)
        if match:
            return match.group(1)
        return ""

    def count_nodes_from_nodelist(self, nodelist: str) -> str:
        """Count the number of nodes from NodeList field."""
        if not nodelist or nodelist.strip() == "":
            return "0"
        if any(reason in nodelist for reason in self.PENDING_REASONS):
            return "0"
        nodes = [n.strip() for n in nodelist.split(",") if n.strip()]
        return str(len(nodes))

    def combine_nodelist_reason(self, nodelist: str, reason: str) -> str:
        """Combine NodeList and Reason into a single display field."""
        if nodelist and nodelist.strip():
            if not any(r in nodelist for r in self.PENDING_REASONS):
                return nodelist
        if reason and reason.strip() and reason != "None":
            return reason
        if nodelist and nodelist.strip():
            return nodelist
        return ""

    def _mock_jobs(self) -> List[Dict[str, Any]]:
        """Return mock job data for testing without Slurm."""
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
        """Return mock node data for testing without Slurm."""
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

    @staticmethod
    def parse_time_to_seconds(time_str: str) -> int:
        """Parse Slurm time format to seconds.

        Formats: MM:SS, HH:MM:SS, D-HH:MM:SS, UNLIMITED, etc.
        """
        if not time_str or time_str in ("UNLIMITED", "INVALID", "Partition_Limit"):
            return -1

        try:
            days = 0
            if "-" in time_str:
                day_part, time_part = time_str.split("-", 1)
                days = int(day_part)
            else:
                time_part = time_str

            parts = time_part.split(":")
            if len(parts) == 3:
                hours, minutes, seconds = map(int, parts)
            elif len(parts) == 2:
                hours = 0
                minutes, seconds = map(int, parts)
            else:
                return -1

            return days * 86400 + hours * 3600 + minutes * 60 + seconds
        except (ValueError, AttributeError):
            return -1

    @staticmethod
    def calculate_time_ratio(time_used: str, time_limit: str) -> float:
        """Calculate the ratio of time used to time limit.

        Returns -1 if unable to calculate (e.g., UNLIMITED limit).
        """
        used_sec = SlurmClient.parse_time_to_seconds(time_used)
        limit_sec = SlurmClient.parse_time_to_seconds(time_limit)

        if used_sec < 0 or limit_sec <= 0:
            return -1.0

        return used_sec / limit_sec

    async def cancel_job(self, jobid: str) -> Tuple[bool, str]:
        """Cancel a job using scancel.

        Returns:
            Tuple of (success, message)
        """
        if not which("scancel"):
            return False, "scancel command not found"

        cmd = f"scancel {shlex.quote(jobid)}"
        rc, _out, err = await run_cmd(cmd, timeout=10)

        if rc == 0:
            return True, f"Job {jobid} cancelled successfully"
        return False, err.strip() or "Unknown error"
