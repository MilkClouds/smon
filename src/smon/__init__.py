"""smon - Slurm Monitor Dashboard."""

# Version is managed by hatch-vcs from Git tags
try:
    from ._version import __version__
except ImportError:  # pragma: no cover
    # Fallback for editable installs without build
    try:
        from importlib.metadata import version

        __version__ = version("smon")
    except Exception:
        __version__ = "0.0.0.dev0"

from .main import main

__all__ = ["main"]
