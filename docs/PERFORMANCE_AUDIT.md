# Performance and Optimization Audit

Date: 2026-06-26

## Executive Summary

The main optimization opportunities are in external API usage, repeated full-candidate financial enrichment, AI model calls, and storage/report generation. The project already has useful caches and tests, but it would benefit from clearer cache invalidation, bounded concurrency, structured profiling, and a shared analysis service contract between the root pipeline and the Streamlit app.

## Current Flow

1. `main.py` orchestrates CLI tasks.
2. `src/data_source_manager.py`, `src/tushare_client.py`, and related modules fetch and cache market/financial data.
3. `src/universe_scanner.py` builds candidates, scores them, and writes scan summaries.
4. `src/ai_value_analysis.py` validates AI providers and calls `aiagents-stock-main/tools/generate_value_stock_analysis.py`.
5. `aiagents-stock-main/tools/generate_value_stock_analysis.py` calls the Streamlit app's unified `analyze_single_stock_for_batch()` function.
6. `main.py` writes reports, Feishu/Lark records, and email output.

## Primary Bottlenecks

| Area | Bottleneck | Impact | Suggested Fix |
| --- | --- | --- | --- |
| Market data | Full scans and external API calls can dominate runtime | Slow daily pipeline and flaky runs when providers throttle | Persist provider response metadata, add TTL-based cache validation, and add retry/backoff metrics |
| Financial enrichment | Up to hundreds of candidates may require expensive financial calls | Long pipeline duration | Batch provider calls where supported and cache per stock/report period |
| AI analysis | Six analysts plus team discussion/final decision per delivered stock | High latency and provider cost | Limit AI analysis to delivered stocks, add per-agent timeout controls, and persist successful per-stock AI results by date/model |
| Streamlit import | CLI tool imports `frontend.app`, which initializes Streamlit module state | Warning noise and import overhead | Move `analyze_single_stock_for_batch` into a pure backend service module and let Streamlit import that |
| Reports | Large Markdown/JSON outputs are repeatedly hashed and rewritten | Moderate I/O overhead | Avoid rewriting unchanged reports and store normalized report metadata |
| SQLite/runtime state | Local SQLite is fine for single-host use | Contention if multiple schedulers run | Keep idempotent locks, add stale-lock cleanup telemetry |

## Recommended Engineering Changes

### 1. Extract a Pure Analysis Service

Move the implementation behind `frontend/app.py::analyze_single_stock_for_batch()` into a backend module such as:

```text
aiagents-stock-main/backend/services/stock_analysis_service.py
```

Then both Streamlit and the root delivery tool can import the service without Streamlit side effects. This will reduce CLI startup overhead and make tests more direct.

### 2. Add Profiling Hooks

Add structured timing around:

- valuation build
- financial build
- candidate scoring
- AI validation
- per-stock AI analysis
- Feishu upsert
- SMTP send

Write these timings to `reports/YYYY-MM-DD_perf.json` locally. Keep the file ignored by Git.

### 3. Cache AI Results by Content Hash

Use a cache key like:

```text
{date}:{stock_code}:{model}:{enabled_analysts_hash}:{value_context_hash}
```

If the same stock context and model were already analyzed successfully, reuse the result instead of calling every analyst again.

### 4. Bound Concurrency Explicitly

The AI analyst flow already uses thread pools internally. Add environment-configured concurrency limits:

```text
AI_ANALYSIS_MAX_WORKERS=2
DATA_FETCH_MAX_WORKERS=5
```

This avoids provider throttling and makes daily runtime more predictable.

### 5. Improve Dependency Hygiene

Split requirements by use case:

```text
requirements.txt
requirements-dev.txt
aiagents-stock-main/requirements.txt
```

Pin high-risk runtime libraries to compatible ranges after a working lock is produced.

## Quick Wins

- Keep AI analysis limited to formal recommendation and observation stocks only.
- Do not run `--deliver-final-report` if no current-day scan exists.
- Avoid committing generated report/history files.
- Move Streamlit-independent analysis code out of `frontend/app.py`.
- Add a `--profile` flag to `main.py`.

## Validation

Current targeted checks used during this audit:

```bash
.venv/bin/python -m pytest tests/test_ai_value_analysis.py -q
aiagents-stock-main/.venv/bin/python -m pytest tests/test_generate_value_stock_analysis.py -q
.venv/bin/python -m py_compile src/ai_value_analysis.py aiagents-stock-main/tools/generate_value_stock_analysis.py
```
