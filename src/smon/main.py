"""Command line entry point for smon."""

import argparse
import os

from .app import SlurmDashboard
from .config import Config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments. Unset options fall back to ~/.config/smon/config.json."""
    p = argparse.ArgumentParser(description="Slurm Dashboard (Textual)")
    p.add_argument("--refresh", type=float, default=None, help="Auto-refresh interval in seconds (default: 5)")
    p.add_argument("--user", type=str, default=None, help="Default user filter")
    p.add_argument("--me", action="store_true", help="Filter jobs for current user (alias for --user $USER)")
    p.add_argument("--partition", "-p", type=str, default=None, help="Default partition filter")
    p.add_argument("--state", type=str, default=None, help="Default job state filter (e.g. RUNNING)")
    p.add_argument("--theme", choices=["dark", "light"], default=None, help="Colour theme")
    p.add_argument("--gpustat-web", type=str, default=None, help="gpustat-web URL (e.g., http://10.50.0.111:48109/)")
    p.add_argument("--mock", action="store_true", help="Use mock data (for development/testing without Slurm)")
    return p.parse_args(argv)


def build_app(args: argparse.Namespace, config: Config) -> SlurmDashboard:
    """Merge CLI arguments over the config file and construct the app."""
    user_filter = args.user
    if args.me:
        user_filter = os.getenv("USER") or os.getenv("USERNAME") or "unknown"
    if user_filter is None:
        user_filter = config.user_filter

    return SlurmDashboard(
        refresh_sec=args.refresh if args.refresh is not None else config.refresh_sec,
        user=user_filter,
        partition=args.partition if args.partition is not None else config.partition_filter,
        state=args.state if args.state is not None else config.state_filter,
        theme=args.theme or config.theme,
        gpustat_web_url=args.gpustat_web or config.gpustat_web_url,
        mock_mode=args.mock,
    )


def main() -> None:
    """Main entry point for smon."""
    build_app(parse_args(), Config.load()).run()


if __name__ == "__main__":
    main()
