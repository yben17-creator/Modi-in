"""Configuration: config.yaml + environment variables (.env).

Secrets (API keys) are read only from the environment / .env file, never from config.yaml.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    raw: dict[str, Any]
    sec_user_agent: str
    finnhub_key: str | None
    massive_key: str | None
    enable_yfinance: bool
    tiingo_key: str | None = None
    telegram_token: str | None = None
    telegram_chat: str | None = None
    smtp: dict[str, str | None] = field(default_factory=dict)

    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    @property
    def db_path(self) -> Path:
        p = Path(self.get("cache.path", "data/evi.sqlite"))
        return p if p.is_absolute() else ROOT / p

    def status(self) -> dict[str, bool]:
        return {
            "SEC EDGAR": bool(self.sec_user_agent and "@" in self.sec_user_agent),
            "Finnhub": bool(self.finnhub_key),
            "Tiingo": bool(self.tiingo_key),
            "Massive": bool(self.massive_key),
            "Yahoo (yfinance, לא רשמי)": self.enable_yfinance,
        }


_SETTINGS: Settings | None = None


def load_settings(config_path: Path | None = None, reload: bool = False) -> Settings:
    global _SETTINGS
    if _SETTINGS is not None and not reload:
        return _SETTINGS
    _load_dotenv(ROOT / ".env")
    cfg_file = config_path or ROOT / "config.yaml"
    raw = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}
    _SETTINGS = Settings(
        raw=raw or {},
        sec_user_agent=os.environ.get("SEC_USER_AGENT", "").strip(),
        finnhub_key=os.environ.get("FINNHUB_API_KEY", "").strip() or None,
        massive_key=os.environ.get("MASSIVE_API_KEY", "").strip() or None,
        enable_yfinance=_env_bool("ENABLE_YFINANCE", False),
        tiingo_key=os.environ.get("TIINGO_API_KEY", "").strip() or None,
        telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN") or None,
        telegram_chat=os.environ.get("TELEGRAM_CHAT_ID") or None,
        smtp={k: os.environ.get(k) for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "ALERT_EMAIL_TO")},
    )
    return _SETTINGS
