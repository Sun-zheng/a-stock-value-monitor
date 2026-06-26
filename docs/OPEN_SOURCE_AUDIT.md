# Open Source Readiness Audit

Date: 2026-06-26

## Executive Summary

The project can be prepared for open source publication after enforcing a strict boundary between source code and local runtime data. The highest-risk items are local secrets, generated reports, SQLite databases, personal email defaults, and the nested `aiagents-stock-main` Git repository. The source tree now includes stronger ignore rules, safer defaults, and GitHub-facing documentation.

## What Was Changed

- Expanded `.gitignore` to exclude secrets, environment files, runtime data, reports, logs, databases, caches, and nested app artifacts.
- Removed the personal default `EMAIL_TO` value from `.env.example` and `config/settings.py`.
- Replaced the hard-coded local `A_STOCK_VALUE_MONITOR_ROOT` fallback with a path derived from the source file.
- Disabled the AI app test master password by default.
- Rewrote `README.md` for GitHub readers.
- Added `SECURITY.md`, this audit, a performance audit, and a threat model.

## Publishable by Default

These categories are appropriate for Git:

- Source code under `src/`, `config/`, `tools/`, `tests/`, `web/`
- `aiagents-stock-main` source, tests, docs, and configuration code
- Documentation under `docs/`
- `.env.example`, `requirements.txt`, `pytest.ini`, `README.md`, `SECURITY.md`

## Must Not Be Published

These categories must stay local:

- `.env`, `aiagents-stock-main/.env`, and any other real env file
- `secrets/`
- `data/`, including `runtime_state.sqlite3`, caches, market snapshots, Feishu table config, and analysis history
- `reports/`, including generated emails and AI analysis reports
- `logs/`
- `*.db`, `*.sqlite3`, `*.parquet`, generated `*.csv`
- `aiagents-stock-main/database/files/`
- `aiagents-stock-main/归档/`

## Git Blockers

The workspace root is not currently a Git repository, while `aiagents-stock-main/` already contains its own `.git` directory. If a root repository is initialized and `aiagents-stock-main/` is added as-is, Git will treat it as an embedded repository/submodule-style entry rather than normal files.

Recommended options:

1. Keep two repositories: one for the root value-monitor pipeline and one for `aiagents-stock-main`.
2. Convert to a single repository by moving `aiagents-stock-main/.git` out of the tree after backing it up, then add the directory as normal source files.
3. Publish `aiagents-stock-main` as a real submodule only if it already has a clean public remote.

Do not delete or move the nested `.git` directory without an explicit decision, because it may contain local history.

## GitHub Upload Status

Automated upload is blocked in this environment because:

- `gh` is not installed.
- No target `owner/repo` was provided.
- The available GitHub connector can write files to an existing repository, but it cannot create a new repository from this tool set.

Once a GitHub repository exists, provide `owner/repo` and the desired branch. The sanitized file set can then be committed and pushed.

## Pre-Publish Checklist

```bash
git init
git status --short
git check-ignore -v .env secrets/aiagents.env data/runtime_state.sqlite3 reports/2026-06-26_email.md
rg -n "sk-|API_KEY=|PASSWORD=|TOKEN=|SECRET=" -g '!**/.venv/**' -g '!data/**' -g '!reports/**' -g '!logs/**' -g '!secrets/**'
pytest -q
```

Before running `git add`, decide how to handle `aiagents-stock-main/.git`.
