# Minimal test environment profile

This profile allows running architecture/type/lint checks and most test bootstrap paths
without exposing production credentials.

## 1) Create local test env file

```bash
cp .env.test.example .env.test
```

## 2) Ensure required variables are set

Required by `Settings` validation:

- `DATABASE_URL`
- `ADMIN_CHAT_ID` (numeric string)
- `GROQ_API_KEY`
- `TOKEN_ENCRYPTION_KEY` (length >= 20)
- `JWT_SECRET_KEY`

## 3) Run quality gate with explicit Python executable

If `venv/bin/python` is unavailable in your environment, run:

```bash
PYTHON_BIN=python bash dev_scripts/codex_extended_quality_gate.sh
```

The quality gate auto-loads environment values in this order:

1. `.env.test`
2. `.env.test.example`

and prints only masked presence status (`SET`/`NOT SET`) for required keys.

`pytest` now runs without hard dependency on `pytest-cov`.
If `pytest-cov` is installed, coverage run is executed as an additional review check.

## 4) Secrets policy

- Keep only dummy/local values in `.env.test` for CI/local checks.
- Never commit production secrets.
- In logs/reporting, expose env presence as SET/NOT SET instead of raw values.
