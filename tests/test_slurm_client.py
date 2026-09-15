"""Tests for smon.slurm_client module."""

import pytest

from smon.slurm_client import SlurmClient, SlurmCommands


class TestSlurmCommands:
    """Tests for SlurmCommands dataclass."""

    def test_default_commands(self) -> None:
        """Test default command values."""
        cmds = SlurmCommands()
        assert cmds.squeue == "squeue"
        assert cmds.sinfo == "sinfo"
        assert cmds.scontrol == "scontrol"

    def test_custom_commands(self) -> None:
        """Test custom command values."""
        cmds = SlurmCommands(squeue="/usr/bin/squeue", sinfo="/usr/bin/sinfo")
        assert cmds.squeue == "/usr/bin/squeue"
        assert cmds.sinfo == "/usr/bin/sinfo"


class TestSlurmClientMockMode:
    """Tests for SlurmClient mock mode behavior."""

    def test_mock_mode_does_not_raise(self) -> None:
        """Test that mock mode does not raise error when Slurm is unavailable."""
        # Should not raise even if Slurm commands don't exist
        client = SlurmClient(mock_mode=True)
        assert client._mock_mode is True

    def test_non_mock_mode_raises_without_slurm(self) -> None:
        """Test that non-mock mode raises error when Slurm is unavailable."""
        # Use non-existent command paths to simulate missing Slurm
        cmds = SlurmCommands(
            squeue="/nonexistent/squeue",
            sinfo="/nonexistent/sinfo",
            scontrol="/nonexistent/scontrol",
        )
        with pytest.raises(RuntimeError, match="Slurm commands not found"):
            SlurmClient(cmds=cmds, mock_mode=False)


class TestSlurmClientNodeGpuParsing:
    """Tests for node GPU parsing methods."""

    def test_parse_node_gpu_info_with_type(self, slurm_client: SlurmClient) -> None:
        """Test GPU info parsing from node GRES with type specified."""
        assert slurm_client.parse_node_gpu_info("gpu:a100:4") == "4"
        assert slurm_client.parse_node_gpu_info("gpu:h100:8") == "8"
        assert slurm_client.parse_node_gpu_info("gpu:v100:2") == "2"

    def test_parse_node_gpu_info_without_type(self, slurm_client: SlurmClient) -> None:
        """Test GPU info parsing without type specified."""
        assert slurm_client.parse_node_gpu_info("gpu:4") == "4"
        assert slurm_client.parse_node_gpu_info("gpu:1") == "1"

    def test_parse_node_gpu_info_null_or_empty(self, slurm_client: SlurmClient) -> None:
        """Test GPU info parsing with null or empty values."""
        assert slurm_client.parse_node_gpu_info("(null)") == "0"
        assert slurm_client.parse_node_gpu_info("") == "0"


class TestSlurmClientTresParsing:
    """Tests for TRES parsing methods."""

    def test_extract_cpus_from_tres(self, slurm_client: SlurmClient) -> None:
        """Test CPU extraction from TRES string."""
        assert slurm_client.extract_cpus_from_tres("cpu=16,mem=64G,gres/gpu=4") == "16"
        assert slurm_client.extract_cpus_from_tres("cpu=8,mem=32G") == "8"
        assert slurm_client.extract_cpus_from_tres("cpu=128") == "128"

    def test_extract_cpus_from_tres_missing(self, slurm_client: SlurmClient) -> None:
        """Test CPU extraction when not present."""
        assert slurm_client.extract_cpus_from_tres("mem=64G,gres/gpu=4") == ""
        assert slurm_client.extract_cpus_from_tres("") == ""

    def test_extract_mem_from_tres(self, slurm_client: SlurmClient) -> None:
        """Test memory extraction from TRES string."""
        assert slurm_client.extract_mem_from_tres("cpu=16,mem=64G,gres/gpu=4") == "64G"
        assert slurm_client.extract_mem_from_tres("cpu=8,mem=128M") == "128M"
        assert slurm_client.extract_mem_from_tres("mem=256G") == "256G"

    def test_extract_mem_from_tres_missing(self, slurm_client: SlurmClient) -> None:
        """Test memory extraction when not present."""
        assert slurm_client.extract_mem_from_tres("cpu=16,gres/gpu=4") == ""
        assert slurm_client.extract_mem_from_tres("") == ""


class TestSlurmClientNodeParsing:
    """Tests for node parsing methods."""

    def test_count_nodes_simple(self, slurm_client: SlurmClient) -> None:
        """Test counting single nodes."""
        assert slurm_client.count_nodes_from_nodelist("node01") == "1"
        assert slurm_client.count_nodes_from_nodelist("gpu-node") == "1"

    def test_count_nodes_comma_separated(self, slurm_client: SlurmClient) -> None:
        """Test counting comma-separated node list."""
        assert slurm_client.count_nodes_from_nodelist("node01,node02") == "2"
        assert slurm_client.count_nodes_from_nodelist("node01,node02,node03") == "3"

    def test_count_nodes_empty_or_pending(self, slurm_client: SlurmClient) -> None:
        """Test counting with empty or pending states."""
        # Empty returns "0" in current implementation
        assert slurm_client.count_nodes_from_nodelist("") == "0"
        # Pending reasons return "0"
        assert slurm_client.count_nodes_from_nodelist("Resources") == "0"
        assert slurm_client.count_nodes_from_nodelist("Priority") == "0"

    def test_combine_nodelist_reason_with_nodelist(self, slurm_client: SlurmClient) -> None:
        """Test combining nodelist with reason when nodelist is present."""
        # When nodelist is present and not a pending reason, return just nodelist
        assert slurm_client.combine_nodelist_reason("node01", "") == "node01"
        assert slurm_client.combine_nodelist_reason("node01", "None") == "node01"

    def test_combine_nodelist_reason_with_reason_only(self, slurm_client: SlurmClient) -> None:
        """Test combining when only reason is present."""
        # When nodelist is empty, return reason (without parentheses per implementation)
        assert slurm_client.combine_nodelist_reason("", "Resources") == "Resources"
        assert slurm_client.combine_nodelist_reason("", "Priority") == "Priority"

    def test_combine_nodelist_reason_pending(self, slurm_client: SlurmClient) -> None:
        """Test combining when nodelist contains pending reason."""
        # When nodelist contains a pending reason keyword, check behavior
        result = slurm_client.combine_nodelist_reason("Resources", "")
        assert result == "Resources"


