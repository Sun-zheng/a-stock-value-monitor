from __future__ import annotations

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from src.runtime_state import RuntimeState
from src.scheduler import configure_native_schedule, native_schedule_status
from src.strategy_config import load_strategy, save_strategy


def latest_scan(reports_dir: Path) -> dict:
    paths = sorted(reports_dir.glob("*_scan_summary.json"), reverse=True)
    if not paths:
        return {}
    try:
        return json.loads(paths[0].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def task_status() -> dict:
    script = (
        "$t=Get-ScheduledTask -TaskName 'A股主板低估股票每日分析自动化' "
        "-ErrorAction SilentlyContinue;"
        "if(-not $t){'{}';exit};"
        "$i=Get-ScheduledTaskInfo -TaskName $t.TaskName;"
        "[pscustomobject]@{state=$t.State;next_run=$i.NextRunTime;"
        "last_run=$i.LastRunTime;last_result=$i.LastTaskResult;"
        "start_when_available=$t.Settings.StartWhenAvailable;"
        "wake_to_run=$t.Settings.WakeToRun;arguments=$t.Actions.Arguments}"
        "|ForEach-Object {$_.next_run=$_.next_run.ToString('yyyy-MM-dd HH:mm:ss');"
        "$_.last_run=$_.last_run.ToString('yyyy-MM-dd HH:mm:ss');$_}"
        "|ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    try:
        return json.loads(result.stdout.strip() or "{}")
    except ValueError:
        return {"error": (result.stderr or result.stdout).strip()}


class ConfigHandler(BaseHTTPRequestHandler):
    project_root: Path

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = (self.project_root / "web" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/state":
            runtime = RuntimeState(self.project_root / "data", "Asia/Shanghai")
            self._json({
                "strategy": load_strategy(self.project_root),
                "scan": latest_scan(self.project_root / "reports"),
                "runtime": {
                    "latest": runtime.latest_run(),
                    "latest_success": runtime.latest_success(),
                },
                "schedule": native_schedule_status(),
            })
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/config":
                config = save_strategy(self.project_root, self._body())
                self._json({"ok": True, "strategy": config})
                return
            if path == "/api/apply-schedule":
                strategy = load_strategy(self.project_root)
                status = configure_native_schedule(
                    self.project_root, strategy["run_time"]
                )
                self._json({"ok": True, "schedule": status})
                return
            if path == "/api/validate":
                result = subprocess.run(
                    [sys.executable, "main.py", "--strategy-validation"],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=900,
                    check=False,
                )
                self._json({
                    "ok": result.returncode == 0,
                    "returncode": result.returncode,
                    "output": (result.stdout or result.stderr)[-4000:],
                })
                return
            self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 400)

    def log_message(self, format: str, *args) -> None:
        return


def serve_config(project_root: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    handler = type(
        "ProjectConfigHandler",
        (ConfigHandler,),
        {"project_root": project_root},
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"策略配置页: http://{host}:{port}")
    server.serve_forever()
