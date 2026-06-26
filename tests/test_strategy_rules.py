import pandas as pd

from src.universe_scanner import add_decision_fields, select_outputs


def candidate(score: float, margin: float | None) -> dict:
    return {
        "综合评分": score,
        "安全边际": margin,
        "可靠估值覆盖率": 100,
        "财报覆盖率": 100,
        "现金流完整": True,
        "一票否决原因": "",
        "估值模型可用于正式推荐": True,
        "估值方法有效数": 3,
        "市场错配判断": "优质成长被低估",
        "十年持有质量门槛": True,
        "生意质量与护城河评分": 10,
        "管理层与资本配置评分": 6,
        "盈利能力与韧性评分": 10,
        "财务安全评分": 7,
        "现金流质量评分": 10,
        "十年成长跑道评分": 6,
        "芒格反向清单评分": 4,
        "行业估值样本充足": True,
        "特殊行业": False,
        "质量因子": 25,
        "估值因子": 25,
        "成长因子": 15,
        "股东回报因子": 10,
        "风险扣分": 0,
    }


def test_formal_recommendation_requires_all_thresholds():
    rows = [
        candidate(80, 25),
        candidate(79.99, 25),
        candidate(80, 24.99),
        {**candidate(80, 25), "可靠估值覆盖率": 50},
        {**candidate(80, 25), "财报覆盖率": 60},
        {**candidate(80, 25), "现金流完整": False},
        {**candidate(80, 25), "一票否决原因": "错配"},
    ]
    result = add_decision_fields(pd.DataFrame(rows))
    assert result["是否正式推荐"].tolist() == [True, False, False, False, False, False, False]


def test_eleventh_candidate_is_still_checked_for_formal_recommendation():
    rows = [candidate(79, 30) for _ in range(10)] + [candidate(90, 30)]
    scored = add_decision_fields(pd.DataFrame(rows))
    formal, observations = select_outputs(scored, recommendation_ready=True)
    assert formal.index.tolist() == [10]
    assert len(formal) == 1
    assert len(observations) <= 5


def test_output_limits_and_watch_floor():
    rows = [candidate(90, 30), candidate(89, 30)]
    rows += [{**candidate(73 - i, None), "估值模型可用于正式推荐": False} for i in range(8)]
    scored = add_decision_fields(pd.DataFrame(rows))
    formal, observations = select_outputs(scored, recommendation_ready=True)
    assert len(formal) == 1
    assert len(observations) == 5
    assert observations["综合评分"].min() >= 68
    assert (observations["操作建议"] == "继续观察，不构成推荐").all()
