import json
from datetime import datetime, timedelta, timezone

import pytest

from src.runtime_state import PipelineAlreadyRunning, RuntimeState


def test_delivery_is_idempotent(tmp_path):
    state = RuntimeState(tmp_path, "UTC")
    key = "2026-06-11:email:final"
    assert state.delivery_completed(key) is False
    state.mark_delivery(
        key, "2026-06-11", "email", "abc", "completed", "sent"
    )
    assert state.delivery_completed(key) is True
    assert state.delivery_completed(key, "abc") is True
    assert state.delivery_completed(key, "def") is False
    state.mark_delivery(
        key, "2026-06-11", "email", "abc", "completed", "sent"
    )
    rows = state.delivery_status("2026-06-11")
    assert len(rows) == 1


def test_delivery_reservation_allows_only_one_sender(tmp_path):
    state = RuntimeState(tmp_path, "UTC")
    key = "2026-06-11:lark:final"
    assert state.reserve_delivery(key, "2026-06-11", "lark", "abc") is True
    assert state.reserve_delivery(key, "2026-06-11", "lark", "abc") is False


def test_delivery_reservation_reopens_completed_delivery_when_hash_changes(tmp_path):
    state = RuntimeState(tmp_path, "UTC")
    key = "2026-06-11:lark:final"
    state.mark_delivery(key, "2026-06-11", "lark", "abc", "completed", "sent")

    assert state.reserve_delivery(key, "2026-06-11", "lark", "def") is True
    assert state.delivery_completed(key, "def") is False
    assert state.delivery_record(key)["status"] == "sending"


def test_run_status_is_persisted(tmp_path):
    state = RuntimeState(tmp_path, "UTC")
    run_id = state.start_run()
    state.update_run(run_id, "completed", "completed")
    assert state.latest_success()["run_id"] == run_id


def test_single_instance_blocks_active_lock(tmp_path):
    state = RuntimeState(tmp_path, "UTC")
    with state.single_instance():
        with pytest.raises(PipelineAlreadyRunning):
            with state.single_instance():
                pass


def test_single_instance_recovers_stale_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_LOCK_STALE_MINUTES", "30")
    state = RuntimeState(tmp_path, "UTC")
    stale_time = datetime.now(timezone.utc) - timedelta(hours=2)
    state.lock_path.write_text(
        json.dumps({"pid": 999999, "created_at": stale_time.isoformat()}),
        encoding="utf-8",
    )

    with state.single_instance():
        payload = json.loads(state.lock_path.read_text(encoding="utf-8"))
        assert payload["recovered_stale_lock"] is True

    assert not state.lock_path.exists()
