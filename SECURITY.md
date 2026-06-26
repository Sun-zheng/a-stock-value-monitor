# Security Policy

## Supported Use

This project is intended for local research automation and private deployments. Do not expose the Streamlit application or configuration server directly to the public internet without adding authentication, network controls, rate limits, and secret-management hardening.

## Secrets and Private Data

Never commit:

- `.env`, `.env.*` except `.env.example`
- `secrets/`
- API keys, SMTP passwords, Lark/Feishu credentials, Tushare tokens, AI provider keys
- `data/`, `reports/`, `logs/`
- SQLite databases and generated market data files
- Personal account, portfolio, notification, or trading configuration

The repository `.gitignore` excludes these paths by default. Before publishing, run:

```bash
git status --short
git check-ignore -v .env secrets/aiagents.env data/runtime_state.sqlite3 reports/2026-06-26_email.md
rg -n "sk-|API_KEY=|PASSWORD=|TOKEN=|SECRET=" -g '!**/.venv/**' -g '!data/**' -g '!reports/**' -g '!logs/**' -g '!secrets/**'
```

## Reporting Security Issues

Open a private security advisory or contact the maintainer privately. Do not include live tokens, raw personal data, portfolio screenshots, or full generated reports in public issues.

## Security Defaults

- AI provider and SMTP credentials are loaded from environment variables.
- The AI sub-application test master password is disabled by default.
- Runtime state and delivery locks are stored locally and should not be shared.
- The project does not require OpenAI API keys unless you explicitly configure an OpenAI-compatible provider.

## Deployment Notes

For shared or server deployments:

- Put Streamlit and any config endpoint behind authentication.
- Restrict inbound network access to trusted IP ranges or VPN.
- Use a secrets manager instead of `.env` files.
- Rotate AI provider, SMTP, Lark/Feishu, and market data tokens regularly.
- Run the pipeline with a least-privileged OS user.
- Keep generated reports and local databases outside the Git repository.