class TestSlurmClientTimeParsing:
    """Tests for time parsing methods."""

    def test_parse_time_mm_ss(self) -> None:
        """Test parsing MM:SS format."""
        assert SlurmClient.parse_time_to_seconds("05:30") == 5 * 60 + 30

    def test_parse_time_hh_mm_ss(self) -> None:
        """Test parsing HH:MM:SS format."""
        assert SlurmClient.parse_time_to_seconds("02:30:45") == 2 * 3600 + 30 * 60 + 45

    def test_parse_time_d_hh_mm_ss(self) -> None:
        """Test parsing D-HH:MM:SS format."""
        assert SlurmClient.parse_time_to_seconds("1-12:00:00") == 1 * 86400 + 12 * 3600

    def test_parse_time_unlimited(self) -> None:
        """Test parsing UNLIMITED returns -1."""
        assert SlurmClient.parse_time_to_seconds("UNLIMITED") == -1
        assert SlurmClient.parse_time_to_seconds("INVALID") == -1

    def test_parse_time_empty(self) -> None:
        """Test parsing empty string returns -1."""
        assert SlurmClient.parse_time_to_seconds("") == -1

    def test_calculate_time_ratio(self) -> None:
        """Test time ratio calculation."""
        # 30 minutes of 1 hour = 0.5
        assert SlurmClient.calculate_time_ratio("30:00", "01:00:00") == pytest.approx(0.5)

    def test_calculate_time_ratio_unlimited(self) -> None:
        """Test time ratio with unlimited limit returns -1."""
        assert SlurmClient.calculate_time_ratio("30:00", "UNLIMITED") == -1.0


class TestOutputParsing:
    """Tests for `|`-suffixed --Format parsing."""

    def test_split_rejoins_separator_in_trailing_name(self) -> None:
        from smon.slurm_client import _split

        assert _split("1|a|b|", 3) == ["1", "a", "b"]
        assert _split("1|a|we|ird|name|", 3) == ["1", "a", "we|ird|name"]
        assert _split("1|a||", 3) == ["1", "a", ""]
        assert _split("1|a|", 3) is None

    def test_parse_jobs(self, slurm_client: SlurmClient) -> None:
        line = (
            "181830|a100|claude|PENDING|cpu=4,mem=8G,node=1,billing=4|0:00|UNLIMITED|1||"
            "ReqNodeNotAvail, UnavailableNodes:A100-Bumblebee|rfm-dataset-dashboard|\n"
            "204084|h100|jyjung|RUNNING|cpu=96,mem=700G,node=1,billing=96,gres/gpu=8|1:15:24|6:00:00|1|DGX-H100-2|None|ev|x|\n"
        )
        jobs = slurm_client._parse_jobs(line)
        assert [j["JOBID"] for j in jobs] == ["181830", "204084"]
        assert jobs[0]["Reason"] == "ReqNodeNotAvail, UnavailableNodes:A100-Bumblebee"
        assert jobs[0]["NodeList"] == ""
        assert jobs[1]["GPU_COUNT"] == "8"
        assert jobs[1]["NAME"] == "ev|x"

    def test_parse_gpu_type(self, slurm_client: SlurmClient) -> None:
        assert slurm_client._parse_gpu_type("cpu=8,gres/gpu:h100:4") == "H100"
        assert slurm_client._parse_gpu_type("cpu=8,gres/gpu=4") == ""

    def test_collapse_carriage_returns(self) -> None:
        from smon.slurm_client import collapse_carriage_returns

        assert collapse_carriage_returns("plain\nlines") == "plain\nlines"
        assert collapse_carriage_returns("10%\r50%\r100%\ndone") == "100%\ndone"
        assert collapse_carriage_returns("a\r\nb\r\n") == "a\nb\n"
        assert collapse_carriage_returns("10%\r50%\r\nend") == "50%\nend"


class TestSlurmClientLive:
    """Async paths exercised through the mock and through run_cmd_safe."""

    async def test_mock_get_jobs_on_node(self, slurm_client: SlurmClient) -> None:
        jobs = await slurm_client.get_jobs_on_node("DGX-H100-1")
        assert [j["JOBID"] for j in jobs] == ["12345"]

    async def test_missing_output_paths_yield_empty(self, slurm_client: SlurmClient) -> None:
        slurm_client._mock_mode = False
        out, err = await slurm_client.get_job_output("1", detail="JobId=1 StdOut=/dev/null StdErr=/dev/null")
        assert (out, err) == ("", "")
