# smon

<img width="1348" height="763" alt="image" src="https://github.com/user-attachments/assets/81379b1e-3547-42a5-bde1-725c51b521f6" />

A terminal user interface (TUI) for monitoring Slurm clusters. Built with [Textual](https://github.com/Textualize/textual) for DGX H100 clusters.

## Features

- Job monitoring with live updates
- Node status display with GPU availability
- GPU count display with partition info
- Script viewer with syntax highlighting
- Output tracking (stdout/stderr)
- Search and filtering
- Tabbed TUI interface
- Keyboard shortcuts
- [gpustat-web](https://github.com/wookayin/gpustat-web) integration for real-time GPU monitoring

## Installation

The package is published on PyPI as [`smon-tui`](https://pypi.org/project/smon-tui/); the command it installs is `smon`.

### Using `uvx`/`uv tool` (recommended)

```sh
# 1. Run without installing
$ uvx --from smon-tui smon

# 2. Install as a tool
$ uv tool install smon-tui
$ smon
```

### Using pip

```sh
$ pip install smon-tui
$ smon
```

### From git (latest main)

```sh
$ uv tool install git+https://github.com/MilkClouds/smon.git
```

## Usage

### Basic Usage

```sh
smon
```

### Command Line Options

```sh
smon --help                    # Show help
smon --refresh 10              # Set refresh interval to 10 seconds
smon --user alice              # Filter jobs by user
smon --me                      # Filter jobs by the current user
smon --partition gpu           # Filter jobs and nodes by partition
smon --state RUNNING           # Default job state filter
smon --theme light             # Colour theme (dark/light)
smon --gpustat-web URL         # Enable gpustat-web integration
smon --mock                    # Demo mode without a Slurm cluster
```

Every option can also be set in `~/.config/smon/config.json`
(`refresh_sec`, `user_filter`, `partition_filter`, `state_filter`, `theme`, `gpustat_web_url`);
command line flags take precedence.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit application |
| `r` | Refresh data now |
| `1` / `2` | Switch to Jobs / Nodes tab |
| `/` | Focus the search box (filters as you type; `Esc` returns to the table) |
| `Enter` | Load details, script and output of the selected job / show jobs on the selected node |
| Click header | Sort the jobs table by that column (click again to reverse) |
| `o` | Open the selected job's stdout/stderr in `bat`/`less` |
| `t` | Toggle real-time output refresh |
| `c` | Cancel the selected job (asks for confirmation) |
| `y` | Copy the selected job ID to the clipboard |
| `+` / `-` | Increase / decrease the refresh interval |
| `T` | Toggle dark/light theme |

## TUI Interface

### Jobs Tab
- Left: job table (JobID, user, state, partition, CPUs, memory, GPUs, time used vs. limit, nodes)
- Right: `scontrol show job` details, the batch script with syntax highlighting, and the tail of stdout/stderr
- The table updates in place on each refresh, so scrolling, sorting and the selected row are preserved

### Nodes Tab
- Node status, GPU allocation bar, CPU and memory usage per node
- `Enter` on a node lists the jobs running on it
- gpustat-web integration (side-by-side view)

## gpustat-web Integration

smon can display real-time GPU status from [gpustat-web](https://github.com/wookayin/gpustat-web) alongside the Slurm node information.

### Setup

1. Make sure gpustat-web is running on your cluster (e.g., `http://10.50.0.111:48109/`)

2. Run smon with the `--gpustat-web` option:
   ```sh
   smon --gpustat-web http://10.50.0.111:48109/
   ```

3. Or add to config file (`~/.config/smon/config.json`):
   ```json
   {
     "gpustat_web_url": "http://10.50.0.111:48109/"
   }
   ```

The Nodes tab will show the Slurm node table on the left and live GPU status from gpustat-web on the right.

## Requirements

- Python ≥ 3.11
- Slurm cluster with `squeue`, `sinfo`, and `scontrol` commands
- Terminal with color support

## Dependencies

- [Textual](https://github.com/Textualize/textual) - TUI framework
- [Rich](https://github.com/Textualize/rich) - Text formatting

## Related projects

- https://github.com/wjwei-handsome/Slurmer

## Contributing

Issues and pull requests are welcome.
