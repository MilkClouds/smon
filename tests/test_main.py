"""Tests for smon.main module."""

from smon.main import parse_args


class TestParseArgs:
    """Tests for command line argument parsing."""

    def test_default_args(self) -> None:
        """Test default argument values."""
        args = parse_args([])
        assert args.refresh is None
        assert args.user is None
        assert args.me is False
        assert args.partition is None
        assert args.mock is False

    def test_refresh_arg(self) -> None:
        """Test --refresh argument."""
        args = parse_args(["--refresh", "10.0"])
        assert args.refresh == 10.0

    def test_user_arg(self) -> None:
        """Test --user argument."""
        args = parse_args(["--user", "testuser"])
        assert args.user == "testuser"

    def test_me_flag(self) -> None:
        """Test --me flag."""
        args = parse_args(["--me"])
        assert args.me is True

    def test_partition_arg(self) -> None:
        """Test --partition argument."""
        args = parse_args(["--partition", "gpu"])
        assert args.partition == "gpu"

    def test_partition_short_arg(self) -> None:
        """Test -p short argument for partition."""
        args = parse_args(["-p", "cpu"])
        assert args.partition == "cpu"

    def test_combined_args(self) -> None:
        """Test combining multiple arguments."""
        args = parse_args(["--refresh", "2.5", "--user", "alice", "-p", "gpu"])
        assert args.refresh == 2.5
        assert args.user == "alice"
        assert args.partition == "gpu"

    def test_mock_flag(self) -> None:
        """Test --mock flag."""
        args = parse_args(["--mock"])
        assert args.mock is True


class TestBuildApp:
    """CLI flags override config values; unset flags fall back to config."""

    def test_config_fallback(self) -> None:
        from smon.config import Config
        from smon.main import build_app

        config = Config(refresh_sec=12.0, user_filter="cfguser", partition_filter="h100", theme="light")
        app = build_app(parse_args(["--mock"]), config)
        assert app.refresh_sec == 12.0
        assert app.filter.user == "cfguser"
        assert app.filter.partition == "h100"
        assert app.theme == "textual-light"

    def test_cli_overrides_config(self) -> None:
        from smon.config import Config
        from smon.main import build_app

        config = Config(refresh_sec=12.0, user_filter="cfguser", theme="light")
        app = build_app(parse_args(["--mock", "--refresh", "3", "--user", "cli", "--theme", "dark"]), config)
        assert app.refresh_sec == 3.0
        assert app.filter.user == "cli"
        assert app.theme == "textual-dark"
