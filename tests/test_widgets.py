"""Tests for smon.widgets module."""

import pytest

from smon.widgets import Filter


class TestFilter:
    """Tests for the Filter class."""

    def test_filter_empty_by_default(self, filter_instance: Filter) -> None:
        """Test that filter has no active filters by default."""
        assert filter_instance.user is None
        assert filter_instance.partition is None
        assert filter_instance.state is None
        assert filter_instance.text == ""  # text defaults to empty string

    def test_filter_jobs_by_user(self, filter_instance: Filter, sample_jobs: list[dict]) -> None:
        """Test filtering jobs by user."""
        filter_instance.user = "alice"
        filtered = filter_instance.apply_jobs(sample_jobs)
        assert len(filtered) == 2
        assert all(j["USER"] == "alice" for j in filtered)

    def test_filter_jobs_by_partition(self, filter_instance: Filter, sample_jobs: list[dict]) -> None:
        """Test filtering jobs by partition."""
        filter_instance.partition = "gpu"
        filtered = filter_instance.apply_jobs(sample_jobs)
        assert len(filtered) == 2
        assert all(j["PARTITION"] == "gpu" for j in filtered)

    def test_filter_jobs_by_state(self, filter_instance: Filter, sample_jobs: list[dict]) -> None:
        """Test filtering jobs by state."""
        filter_instance.state = "RUNNING"
        filtered = filter_instance.apply_jobs(sample_jobs)
        assert len(filtered) == 1
        assert filtered[0]["STATE"] == "RUNNING"

    def test_filter_jobs_by_text(self, filter_instance: Filter, sample_jobs: list[dict]) -> None:
        """Test filtering jobs by text search."""
        filter_instance.text = "train"
        filtered = filter_instance.apply_jobs(sample_jobs)
        assert len(filtered) == 1
        assert "train" in filtered[0]["NAME"]

    def test_filter_jobs_by_text_case_insensitive(self, filter_instance: Filter, sample_jobs: list[dict]) -> None:
        """Test that text filter is case insensitive."""
        filter_instance.text = "TRAIN"
        filtered = filter_instance.apply_jobs(sample_jobs)
        assert len(filtered) == 1

    def test_filter_jobs_combined(self, filter_instance: Filter, sample_jobs: list[dict]) -> None:
        """Test combining multiple filters."""
        filter_instance.user = "alice"
        filter_instance.partition = "gpu"
        filtered = filter_instance.apply_jobs(sample_jobs)
        assert len(filtered) == 2

    def test_filter_nodes_by_text(self, filter_instance: Filter, sample_nodes: list[dict]) -> None:
        """Test filtering nodes by text."""
        filter_instance.text = "node01"
        filtered = filter_instance.apply_nodes(sample_nodes)
        assert len(filtered) == 1
        assert filtered[0]["NODE"] == "node01"

    def test_filter_nodes_by_partition(self, filter_instance: Filter, sample_nodes: list[dict]) -> None:
        """Test filtering nodes by partition."""
        filter_instance.partition = "cpu"
        filtered = filter_instance.apply_nodes(sample_nodes)
        assert len(filtered) == 1
        assert filtered[0]["PARTITION"] == "cpu"

    def test_filter_no_match(self, filter_instance: Filter, sample_jobs: list[dict]) -> None:
        """Test filtering with no matches."""
        filter_instance.user = "nonexistent"
        filtered = filter_instance.apply_jobs(sample_jobs)
        assert len(filtered) == 0

    def test_filter_empty_list(self, filter_instance: Filter) -> None:
        """Test filtering empty list."""
        filter_instance.user = "alice"
        filtered = filter_instance.apply_jobs([])
        assert len(filtered) == 0
