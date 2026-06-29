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
- Scheduled jobs do not run large-model stock analysis by default. This avoids paid API usage and long-running delivery failures.

## AI Cost Controls

Default scheduled behavior:

- `VALUE_ANALYSIS_ENABLED=0`: final delivery does not call stock-analysis agents unless explicitly enabled.
- `LOW_PRICE_BULL_AI_ANALYSIS=0`: low-price bull delivery only screens and emails results unless explicitly enabled.
- `VALUE_ANALYSIS_ALLOW_DEEPSEEK=0`: any model name containing `deepseek` is filtered out of scheduled model validation.
- Default validation models are ModelScope-compatible free/test models: `stepfun-ai/Step-3.5-Flash`, `Qwen/Qwen3-Next-80B-A3B-Instruct`, `moonshotai/Kimi-K2.5`.

To test the full agent chain with free/test models only:

```bash
VALUE_ANALYSIS_ENABLED=1 \
VALUE_ANALYSIS_MODELS="stepfun-ai/Step-3.5-Flash,Qwen/Qwen3-Next-80B-A3B-Instruct" \
python main.py --deliver-final-report

LOW_PRICE_BULL_AI_ANALYSIS=1 \
LOW_PRICE_BULL_TOP_N=1 \
VALUE_ANALYSIS_MODELS="stepfun-ai/Step-3.5-Flash" \
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
