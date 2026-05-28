#!/usr/bin/env bash
set -euo pipefail

python -m ruff format --check src tests
python -m ruff check src tests
python -m mypy src
python -m pytest -q tests/infrastructure/llm/test_groq_quota_state.py -o addopts=''

if [ -f frontend/package.json ]; then
  npm --prefix frontend run type-check
fi
