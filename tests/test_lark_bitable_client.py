from pathlib import Path

from src.lark_bitable_client import LarkBitableClient


def client() -> LarkBitableClient:
    instance = object.__new__(LarkBitableClient)
    instance.cli = "lark-cli"
    instance.config_path = Path("unused")
    instance.config = {"base_token": "base", "table_id": "table"}
    return instance


def test_find_record_parses_tabular_cli_response(monkeypatch):
    instance = client()
    captured = []

    def fake_run(args):
        captured.extend(args)
        return {
            "data": {
                "fields": ["执行日期", "股票代码", "股票名称"],
                "data": [["2026-06-12", "601083", "锦江航运"]],
                "record_id_list": ["rec_existing"],
            }
        }

    monkeypatch.setattr(
        instance,
        "_run",
        fake_run,
    )
    assert instance.find_record("2026-06-12", "601083") == "rec_existing"
    assert captured.count("--field-id") == 2
    assert "股票代码" in captured


def test_upsert_rechecks_business_key_when_cli_omits_record_id(monkeypatch):
    instance = client()
    calls = iter([
        {
            "data": {
                "fields": ["执行日期", "股票代码"],
                "data": [],
                "record_id_list": [],
            }
        },
        {"data": {}},
        {
            "data": {
                "fields": ["执行日期", "股票代码"],
                "data": [["2026-06-12", "601083"]],
                "record_id_list": ["rec_created"],
            }
        },
    ])
    monkeypatch.setattr(instance, "_run", lambda args: next(calls))
    action, record_id = instance.upsert_daily_stock(
        "2026-06-12",
        "601083",
        {"执行日期": "2026-06-12", "股票代码": "601083"},
    )
    assert action == "新增"
    assert record_id == "rec_created"
