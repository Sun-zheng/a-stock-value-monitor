import json

import pytest

from src.strategy_config import DEFAULT_STRATEGY, load_strategy, save_strategy


def test_strategy_weights_must_total_100(tmp_path):
    config = json.loads(json.dumps(DEFAULT_STRATEGY, ensure_ascii=False))
    config["weights"]["股东回报"] = 6
    with pytest.raises(ValueError, match="合计必须为100"):
        save_strategy(tmp_path, config)


def test_strategy_round_trip(tmp_path):
    config = json.loads(json.dumps(DEFAULT_STRATEGY, ensure_ascii=False))
    saved = save_strategy(tmp_path, config)
    assert saved == load_strategy(tmp_path)
    assert saved["run_time"] == "14:10"
    assert saved["formal_score"] == 80
    assert saved["candidate_limit"] == 500
