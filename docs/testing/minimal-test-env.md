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

Primary local path:

```bash
PYTHON_BIN=venv/bin/python AUTO_BOOTSTRAP_ENV=0 bash dev_scripts/codex_extended_quality_gate.sh
```

Primary Codex/cloud path:

```bash
bash dev_scripts/bootstrap_codex_env.sh
PYTHON_BIN=.codex_venv/bin/python AUTO_BOOTSTRAP_ENV=0 bash dev_scripts/codex_extended_quality_gate.sh
```

By default, the quality gate auto-bootstraps a local isolated environment
(`.codex_venv`) and installs `requirements.txt` + `requirements-dev.txt` when
required tooling is missing. This reduces "works locally but fails in Codex" drift.

Environment invariant for Codex/cloud runs:

- Python 3.12.x only
- `pytest_asyncio` present
- `pytest_env` present

When this invariant is broken, the expected status is `ENV_FAIL` (environment issue),
not product test regression.

Disable bootstrap only if you fully manage the interpreter yourself:

```bash
AUTO_BOOTSTRAP_ENV=0 PYTHON_BIN=venv/bin/python bash dev_scripts/codex_extended_quality_gate.sh
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
