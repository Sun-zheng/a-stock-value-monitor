# GitHub Publishing Guide

This workspace has been prepared for open source publishing, but one structural decision remains.

## Current State

- Root Git repository has been initialized on branch `main`.
- Sensitive runtime paths are ignored by `.gitignore`.
- `aiagents-stock-main/` has been merged into the root working tree as normal source files. Its former `.git` directory was moved outside the project as a backup.
- `gh` is not installed in this environment, so automated push/PR creation through the normal GitHub CLI flow is unavailable.

## Decide Repository Layout

### Single Public Repository

The workspace is now prepared for one GitHub repository containing both the root value-monitor pipeline and the Streamlit AI app.

```bash
git add .
git status --short
git commit -m "Prepare open source stock value monitor"
git remote add origin git@github.com:OWNER/REPO.git
git push -u origin main
```

## Pre-Push Checks

Run these from the root:

```bash
git status --short
git check-ignore -v .env secrets/aiagents.env data/runtime_state.sqlite3 reports/2026-06-26_email.md
rg -n "sk-|API_KEY=|PASSWORD=|TOKEN=|SECRET=" -g '!**/.venv/**' -g '!data/**' -g '!reports/**' -g '!logs/**' -g '!secrets/**'
.venv/bin/python -m pytest tests/test_ai_value_analysis.py tests/test_strategy_config.py tests/test_runtime_state.py -q
cd aiagents-stock-main && .venv/bin/python -m pytest tests/test_generate_value_stock_analysis.py tests/test_provider_config.py -q
```

## Notes

- Do not put tokens in remote URLs.
- Prefer SSH remotes or an authenticated GitHub CLI session.
- If using the GitHub connector, provide the target `owner/repo`; the current connector can write to an existing repository but cannot create a new repository in this environment.
