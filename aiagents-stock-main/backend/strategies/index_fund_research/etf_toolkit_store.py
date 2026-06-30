from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class ETFToolkitStore:
    def __init__(self, project_root: Path):
        self.root = project_root / "data" / "etf_toolkit"
        self.cache_dir = self.root / "cache"
        self.history_dir = self.root / "history"
        self.index_path = self.history_dir / "index.json"

    def load_cached_result(self, settings: dict) -> dict | None:
        storage = settings.get("storage", {})
        analysis = settings.get("analysis", {})
        if not storage.get("cache_enabled", True) or not storage.get("reuse_cached_result", True):
            return None
        path = self.cache_dir / f"{self.cache_key(settings)}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        created_at = _parse_time(payload.get("cached_at"))
        if not created_at:
            return None
        policy = str(storage.get("cache_policy", "same_day"))
        if policy == "ttl":
            ttl = int(analysis.get("cache_ttl_minutes", 30))
            if datetime.now() - created_at > timedelta(minutes=max(1, ttl)):
                return None
        elif policy == "same_day":
            if created_at.date() != datetime.now().date():
                return None
        else:
            return None
        result = payload.get("result")
        if isinstance(result, dict):
            result["cache_hit"] = True
            result["cache_path"] = str(path)
            return result
        return None

    def save_result(self, result: dict, settings: dict) -> dict:
        storage = settings.get("storage", {})
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        key = self.cache_key(settings)
        cached_at = datetime.now().isoformat(timespec="seconds")
        cache_path = self.cache_dir / f"{key}.json"
        cache_path.write_text(
            json.dumps({"cached_at": cached_at, "settings": settings, "result": result}, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        history_path = ""
        if storage.get("history_enabled", True):
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            history_file = self.history_dir / f"{stamp}_{key[:8]}.json"
            history_file.write_text(
                json.dumps({"created_at": cached_at, "settings": settings, "result": result}, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            history_path = str(history_file)
            self._append_history_index(history_file, result, settings)
            self._trim_history(int(storage.get("history_limit", 120)))
        return {"cache_key": key, "cache_path": str(cache_path), "history_path": history_path}

    def save_history_result(
        self,
        result: dict,
        settings: dict | None = None,
        module: str = "ETF策略工具箱",
        result_type: str = "analysis",
    ) -> dict:
        settings = settings or {}
        self.history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        key = hashlib.sha256(
            json.dumps(
                {
                    "module": module,
                    "result_type": result_type,
                    "created_at": stamp,
                    "config": result.get("config", {}),
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        history_file = self.history_dir / f"{stamp}_{module_slug(module)}_{key[:8]}.json"
        history_file.write_text(
            json.dumps(
                {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "module": module,
                    "result_type": result_type,
                    "settings": settings,
                    "result": result,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        self._append_history_index(history_file, result, settings, module=module, result_type=result_type)
        return {"history_path": str(history_file)}

    def list_history(self, limit: int = 20) -> list[dict]:
        try:
            rows = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows = []
        return rows[:limit]

    def load_history_result(self, path: str | Path) -> dict | None:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        result = payload.get("result")
        return result if isinstance(result, dict) else None

    def cache_key(self, settings: dict) -> str:
        analysis = settings.get("analysis", {})
        key_payload = {
            "analysis": analysis,
            "version": "etf_toolkit_v2",
        }
        raw = json.dumps(key_payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _append_history_index(
        self,
        history_file: Path,
        result: dict,
        settings: dict,
        module: str = "ETF策略工具箱",
        result_type: str = "analysis",
    ) -> None:
        rows = self.list_history(limit=10000)
        rows.insert(0, {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "module": module,
            "result_type": result_type,
            "path": str(history_file),
            "market_snapshot_count": result.get("market_snapshot_count", 0),
            "analyzed_count": result.get("analyzed_count", 0),
            "candidate_count": len(result.get("candidates", [])),
            "alert_count": len(result.get("alerts", [])),
            "error_count": result.get("error_count", 0),
            "success": bool(result.get("success")),
            "max_history": settings.get("analysis", {}).get("max_history"),
            "min_turnover_wan": settings.get("analysis", {}).get("min_turnover_wan"),
            "cache_hit": bool(result.get("cache_hit")),
        })
        self.index_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def _trim_history(self, limit: int) -> None:
        rows = self.list_history(limit=10000)
        keep = rows[:max(1, limit)]
        remove = rows[max(1, limit):]
        for item in remove:
            try:
                Path(str(item.get("path", ""))).unlink(missing_ok=True)
            except OSError:
                pass
        self.index_path.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def module_slug(value: str) -> str:
    mapping = {
        "ETF策略工具箱": "toolkit",
        "指数基金研究": "index_fund",
        "大盘ETF指数分析": "major_market",
        "单只ETF分析": "single_etf",
    }
    return mapping.get(value, "etf")
