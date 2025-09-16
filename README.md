# smon

A terminal user interface (TUI) for monitoring Slurm clusters. Built with Textual for DGX H100 clusters.

> **⚠️ Development Notice**: This project is mainly implemented by LLM (Sonnet 4/GPT-4) and is not complete, has bugs. Contributions are welcome, including major changes.

## Features

- Job monitoring with live updates
- Node status display with GPU availability
- GPU count display with partition info
- Script viewer with syntax highlighting
- Output tracking (stdout/stderr)
- Search and filtering
- Tabbed TUI interface
- Keyboard shortcuts

## Installation

### Using uvx (recommended)

```sh
uvx --from git+https://github.com/MilkClouds/smon.git smon
```

### Using pip

```sh
pip install git+https://github.com/MilkClouds/smon.git
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
smon --partition gpu           # Filter jobs by partition
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit application |
| `r` | Refresh data |
| `/` | Focus search input |
| `f` | Show filter status |
| `s` | Open script modal for selected job |
| `o` | Open output modal for selected job |
| `t` | Toggle real-time output refresh |
| `Ctrl+R` | Refresh output in current tab |

## TUI Interface

### Jobs Tab
- Job information: JobID, User, State, Partition, Resources
- GPU/CPU/memory usage and timing
- Select job to view details, script, and output

### Script Tab
- Shows script for selected job
- Bash syntax highlighting
- Modal view with `s` key

### Output Tab
- stdout/stderr for selected jobs
- Real-time refresh toggle (`t`)
- Manual refresh (`Ctrl+R`)

### Nodes Tab
- Node status and availability
- GPU/CPU/memory per node

## Requirements

- Python ≥ 3.11
- Slurm cluster with `squeue`, `sinfo`, and `scontrol` commands
- Terminal with color support

## Dependencies

- [Textual](https://github.com/Textualize/textual) - TUI framework
- [Rich](https://github.com/Textualize/rich) - Text formatting

## Contributing

This TUI project is primarily implemented using LLM assistance (Sonnet 4/GPT-4) and is incomplete with known bugs. Contributions are welcome:

- Bug fixes
- Feature improvements
- Code refactoring
- Documentation
- Major changes
- Testing

Feel free to open issues or submit pull requests.
