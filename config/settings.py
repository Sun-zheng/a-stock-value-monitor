from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _path(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default))
    return value if value.is_absolute() else PROJECT_ROOT / value


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    timezone: str = os.getenv("TIMEZONE", "Asia/Shanghai")
    run_time: str = os.getenv("RUN_TIME", "14:10")
    email_to: str = os.getenv("EMAIL_TO", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    smtp_host: str = os.getenv("EMAIL_SMTP_HOST", "")
    smtp_port: int = int(os.getenv("EMAIL_SMTP_PORT", "465") or 465)
    smtp_username: str = os.getenv("EMAIL_USERNAME", "")
    smtp_password: str = os.getenv("EMAIL_PASSWORD", "")
    smtp_use_ssl: bool = os.getenv("EMAIL_USE_SSL", "true").lower() == "true"
    lark_cli: str = os.getenv("LARK_CLI", "lark-cli")
    lark_table_name: str = os.getenv(
        "LARK_TABLE_NAME", "A股主板低估股票每日分析记录"
    )
    lark_config_path: Path = _path(
        "LARK_TABLE_CONFIG_PATH", "data/feishu_table.json"
    )
    calendar_cache_path: Path = PROJECT_ROOT / "data/trading_calendar_cache.json"
    reports_dir: Path = PROJECT_ROOT / "reports"
    logs_dir: Path = PROJECT_ROOT / "logs"
    max_financial_candidates: int = int(
        os.getenv("MAX_FINANCIAL_CANDIDATES", "20")
    )

    def ensure_directories(self) -> None:
        for path in (self.reports_dir, self.logs_dir, self.lark_config_path.parent):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
