# Scheduled Task Operations

## Goal

The scheduler should support adding new recurring jobs without duplicating systemd unit-writing logic. Existing jobs remain:

- Streamlit console service
- Daily Buffett-Munger value pipeline
- Low-price bull daily selector
- Final delivery fallback

## Design

Linux user-level scheduling is generated from `src.scheduler.scheduled_commands()`.

To add a future scheduled job:

1. Add a CLI flag and implementation in `main.py`.
2. Add a `ScheduledCommand` entry in `src/scheduler.py`.
3. Add or update tests in `tests/test_scheduler.py`.
4. Run `python main.py --apply-schedule`.
5. Verify with `python main.py --schedule-status`.

Example:

```python
ScheduledCommand(
    name="new-job",
    description="New scheduled job",
    service_name="stock-new-job.service",
    timer_name="stock-new-job.timer",
    command="--run-new-job",
    calendar="Mon..Fri 15:00:00",
    order=50,
)
```

## Reliability Controls

- Timers use `Persistent=true`, so missed jobs run after the user systemd session resumes.
- The main pipeline uses `RuntimeState.single_instance()` to prevent overlapping runs.
- Stale `pipeline.lock` files are recovered after `PIPELINE_LOCK_STALE_MINUTES` minutes, default `240`.
- Delivery uses content hashes and reservation records to prevent duplicate sends.
- Scheduled jobs use the private local AI env file for analysis switches and model pools: `~/.config/a-stock-value-monitor/aiagents.env`.

## AI Cost Controls

Default scheduled behavior:

- `VALUE_ANALYSIS_ALLOW_DEEPSEEK=0`: blocks the official DeepSeek provider models `deepseek-chat` and `deepseek-reasoner`.
- ModelScope model ids such as `deepseek-ai/DeepSeek-V4-Pro` are allowed because they use `MODELSCOPE_API_KEY`, not the DeepSeek official key.
- Scheduled email detail defaults to `VALUE_ANALYSIS_EMAIL_DETAIL=summary`, so mails include readable analyst summaries instead of full verbose transcripts.
- Recommended scheduled model pool after validation on this machine: `stepfun-ai/Step-3.7-Flash`, `moonshotai/Kimi-K2.7-Code:Moonshot`.
- `MiniMax/MiniMax-M3` and `deepseek-ai/DeepSeek-V4-Pro` are routed through ModelScope, but this account currently returned balance/quota errors during validation, so they are not in the default timer pool.
- Runtime limits on this machine: `LOW_PRICE_BULL_TOP_N=5`, `LOW_PRICE_BULL_ANALYSIS_LIMIT=1`, `VALUE_ANALYSIS_MAX_STOCKS=3`.

To test the full agent chain with ModelScope models only:

```bash
VALUE_ANALYSIS_ENABLED=1 \
VALUE_ANALYSIS_MODELS="stepfun-ai/Step-3.7-Flash,moonshotai/Kimi-K2.7-Code:Moonshot" \
python main.py --deliver-final-report

LOW_PRICE_BULL_AI_ANALYSIS=1 \
LOW_PRICE_BULL_TOP_N=1 \
VALUE_ANALYSIS_MODELS="stepfun-ai/Step-3.7-Flash" \
python main.py --run-low-price-bull
```

Only enable DeepSeek manually for an intentional paid run:

```bash
VALUE_ANALYSIS_ALLOW_DEEPSEEK=1 VALUE_ANALYSIS_MODELS="deepseek-chat" python main.py --deliver-final-report
```

## Deployment

```bash
python main.py --apply-schedule
python main.py --schedule-status
python main.py --server-readiness-check
```

For Linux user services:

```bash
systemctl --user list-timers 'stock-*'
systemctl --user status stock-site.service
journalctl --user -u stock-daily-analysis.service -n 100 --no-pager
```

## Test Plan

Before deployment:

```bash
pytest -q
python main.py --data-freshness-check
python main.py --strategy-validation
python main.py --server-readiness-check
```

After deployment:

```bash
python main.py --schedule-status
python main.py --run-status
python main.py --validate-delivery
```

## Operations Checklist

- Confirm `.env` and AI provider env file exist only locally.
- Confirm `data/`, `reports/`, and `logs/` are writable by the scheduler user.
- Confirm external providers are reachable.
- Confirm SMTP and Lark/Feishu credentials are valid.
- Confirm `stock-site.service` binds to `127.0.0.1` unless an authenticated reverse proxy is configured.
