from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
SAMPLE_DATA_DIR = BASE_DIR.parent / "基金净值数据"
DEFAULT_DB_PATH = DATA_DIR / "fof_nav.db"


def load_env_file(env_path: Path | None = None) -> None:
    path = env_path or (BASE_DIR / ".env")
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


@dataclass
class MailConfig:
    provider: str = field(default_factory=lambda: os.getenv("FOF_MAIL_PROVIDER", "qq"))
    email_address: str = field(default_factory=lambda: os.getenv("FOF_MAIL_ADDRESS", ""))
    password: str = field(default_factory=lambda: os.getenv("FOF_MAIL_PASSWORD", ""))
    imap_host: str = field(default_factory=lambda: os.getenv("FOF_MAIL_IMAP_HOST", "imap.qq.com"))
    imap_port: int = field(default_factory=lambda: int(os.getenv("FOF_MAIL_IMAP_PORT", "993")))
    folder: str = field(default_factory=lambda: os.getenv("FOF_MAIL_FOLDER", "INBOX"))
    search_keyword: str = field(default_factory=lambda: os.getenv("FOF_MAIL_SEARCH_KEYWORD", ""))
    poll_minutes: int = field(default_factory=lambda: int(os.getenv("FOF_MAIL_POLL_MINUTES", "5")))
    use_ssl: bool = field(
        default_factory=lambda: os.getenv("FOF_MAIL_USE_SSL", "true").lower() in {"1", "true", "yes", "on"}
    )
    initial_sync_limit: int = field(default_factory=lambda: int(os.getenv("FOF_MAIL_INITIAL_SYNC_LIMIT", "300")))
    overlap_uids: int = field(default_factory=lambda: int(os.getenv("FOF_MAIL_OVERLAP_UIDS", "300")))

    @property
    def configured(self) -> bool:
        return bool(self.email_address and self.password)


@dataclass
class AppConfig:
    secret_key: str = field(default_factory=lambda: os.getenv("FOF_SECRET_KEY", "fof-nav-dev"))
    database_url: str = field(default_factory=lambda: f"sqlite:///{os.getenv('FOF_DB_PATH', DEFAULT_DB_PATH)}")
    bootstrap_samples: bool = field(
        default_factory=lambda: os.getenv("FOF_BOOTSTRAP_SAMPLES", "true").lower() in {"1", "true", "yes", "on"}
    )
    sample_data_dir: Path = field(default_factory=lambda: Path(os.getenv("FOF_SAMPLE_DATA_DIR", SAMPLE_DATA_DIR)))
    risk_free_rate: float = field(default_factory=lambda: float(os.getenv("FOF_RISK_FREE_RATE", "0.015")))
    annual_trading_days: int = field(default_factory=lambda: int(os.getenv("FOF_ANNUAL_TRADING_DAYS", "252")))
    weekly_periods: int = field(default_factory=lambda: int(os.getenv("FOF_WEEKLY_PERIODS", "52")))
    access_code: str = field(default_factory=lambda: os.getenv("FOF_ACCESS_CODE", "").strip())
    portfolio_seed_json: str = field(default_factory=lambda: os.getenv("FOF_PORTFOLIO_JSON", "").strip())
    dashboard_cache_seconds: int = field(default_factory=lambda: int(os.getenv("FOF_DASHBOARD_CACHE_SECONDS", "30")))


def ensure_data_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
