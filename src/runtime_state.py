from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


class PipelineAlreadyRunning(RuntimeError):
    pass


class RuntimeState:
    def __init__(self, data_dir: Path, timezone: str):
        self.data_dir = data_dir
        self.timezone = timezone
        self.db_path = data_dir / "runtime_state.sqlite3"
        self.lock_path = data_dir / "pipeline.lock"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def now(self) -> datetime:
        return datetime.now(ZoneInfo(self.timezone))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    run_date TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS deliveries (
                    delivery_key TEXT PRIMARY KEY,
                    run_date TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    completed_at TEXT,
                    detail TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(run_date);
                """
            )

    def _stale_lock_after(self) -> timedelta:
        minutes = int(os.getenv("PIPELINE_LOCK_STALE_MINUTES", "240") or "240")
        return timedelta(minutes=max(minutes, 1))

    def _lock_is_stale(self) -> bool:
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
            created_at = datetime.fromisoformat(payload.get("created_at", ""))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return True
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=ZoneInfo(self.timezone))
        return self.now() - created_at > self._stale_lock_after()

    def _open_lock(self) -> int:
        return os.open(
            self.lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )

    @contextmanager
    def single_instance(self):
        handle = None
        try:
            handle = self._open_lock()
            os.write(
                handle,
                json.dumps(
                    {"pid": os.getpid(), "created_at": self.now().isoformat()}
                ).encode("utf-8"),
            )
        except FileExistsError as exc:
            if self._lock_is_stale():
                self.lock_path.unlink(missing_ok=True)
                handle = self._open_lock()
                os.write(
                    handle,
                    json.dumps(
                        {
                            "pid": os.getpid(),
                            "created_at": self.now().isoformat(),
                            "recovered_stale_lock": True,
                        }
                    ).encode("utf-8"),
                )
            else:
                raise PipelineAlreadyRunning(
                    f"pipeline lock exists: {self.lock_path}"
                ) from exc
        except OSError as exc:
            raise PipelineAlreadyRunning(
                f"cannot create pipeline lock: {self.lock_path}: {exc}"
            ) from exc
        try:
            yield
        finally:
            if handle is not None:
                os.close(handle)
            self.lock_path.unlink(missing_ok=True)

    def start_run(self, metadata: dict | None = None) -> str:
        now = self.now()
        run_id = f"{now:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs
                (run_id, run_date, started_at, updated_at, stage, status, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    now.date().isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                    "started",
                    "running",
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
        return run_id

    def update_run(
        self,
        run_id: str,
        stage: str,
        status: str = "running",
        error: str = "",
        metadata: dict | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET updated_at = ?, stage = ?, status = ?, error = ?,
                    metadata_json = CASE WHEN ? = '{}' THEN metadata_json ELSE ? END
                WHERE run_id = ?
                """,
                (
                    self.now().isoformat(),
                    stage,
                    status,
                    error[:4000],
                    json.dumps(metadata or {}, ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    run_id,
                ),
            )

    def latest_run(self) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else {}

    def latest_success(self) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM runs
                WHERE status = 'completed'
                ORDER BY started_at DESC LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else {}

    def delivery_record(self, delivery_key: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM deliveries WHERE delivery_key = ?",
                (delivery_key,),
            ).fetchone()
        return dict(row) if row else {}

    def delivery_completed(
        self, delivery_key: str, content_hash: str | None = None
    ) -> bool:
        row = self.delivery_record(delivery_key)
        if not row or row["status"] != "completed":
            return False
        if content_hash is None:
            return True
        return row.get("content_hash") == content_hash

    def mark_delivery(
        self,
        delivery_key: str,
        run_date: str,
        channel: str,
        content_hash: str,
        status: str,
        detail: str = "",
    ) -> None:
        now = self.now().isoformat()
        completed_at = now if status == "completed" else None
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO deliveries
                (delivery_key, run_date, channel, content_hash, status,
                 attempted_at, completed_at, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(delivery_key) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    status = excluded.status,
                    attempted_at = excluded.attempted_at,
                    completed_at = excluded.completed_at,
                    detail = excluded.detail
                """,
                (
                    delivery_key,
                    run_date,
                    channel,
                    content_hash,
                    status,
                    now,
                    completed_at,
                    detail[:4000],
                ),
            )

    def reserve_delivery(
        self,
        delivery_key: str,
        run_date: str,
        channel: str,
        content_hash: str,
    ) -> bool:
        now = self.now().isoformat()
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO deliveries
                    (delivery_key, run_date, channel, content_hash, status,
                     attempted_at, completed_at, detail)
                    VALUES (?, ?, ?, ?, 'sending', ?, NULL, 'reserved')
                    """,
                    (
                        delivery_key,
                        run_date,
                        channel,
                        content_hash,
                        now,
                    ),
                )
                return True
            except sqlite3.IntegrityError:
                row = connection.execute(
                    "SELECT status, content_hash FROM deliveries WHERE delivery_key = ?",
                    (delivery_key,),
                ).fetchone()
                if not row:
                    return False
                if row["status"] == "failed" or (
                    row["status"] == "completed"
                    and row["content_hash"] != content_hash
                ):
                    connection.execute(
                        """
                        UPDATE deliveries
                        SET content_hash = ?, status = 'sending',
                            attempted_at = ?, completed_at = NULL, detail = 'reserved'
                        WHERE delivery_key = ?
                        """,
                        (content_hash, now, delivery_key),
                    )
                    return True
                return False

    def delivery_status(self, run_date: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM deliveries
                WHERE run_date = ?
                ORDER BY attempted_at
                """,
                (run_date,),
            ).fetchall()
        return [dict(row) for row in rows]
