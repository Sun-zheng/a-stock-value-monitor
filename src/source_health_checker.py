from __future__ import annotations

import importlib.util
from pathlib import Path

from src.data_source_manager import DataSourceManager
from src.lark_bitable_client import LarkBitableClient


def health_check(settings) -> dict:
    result = {
        "Tushare依赖": importlib.util.find_spec("tushare") is not None,
        "TUSHARE_TOKEN已配置": bool(__import__("os").getenv("TUSHARE_TOKEN")),
        "缓存目录": str(settings.project_root / "data" / "cache"),
    }
    manager = DataSourceManager(settings.project_root)
    try:
        universe, _ = manager.build_universe(force=True)
        result["Tushare是否可用"] = True
        result["Tushare股票池数量"] = len(universe)
    except Exception as exc:
        result["Tushare是否可用"] = False
        result["Tushare错误"] = f"{type(exc).__name__}: {exc}"
    lark = LarkBitableClient(settings.lark_cli, settings.lark_config_path)
    result["飞书"] = lark.check()[1]
    result["SMTP配置完整"] = all([
        settings.email_from, settings.smtp_host,
        settings.smtp_username, settings.smtp_password,
    ])
    result["健康"] = bool(
        result["Tushare依赖"] and result.get("Tushare是否可用")
        and result["SMTP配置完整"]
    )
    return result
