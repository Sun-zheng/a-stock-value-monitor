# Windows 定时任务与 Codex Automation

## Windows 任务：14:10 基础流水线

任务名称：`A股主板低估股票每日分析自动化`

```text
C:\Users\sum\AppData\Local\Programs\Python\Python312\python.exe E:\a_stock_value_monitor\main.py --run-pipeline --no-delivery
```

职责：

- 判断 A 股交易日。
- 获取最新可用数据并执行全市场分层扫描。
- 生成 `reports/YYYY-MM-DD_result.json`。
- 生成 `reports/YYYY-MM-DD_scan_summary.json`。
- 生成 `reports/YYYY-MM-DD_report_base.md`。
- 写入 `data/runtime_state.sqlite3`。
- 不写飞书，不发送最终邮件。

进程使用 `data/pipeline.lock` 防止重入。每次运行具有唯一 `run_id`，状态包括
`started`、`data_fetch`、`light_scan`、`scoring`、`completed` 或 `failed`。

## Codex Automation：14:20 AI 二次分析与最终交付

名称：`A股主板低估股票每日AI分析自动化`

职责：

- 执行 `python main.py --run-status`，确认当天基础流水线成功。
- 只读取当天已有的 `result.json`、`scan_summary.json` 和 `report_base.md`。
- 不再运行全市场扫描。
- 基于结构化结果生成或完善 `report.md`。
- 最后只执行一次 `python main.py --deliver-final-report`。

最终交付使用 SQLite 键 `日期:渠道:final` 保证飞书与邮件幂等。重复执行不会
重复发送已经成功的邮件，也不会重复新增同日飞书记录。

## Windows 任务：14:40 交付兜底

若 14:20 Codex Automation 未启动或未完成交付，本机任务会执行：

```text
python main.py --deliver-final-report
```

若邮件和飞书已经成功，幂等状态会直接跳过，不会重复发送或新增记录。若当天
基础流水线未生成报告，则明确失败并且不会拿旧报告冒充当天结果。

## 运维命令

```powershell
python main.py --data-freshness-check
python main.py --compare-previous-day
python main.py --strategy-health-check
python main.py --run-status
python main.py --validate-delivery
python main.py --server-readiness-check
python main.py --run-pipeline --no-delivery
python main.py --deliver-final-report
```

## 查看任务

```powershell
Get-ScheduledTask -TaskName "A股主板低估股票每日分析自动化"
Get-ScheduledTaskInfo -TaskName "A股主板低估股票每日分析自动化"
Get-Content .\logs\$(Get-Date -Format yyyy-MM-dd).log -Tail 100
```

本系统不调用 OpenAI API，不需要 `OPENAI_API_KEY`。所有结论仅作为投资研究
参考，不构成投资建议。
