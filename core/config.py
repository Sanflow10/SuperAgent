import os
from pathlib import Path

import yaml

from core.paths import CONFIG_FILE


class Config:
    """
    Precedence: environment variable > YAML value > explicit default.
    """

    def __init__(self, path: Path = CONFIG_FILE):
        self.path = path

        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                self.data = yaml.safe_load(handle) or {}
        else:
            self.data = {}

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict):
                return default
            value = value.get(key)
            if value is None:
                return default
        return value

    def env_int(self, env_name: str, *keys, default: int) -> int:
        raw = os.getenv(env_name)
        if raw is not None and raw.strip():
            try:
                return int(raw)
            except ValueError:
                pass
        return int(self.get(*keys, default=default))

    def env_float(self, env_name: str, *keys, default: float) -> float:
        raw = os.getenv(env_name)
        if raw is not None and raw.strip():
            try:
                return float(raw)
            except ValueError:
                pass
        return float(self.get(*keys, default=default))

    def env_bool(self, env_name: str, *keys, default: bool) -> bool:
        raw = os.getenv(env_name)
        value = raw if (raw is not None and raw.strip()) else self.get(*keys, default=default)
        return str(value).lower() in {"1", "true", "yes", "on"}

    def env_str(self, env_name: str, *keys, default: str) -> str:
        raw = os.getenv(env_name)
        if raw is not None and raw.strip():
            return raw
        return str(self.get(*keys, default=default))

    def model(self, role: str) -> str:
        return self.env_str(
            f"{role.upper()}_MODEL", "models", role, default="qwen3:8b"
        )

    def temperature(self, role: str) -> float:
        env_name = f"{role.upper()}_TEMPERATURE"
        raw = os.getenv(env_name)
        if raw is not None and raw.strip():
            return float(raw)
        return float(self.get("temperatures", role, default=0.2))
