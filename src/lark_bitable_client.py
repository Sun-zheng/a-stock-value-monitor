from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path


LARK_FIELDS = [
    "执行日期", "是否交易日", "执行时间", "最终结论", "股票代码", "股票名称",
    "所属交易所", "上市板块", "所属行业", "当前价格", "涨跌幅", "当前市值",
    "流通市值", "PE TTM", "PB", "PS", "股息率", "ROE", "扣非ROE", "ROIC",
    "毛利率", "净利率", "经营现金流净额", "自由现金流", "资产负债率",
    "综合评分", "安全边际", "操作建议", "核心逻辑", "主要风险", "完整分析报告",
    "数据来源", "数据时间", "飞书表格链接", "邮件发送状态", "飞书写入状态",
    "运行日志", "原始股票数量", "主板股票数量", "行情覆盖率", "估值覆盖率",
    "财报覆盖率", "通过估值初筛数量", "通过一票否决数量", "深度分析数量",
    "最终推荐数量", "扫描耗时", "数据缺失说明", "无推荐原因", "观察方向",
    "扫描摘要",
    "Tushare是否可用", "Tushare覆盖数量", "现金流覆盖率", "缓存命中率",
    "数据源失败原因", "是否满足正式推荐条件", "估值数据交易日",
    "财报数据报告期", "数据覆盖率说明",
    "是否正式推荐", "股票类型", "观察排名", "未达推荐原因",
    "距离推荐标准差距", "下一步观察重点", "是否观察股票", "是否今日休息",
    "上一日排名", "排名变化", "连续观察天数", "首次进入日期", "今日变化摘要",
    "策略名称", "策略版本", "正式推荐分数门槛", "安全边际门槛",
    "生意质量与护城河评分", "管理层与资本配置评分", "盈利能力与韧性评分",
    "财务安全评分", "现金流质量评分", "十年成长跑道评分",
    "估值与安全边际评分", "股东回报评分", "芒格反向清单评分",
    "九维评分明细", "芒格反向失败清单", "市场错配判断",
    "十年持有质量门槛", "十年持有结论", "估值方法有效数",
    "可靠估值覆盖率", "市值口径", "报表期间一致",
    "已计价预期", "长期投资关键证据", "为何现在",
    "国内全市场基准股票数量", "行业基准范围",
]


class LarkError(RuntimeError):
    pass


def _is_rate_limited(message: str) -> bool:
    lowered = message.lower()
    return (
        "800004135" in message
        or "limited" in lowered
        or "rate" in lowered
        or "too many" in lowered
    )


class LarkBitableClient:
    def __init__(self, cli: str, config_path: Path):
        self.cli = cli
        self.config_path = config_path
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise LarkError(f"飞书配置读取失败: {exc}") from exc

    def _run(self, args: list[str], timeout: int = 90) -> dict:
        last_error = ""
        for attempt in range(5):
            result = subprocess.run(
                [self.cli, *args, "--as", "user", "--format", "json"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout, check=False,
            )
            raw = (result.stderr or result.stdout).strip()
            if result.returncode:
                last_error = raw
            else:
                try:
                    payload = json.loads(result.stdout)
                except ValueError as exc:
                    raise LarkError(f"lark-cli 返回非 JSON: {result.stdout[:500]}") from exc
                if payload.get("ok") is not False:
                    return payload
                last_error = json.dumps(payload, ensure_ascii=False)
            if not _is_rate_limited(last_error) or attempt == 4:
                break
            time.sleep(2 ** attempt)
        raise LarkError(last_error)

    def check(self) -> tuple[bool, str]:
        if shutil.which(self.cli) is None:
            return False, f"未找到 {self.cli}"
        try:
            result = subprocess.run(
                [self.cli, "doctor"], capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30, check=False,
            )
            payload = json.loads(result.stdout)
            return bool(payload.get("ok")), "lark-cli 已安装、授权和联网"
        except Exception as exc:
            return False, f"lark-cli 检查失败: {exc}"

    @property
    def url(self) -> str:
        return str(self.config.get("url", ""))

    def ensure_fields(self) -> list[str]:
        payload = self._run([
            "base", "+field-list", "--base-token", self.config["base_token"],
            "--table-id", self.config["table_id"], "--limit", "200",
        ])
        data = payload.get("data", {})
        items = data.get("fields", data.get("items", []))
        existing = {item.get("name") for item in items if isinstance(item, dict)}
        created = []
        for name in LARK_FIELDS:
            if name in existing:
                continue
            self._run([
                "base", "+field-create", "--base-token", self.config["base_token"],
                "--table-id", self.config["table_id"], "--json",
                json.dumps({"type": "text", "name": name}, ensure_ascii=False),
            ])
            created.append(name)
        return created

    def find_record(
        self, execution_date: str, stock_code: str
    ) -> str | None:
        payload = self._run([
            "base", "+record-search", "--base-token", self.config["base_token"],
            "--table-id", self.config["table_id"], "--keyword", execution_date,
            "--search-field", "执行日期",
            "--field-id", "执行日期",
            "--field-id", "股票代码",
            "--limit", "200",
        ])
        data = payload.get("data", {})
        rows = data.get("data", [])
        ids = data.get("record_id_list", [])
        fields = data.get("fields", [])
        date_index = fields.index("执行日期") if "执行日期" in fields else -1
        code_index = fields.index("股票代码") if "股票代码" in fields else -1
        for index, row in enumerate(rows):
            if isinstance(row, list) and date_index >= 0 and code_index >= 0:
                if (
                    str(row[date_index] or "") == execution_date
                    and str(row[code_index] or "") == stock_code
                    and index < len(ids)
                ):
                    return ids[index]
            text = str(row)
            if execution_date in text and stock_code in text and index < len(ids):
                return ids[index]
        for record in data.get("records", data.get("items", [])):
            fields = record.get("fields", {})
            if (
                execution_date in str(fields.get("执行日期"))
                and stock_code in str(fields.get("股票代码"))
            ):
                return record.get("record_id") or record.get("id")
        return None

    def upsert_daily_stock(
        self, execution_date: str, stock_code: str, fields: dict
    ) -> tuple[str, str]:
        record_id = self.find_record(execution_date, stock_code)
        args = [
            "base", "+record-upsert", "--base-token", self.config["base_token"],
            "--table-id", self.config["table_id"], "--json",
            json.dumps(fields, ensure_ascii=False),
        ]
        action = "新增"
        if record_id:
            args.extend(["--record-id", record_id])
            action = "更新"
        payload = self._run(args)
        data = payload.get("data", {})
        record = data.get("record", {})
        returned_id = (
            record.get("record_id") or record.get("id") or data.get("record_id")
            or next(iter(data.get("record_id_list", [])), "")
            or record_id
        )
        if not returned_id:
            returned_id = self.find_record(execution_date, stock_code)
        return action, returned_id or ""
