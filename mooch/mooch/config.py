"""Loads config.yaml and .env into one object the rest of the app reads."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv


class ConfigError(Exception):
    pass


def _expand(p: str) -> Path:
    return Path(os.path.expandvars(str(p))).expanduser()


@dataclass
class Config:
    raw: dict
    path: Path

    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("America/New_York"))
    lookahead_days: int = 14
    confidence_threshold: float = 0.55
    data_dir: Path = field(default_factory=lambda: Path.home() / ".mooch")

    anthropic_key: str | None = None
    imap_password: str | None = None
    ig_password: str | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mooch.db"

    @property
    def report_path(self) -> Path:
        return self.data_dir / "report.html"

    def section(self, name: str) -> dict:
        return self.raw.get(name) or {}

    def enabled(self, name: str) -> bool:
        return bool(self.section(name).get("enabled"))


def load(config_path: str | Path | None = None, env_path: str | Path | None = None) -> Config:
    root = Path(__file__).resolve().parent.parent

    load_dotenv(_expand(env_path) if env_path else root / ".env")

    cfg_path = _expand(config_path) if config_path else root / "config.yaml"
    if not cfg_path.exists():
        raise ConfigError(
            f"No config at {cfg_path}. Copy config.example.yaml to config.yaml and edit it."
        )

    raw = yaml.safe_load(cfg_path.read_text()) or {}

    try:
        tz = ZoneInfo(raw.get("timezone", "America/New_York"))
    except Exception as exc:
        raise ConfigError(f"Unknown timezone {raw.get('timezone')!r}: {exc}") from exc

    data_dir = _expand(raw.get("data_dir", "~/.mooch"))
    data_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        raw=raw,
        path=cfg_path,
        timezone=tz,
        lookahead_days=int(raw.get("lookahead_days", 14)),
        confidence_threshold=float(raw.get("confidence_threshold", 0.55)),
        data_dir=data_dir,
        anthropic_key=os.getenv("ANTHROPIC_API_KEY"),
        imap_password=os.getenv("MOOCH_IMAP_PASSWORD"),
        ig_password=os.getenv("MOOCH_IG_PASSWORD"),
    )
