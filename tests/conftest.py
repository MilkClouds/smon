"""Pytest fixtures for smon tests."""

import pytest

from smon.slurm_client import SlurmClient
from smon.widgets import Filter


@pytest.fixture
def slurm_client() -> SlurmClient:
    """Create a SlurmClient instance for testing."""
    return SlurmClient()


@pytest.fixture
def filter_instance() -> Filter:
    """Create a Filter instance for testing."""
    return Filter()


@pytest.fixture
def sample_jobs() -> list[dict]:
    """Sample job data for testing."""
    return [
        {
            "JOBID": "12345",
            "USER": "alice",
            "USERNAME": "alice",
            "STATE": "RUNNING",
            "PARTITION": "gpu",
            "CPUS": "8",
            "MEM": "32G",
            "TIME": "1:00:00",
            "NAME": "train_model",
            "NODELIST(REASON)": "node01",
            "TRES": "cpu=8,mem=32G,gres/gpu=2",
            "GPU_COUNT": "2",
        },
        {
            "JOBID": "12346",
            "USER": "bob",
            "USERNAME": "bob",
            "STATE": "PENDING",
            "PARTITION": "cpu",
            "CPUS": "4",
            "MEM": "16G",
            "TIME": "0:00:00",
            "NAME": "preprocess",
            "NODELIST(REASON)": "(Resources)",
            "TRES": "cpu=4,mem=16G",
            "GPU_COUNT": "0",
        },
        {
            "JOBID": "12347",
            "USER": "alice",
            "USERNAME": "alice",
            "STATE": "COMPLETED",
            "PARTITION": "gpu",
            "CPUS": "16",
            "MEM": "64G",
            "TIME": "2:30:00",
            "NAME": "inference",
            "NODELIST(REASON)": "node[02-03]",
            "TRES": "cpu=16,mem=64G,gres/gpu=4",
            "GPU_COUNT": "4",
        },
    ]


@pytest.fixture
def sample_nodes() -> list[dict]:
    """Sample node data for testing."""
    return [
        {
            "NODE": "node01",
            "STATE": "idle",
            "AVAIL": "up",
            "GRES": "gpu:a100:4",
            "CPUS": "64",
            "MEM": "512000",
            "PARTITION": "gpu",
        },
        {
            "NODE": "node02",
            "STATE": "alloc",
            "AVAIL": "up",
            "GRES": "gpu:h100:8",
            "CPUS": "128",
            "MEM": "1024000",
            "PARTITION": "gpu",
        },
        {
            "NODE": "cpu01",
            "STATE": "idle",
            "AVAIL": "up",
            "GRES": "(null)",
            "CPUS": "32",
            "MEM": "256000",
            "PARTITION": "cpu",
        },
    ]

