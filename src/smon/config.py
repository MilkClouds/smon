"""Configuration management for smon."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Config:
    """User configuration settings (~/.config/smon/config.json). CLI flags override these."""

    refresh_sec: float = 5.0
    user_filter: str | None = None
    partition_filter: str | None = None
    state_filter: str | None = None
    theme: str = "dark"
    gpustat_web_url: str | None = None  # e.g., "http://10.50.0.111:48109/"

    @classmethod
    def config_path(cls) -> Path:
        """Get the configuration file path."""
        config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "smon"
        return config_dir / "config.json"

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from file."""
        config_path = cls.config_path()
        if config_path.exists():
            try:
                with open(config_path) as f:
                    data = json.load(f)
                return cls(
                    refresh_sec=data.get("refresh_sec", 5.0),
                    user_filter=data.get("user_filter"),
                    partition_filter=data.get("partition_filter"),
                    state_filter=data.get("state_filter"),
                    theme=data.get("theme", "dark"),
                    gpustat_web_url=data.get("gpustat_web_url"),
                )
            except (json.JSONDecodeError, OSError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        """Save configuration to file."""
        config_path = self.config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(config_path, "w") as f:
                json.dump(asdict(self), f, indent=2)
        except OSError:
            pass
