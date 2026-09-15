"""Slurm client for interacting with Slurm commands."""

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from .utils import run_cmd_safe, which

# Field separator appended to every -O/--Format column. Slurm never emits '|' in these fields.
_SEP = "|"


def _fmt(*fields: str) -> str:
    """Build a `--Format` spec with a `|` suffix on every field."""
    return ",".join(f"{f}:{_SEP}" for f in fields)


def _split(line: str, n: int) -> list[str] | None:
    """Split a `|`-suffixed line into n fields, or None if malformed.

    Free-text fields (job name) are placed last in every format so that a `|`
    inside them is re-joined instead of shifting the columns.
    """
    parts = line.split(_SEP)
    if parts and parts[-1] == "":
        parts.pop()  # trailing suffix
    if len(parts) < n:
        return None
    if len(parts) > n:
        parts = parts[: n - 1] + [_SEP.join(parts[n - 1 :])]
    return [p.strip() for p in parts]


@dataclass
class SlurmCommands:
    """Paths to Slurm commands."""

    squeue: str = "squeue"
    sinfo: str = "sinfo"
    scontrol: str = "scontrol"
    scancel: str = "scancel"


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

    JOB_FIELDS = (
        "JobID",
        "Partition",
        "UserName",
        "State",
        "tres-alloc",
        "TimeUsed",
        "TimeLimit",
        "NumNodes",
        "NodeList",
        "Reason",
        "Name",
    )
    JOB_COLS = [
        "JOBID",
        "PARTITION",
        "USERNAME",
        "STATE",
        "TRES",
        "TimeUsed",
        "TimeLimit",
        "ReqNodes",
        "NodeList",
        "Reason",
        "NAME",
    ]
    # Legacy `-o` fallback for controllers that reject the --Format suffix syntax.
    JOB_BASIC_FMT = "%i|%u|%T|%M|%D|%P|%R|%C|%m|%j"
    JOB_BASIC_COLS = [
        "JOBID",
        "USER",
        "STATE",
        "TIME",
        "NODES",
        "PARTITION",
        "NODELIST(REASON)",
        "CPUS",
        "MEM",
        "NAME",
    ]

    NODE_FIELDS = (
        "NodeList",
        "Partition",
        "StateLong",
        "Available",
        "CPUsState",
        "Memory",
        "AllocMem",
        "Gres",
        "GresUsed",
    )
    NODE_COLS = ["NODE", "PARTITION", "STATE", "AVAIL", "CPUS_STATE", "MEM", "ALLOC_MEM", "GRES", "GRES_USED"]

    NODE_JOB_FIELDS = ("JobID", "UserName", "State", "TimeUsed", "Partition", "NumCPUs", "tres-alloc", "Name")
    NODE_JOB_COLS = ["JOBID", "USER", "STATE", "TIME", "PARTITION", "CPUS", "TRES", "NAME"]
    NODE_JOB_BASIC_FMT = "%i|%u|%T|%M|%P|%C|%j"
    NODE_JOB_BASIC_COLS = ["JOBID", "USER", "STATE", "TIME", "PARTITION", "CPUS", "NAME"]

    def __init__(self, cmds: SlurmCommands | None = None, mock_mode: bool = False) -> None:
        self.cmds = cmds or SlurmCommands()
        self._mock_mode = mock_mode

        missing: list[str] = []
        for name in ("squeue", "sinfo", "scontrol", "scancel"):
            found = which(getattr(self.cmds, name))
            if found:
                setattr(self.cmds, name, found)
            else:
                missing.append(name)

        if missing and not mock_mode:
            raise RuntimeError(
                f"Slurm commands not found: {', '.join(missing)}. Use --mock flag for demo/testing mode."
            )

    async def get_jobs(self) -> list[dict[str, Any]]:
        """Get list of jobs from Slurm."""
        if self._mock_mode:
            return self._mock_jobs()

        rc, out, err = await run_cmd_safe([self.cmds.squeue, "-h", "--states=all", "-O", _fmt(*self.JOB_FIELDS)])
        if rc == 0:
            return self._parse_jobs(out)

        rc, out, err2 = await run_cmd_safe([self.cmds.squeue, "-h", "--states=all", "-o", self.JOB_BASIC_FMT])
        if rc != 0:
            raise RuntimeError(f"squeue failed: {(err2 or err).strip() or 'unknown error'}")
        jobs = []
        for line in out.splitlines():
            parts = _split(line, len(self.JOB_BASIC_COLS))
            if parts is None:
                continue
            row: dict[str, Any] = dict(zip(self.JOB_BASIC_COLS, parts, strict=True))
            row["GPU_COUNT"] = ""
            row["GPU_TYPE"] = ""
            jobs.append(row)
        return jobs

    def _parse_jobs(self, out: str) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        for line in out.splitlines():
            parts = _split(line, len(self.JOB_COLS))
            if parts is None:
                continue
            row: dict[str, Any] = dict(zip(self.JOB_COLS, parts, strict=True))
            row["GPU_COUNT"] = self._parse_gpu_count(row["TRES"])
            row["GPU_TYPE"] = self._parse_gpu_type(row["TRES"])
            jobs.append(row)
        return jobs

    async def get_nodes(self) -> list[dict[str, Any]]:
        """Get list of nodes from Slurm (one row per node/partition pair)."""
        if self._mock_mode:
            return self._mock_nodes()

        rc, out, err = await run_cmd_safe([self.cmds.sinfo, "-N", "-h", "-O", _fmt(*self.NODE_FIELDS)])
        if rc != 0:
            raise RuntimeError(f"sinfo failed: {err.strip() or 'unknown error'}")

        nodes: list[dict[str, Any]] = []
        for line in out.splitlines():
            parts = _split(line, len(self.NODE_COLS))
            if parts is not None:
                nodes.append(dict(zip(self.NODE_COLS, parts, strict=True)))
        return nodes

    async def get_job_detail(self, jobid: str) -> str:
        """Get detailed information for a specific job."""
        if self._mock_mode:
            return f"Mock details for Job {jobid}\nUser=alice State=RUNNING Nodes=1 CPUS=8 Mem=16G"
        rc, out, err = await run_cmd_safe([self.cmds.scontrol, "show", "job", jobid])
        if rc != 0:
            return f"Failed to get job detail: {err.strip() or 'unknown error'}"
        return out.strip()

    async def get_jobs_on_node(self, node_name: str) -> list[dict[str, Any]]:
        """Get jobs running on a specific node using squeue -w."""
        if self._mock_mode:
            return [j for j in self._mock_jobs() if j.get("NodeList") == node_name]

        rc, out, _err = await run_cmd_safe(
            [self.cmds.squeue, "-h", "-w", node_name, "-O", _fmt(*self.NODE_JOB_FIELDS)]
        )
        cols = self.NODE_JOB_COLS
        if rc != 0:  # legacy controllers without --Format suffix support
            rc, out, _err = await run_cmd_safe(
                [self.cmds.squeue, "-h", "-w", node_name, "-o", self.NODE_JOB_BASIC_FMT]
            )
            cols = self.NODE_JOB_BASIC_COLS
        if rc != 0:
            return []

        jobs: list[dict[str, Any]] = []
        for line in out.splitlines():
            parts = _split(line, len(cols))
            if parts is None:
                continue
            row: dict[str, Any] = dict(zip(cols, parts, strict=True))
            row["GPU_COUNT"] = self._parse_gpu_count(row.get("TRES", ""))
            jobs.append(row)
        return jobs

    async def get_job_script(self, jobid: str) -> str:
        """Get the batch script for a job."""
        if self._mock_mode:
            return f"#!/bin/bash\n#SBATCH --job-name=mock_job_{jobid}\necho 'Mock script'"
        rc, out, _err = await run_cmd_safe([self.cmds.scontrol, "write", "batch_script", jobid, "-"], timeout=15)
        if rc == 0 and out.strip():
            return out.rstrip()
        return "(No script stored by controller)"

    async def get_job_output_paths(self, jobid: str, detail: str | None = None) -> tuple[str, str]:
        """Get (stdout_path, stderr_path) for a job; `detail` may be a pre-fetched `scontrol show job`."""
        if self._mock_mode:
            return "/tmp/mock_stdout.txt", "/tmp/mock_stderr.txt"

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

    async def get_job_output(self, jobid: str, full: bool = False, detail: str | None = None) -> tuple[str, str]:
        """Get the tail of stdout and stderr for a job (20 lines, or 100 when `full`)."""
        stdout_file, stderr_file = await self.get_job_output_paths(jobid, detail)
        if not stdout_file and not stderr_file:
            return "", ""

        lines = 100 if full else 20
        stdout_content, stderr_content = await asyncio.gather(
            self._read_output_file(stdout_file, lines),
            self._read_output_file(stderr_file, lines),
        )
        return stdout_content, stderr_content

    async def _read_output_file(self, filepath: str, lines: int = 20) -> str:
        """Tail an output file; carriage-return progress bars are collapsed to their last state."""
        if not filepath or filepath == "/dev/null":
            return ""
        try:
            rc, out, err = await run_cmd_safe(["tail", "-n", str(lines), filepath], timeout=5)
            if rc == 0:
                return collapse_carriage_returns(out)
            return f"Could not read file: {err.strip()}"
        except Exception as e:
            return f"Error reading file: {e}"

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
        """Parse GPU type from TRES field (empty when the TRES carries no type)."""
        if not tres_field or tres_field == "N/A":
            return ""
        match = self.GPU_TYPE_PATTERN.search(tres_field)
        if not match:
            return ""
        gpu_type = match.group(1).upper()
        for known in ("H100", "A100", "V100"):
            if known in gpu_type:
                return known
        return gpu_type

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
        return match.group(1) if match else ""

    def extract_mem_from_tres(self, tres_field: str) -> str:
        """Extract memory from TRES field."""
        if not tres_field or tres_field == "N/A":
            return ""
        match = self.MEM_PATTERN.search(tres_field)
        return match.group(1) if match else ""

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

    def _mock_jobs(self) -> list[dict[str, Any]]:
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
                "Reason": "None",
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
                "NodeList": "",
                "Reason": "Resources",
                "GPU_COUNT": "2",
                "GPU_TYPE": "A100",
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
                "Reason": "None",
                "GPU_COUNT": "0",
                "GPU_TYPE": "",
            },
        ]

    def _mock_nodes(self) -> list[dict[str, Any]]:
        """Return mock node data for testing without Slurm."""
        return [
            {
                "NODE": "DGX-H100-1",
                "PARTITION": "h100",
                "STATE": "mixed",
                "AVAIL": "up",
                "CPUS_STATE": "64/160/0/224",  # Alloc/Idle/Other/Total
                "MEM": "1960740",
                "ALLOC_MEM": "819200",
                "GRES": "gpu:h100:8",
                "GRES_USED": "gpu:h100:4",
            },
            {
                "NODE": "DGX-H100-2",
                "PARTITION": "h100",
                "STATE": "idle",
                "AVAIL": "up",
                "CPUS_STATE": "0/224/0/224",
                "MEM": "1960740",
                "ALLOC_MEM": "0",
                "GRES": "gpu:8(S:0-1)",
                "GRES_USED": "gpu:(null):0(IDX:N/A)",
            },
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
        """Ratio of time used to time limit, or -1 if not computable (e.g. UNLIMITED)."""
        used_sec = SlurmClient.parse_time_to_seconds(time_used)
        limit_sec = SlurmClient.parse_time_to_seconds(time_limit)
        if used_sec < 0 or limit_sec <= 0:
            return -1.0
        return used_sec / limit_sec

    async def cancel_job(self, jobid: str) -> tuple[bool, str]:
        """Cancel a job using scancel. Returns (success, message)."""
        if self._mock_mode:
            return True, f"[Mock] Job {jobid} cancelled successfully"

        rc, _, err = await run_cmd_safe([self.cmds.scancel, jobid])
        if rc == 0:
            return True, f"Job {jobid} cancelled successfully"
        return False, err.strip() or "Unknown error"


def collapse_carriage_returns(text: str) -> str:
    """Emulate a terminal for `\\r`: keep only the last segment of each line."""
    if "\r" not in text:
        return text
    # rstrip first so CRLF line endings are not mistaken for an empty final segment
    return "\n".join(line.rstrip("\r").rsplit("\r", 1)[-1] for line in text.split("\n"))
