#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export DATABASE_URL="${DATABASE_URL:-postgresql://test:test@localhost:5432/test}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-test-secret-key-for-unit-tests}"
export ADMIN_CHAT_ID="${ADMIN_CHAT_ID:-123456789}"
export GROQ_API_KEY="${GROQ_API_KEY:-test-groq-api-key}"
export TOKEN_ENCRYPTION_KEY="${TOKEN_ENCRYPTION_KEY:-test-token-encryption-key-long-enough}"
export ENVIRONMENT="${ENVIRONMENT:-test}"
export MODEL_USAGE_MONTHLY_TOKEN_BUDGET="${MODEL_USAGE_MONTHLY_TOKEN_BUDGET:-1000000}"
export VOYAGE_FREE_MONTHLY_TOKENS="${VOYAGE_FREE_MONTHLY_TOKENS:-1000000}"
export MODEL_USAGE_COUNTER_ENABLED="${MODEL_USAGE_COUNTER_ENABLED:-false}"

if [[ -x "venv/bin/python" ]]; then
  PYTHON_BIN="venv/bin/python"
else
  PYTHON_BIN="python"
fi

echo "Using Python: $PYTHON_BIN"
"$PYTHON_BIN" --version

"$PYTHON_BIN" -m pytest \
  tests/infrastructure/test_knowledge_resume_processing_handler.py \
  tests/domain/test_knowledge_document_pipeline.py \
  tests/architecture/test_knowledge_pipeline_queue_registry_contract.py \
  tests/architecture/test_knowledge_pipeline_contract_guards.py \
  tests/architecture/test_knowledge_pipeline_stage_literals_guard.py \
  tests/application/services/test_knowledge_service_runtime.py
