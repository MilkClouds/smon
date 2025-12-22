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
import os
from typing import List, Optional

from .app import SlurmDashboard
from .config import Config


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    p = argparse.ArgumentParser(description="Slurm Dashboard (Textual)")
    p.add_argument("--refresh", type=float, default=5.0, help="Auto-refresh interval (s)")
    p.add_argument("--user", type=str, default=None, help="Default user filter")
    p.add_argument("--me", action="store_true", help="Filter jobs for current user (alias for --user $USER)")
    p.add_argument("--partition", "-p", type=str, default=None, help="Default partition filter")
    p.add_argument(
        "--gpustat-web",
        type=str,
        default=None,
        help="gpustat-web URL (e.g., http://10.50.0.111:48109/)",
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="Use mock data (for development/testing without Slurm)",
    )
    return p.parse_args(argv)


def main() -> None:
    """Main entry point for smon."""
    args = parse_args()

    # Load config for defaults
    config = Config.load()

    user_filter = args.user
    if args.me:
        user_filter = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    # Use CLI arg if provided, otherwise fall back to config
    gpustat_web_url = args.gpustat_web or config.gpustat_web_url

    app = SlurmDashboard(
        refresh_sec=args.refresh,
        user=user_filter,
        partition=args.partition,
        gpustat_web_url=gpustat_web_url,
        mock_mode=args.mock,
    )
    app.run()


if __name__ == "__main__":
    main()
