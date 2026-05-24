#!/usr/bin/env bash
set -u

ROOT="${ROOT:-$(pwd)}"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-venv/bin/python}"
TEST_ENV_FILE="${TEST_ENV_FILE:-.env.test}"
TEST_ENV_FALLBACK_FILE="${TEST_ENV_FALLBACK_FILE:-.env.test.example}"
AUTO_BOOTSTRAP_ENV="${AUTO_BOOTSTRAP_ENV:-1}"
BOOTSTRAP_VENV_DIR="${BOOTSTRAP_VENV_DIR:-.codex_venv}"
TS="$(date -u +%Y%m%d_%H%M%S)"
ISO_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RAW="reports/codex-extended-quality-gate-raw-${TS}.txt"
TMP_SUMMARY="$(mktemp)"
TMP_DETAILS="$(mktemp)"

mkdir -p reports

RESULT_GROUPS=()
RESULT_CHECKS=()
RESULT_RESULTS=()
RESULT_EXITS=()
REQUIRED_FAILED=0

cleanup() {
  rm -f "$TMP_SUMMARY" "$TMP_DETAILS"
}
trap cleanup EXIT

append_result() {
  RESULT_GROUPS+=("$1")
  RESULT_CHECKS+=("$2")
  RESULT_RESULTS+=("$3")
  RESULT_EXITS+=("$4")
}

run_check() {
  local group="$1"
  local name="$2"
  local cmd="$3"
  local rc=0
  local result="PASS"

  {
    echo
    echo "===== ${group}: ${name} ====="
    echo "\$ ${cmd}"
  } >> "$TMP_DETAILS"

  bash -lc "$cmd" >> "$TMP_DETAILS" 2>&1
  rc=$?

  {
    echo "exit=${rc}"
    echo
  } >> "$TMP_DETAILS"

  if [[ "$group" == "REQUIRED" ]]; then
    if [[ "$rc" -ne 0 ]]; then
      result="FAIL"
      REQUIRED_FAILED=1
    fi
  else
    if [[ "$rc" -ne 0 ]]; then
      result="REVIEW"
    fi
  fi

  append_result "$group" "$name" "$result" "$rc"
}

load_test_env_file() {
  local file_path="$1"
  if [[ -f "$file_path" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$file_path"
    set +a
    return 0
  fi
  return 1
}

mask_presence() {
  local value="$1"
  if [[ -n "$value" ]]; then
    echo "SET"
  else
    echo "NOT SET"
  fi
}

ensure_python_bin() {
  if [[ -x "$PYTHON_BIN" ]]; then
    return 0
  fi
  if [[ "$AUTO_BOOTSTRAP_ENV" != "1" ]]; then
    echo "ERROR: PYTHON_BIN '$PYTHON_BIN' not found and AUTO_BOOTSTRAP_ENV=0" >&2
    return 1
  fi
  python -m venv "$BOOTSTRAP_VENV_DIR"
  PYTHON_BIN="$BOOTSTRAP_VENV_DIR/bin/python"
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PYTHON_BIN" -m pip install -r requirements.txt -r requirements-dev.txt
  return 0
}

ensure_python_stack() {
  local required_modules=(pytest pytest_cov ruff mypy)
  local missing=0
  for module in "${required_modules[@]}"; do
    if ! "$PYTHON_BIN" -c "import ${module}" >/dev/null 2>&1; then
      missing=1
      break
    fi
  done
  if [[ "$missing" -eq 1 && "$AUTO_BOOTSTRAP_ENV" == "1" ]]; then
    "$PYTHON_BIN" -m pip install -r requirements.txt -r requirements-dev.txt
  fi
}

fail_env() {
  echo "ENV_FAIL: $1" >&2
  exit 20
}

git_branch="$(git branch --show-current 2>/dev/null || true)"
git_commit="$(git rev-parse HEAD 2>/dev/null || true)"
git_status="$(git status --short 2>/dev/null || true)"
virtual_env_value="${VIRTUAL_ENV:-}"

ensure_python_bin || exit 1
ensure_python_stack

python_minor="$($PYTHON_BIN - << 'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
if [[ "$python_minor" != "3.12" ]]; then
  fail_env "expected Python 3.12.x, got ${python_minor}"
fi

for module in pytest_asyncio pytest_env; do
  if ! "$PYTHON_BIN" -c "import ${module}" >/dev/null 2>&1; then
    fail_env "required pytest plugin/module is missing: ${module}"
  fi
done

loaded_env_source="none"
if load_test_env_file "$TEST_ENV_FILE"; then
  loaded_env_source="$TEST_ENV_FILE"
elif load_test_env_file "$TEST_ENV_FALLBACK_FILE"; then
  loaded_env_source="$TEST_ENV_FALLBACK_FILE"
fi

database_url_status="$(mask_presence "${DATABASE_URL:-}")"
admin_chat_id_status="$(mask_presence "${ADMIN_CHAT_ID:-}")"
groq_api_key_status="$(mask_presence "${GROQ_API_KEY:-}")"
token_encryption_key_status="$(mask_presence "${TOKEN_ENCRYPTION_KEY:-}")"
jwt_secret_key_status="$(mask_presence "${JWT_SECRET_KEY:-}")"

run_check "REQUIRED" "python executable" \
  "${PYTHON_BIN} -c 'import sys; print(sys.executable); print(sys.version); print(\"prefix=\", sys.prefix); print(\"base_prefix=\", sys.base_prefix)'"

run_check "REQUIRED" "pip check" \
  "${PYTHON_BIN} -m pip check"

run_check "REQUIRED" "ruff version" \
  "${PYTHON_BIN} -m ruff --version"

run_check "REQUIRED" "mypy version" \
  "${PYTHON_BIN} -m mypy --version"

run_check "REQUIRED" "pytest version" \
  "${PYTHON_BIN} -m pytest --version"

run_check "REQUIRED" "python version is 3.12" \
  "${PYTHON_BIN} -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'"

run_check "REQUIRED" "pytest async plugin availability" \
  "${PYTHON_BIN} -c 'import pytest_asyncio; print(pytest_asyncio.__version__)'"

run_check "REQUIRED" "pytest env plugin availability" \
  "${PYTHON_BIN} -c 'import pytest_env; print(pytest_env.__version__)'"

pytest_cov_available=0
if ${PYTHON_BIN} -c 'import pytest_cov' >/dev/null 2>&1; then
  pytest_cov_available=1
fi

if [[ "$pytest_cov_available" -eq 1 ]]; then
  run_check "REVIEW" "pytest-cov version" \
    "${PYTHON_BIN} -c 'import pytest_cov; print(pytest_cov.__version__)'"
else
  append_result "REVIEW" "pytest-cov version" "REVIEW" "1"
fi

run_check "REVIEW" "bandit version" \
  "${PYTHON_BIN} -m bandit --version"

run_check "REVIEW" "pip-audit version" \
  "${PYTHON_BIN} -m pip_audit --version"

run_check "REVIEW" "pyinstrument version" \
  "${PYTHON_BIN} -m pyinstrument --version"

run_check "REVIEW" "radon version" \
  "${PYTHON_BIN} -m radon --version"

run_check "REQUIRED" "git diff check" \
  "git diff --check"

run_check "REQUIRED" "merge conflict marker scan" \
  "! rg -n '^(<<<<<<<|=======|>>>>>>>)' --glob '!reports/**' --glob '!htmlcov/**' --glob '!frontend/dist/**' ."

run_check "REQUIRED" "ruff format check" \
  "${PYTHON_BIN} -m ruff format --check src tests"

run_check "REQUIRED" "ruff check" \
  "${PYTHON_BIN} -m ruff check src tests"

run_check "REQUIRED" "mypy src" \
  "${PYTHON_BIN} -m mypy src"

run_check "REQUIRED" "pytest full" \
  "${PYTHON_BIN} -m pytest -q"

if [[ "$pytest_cov_available" -eq 1 ]]; then
  run_check "REVIEW" "pytest with coverage" \
    "${PYTHON_BIN} -m pytest -q --cov=src --cov-report=term-missing --cov-report=html"
else
  append_result "REVIEW" "pytest with coverage" "REVIEW" "1"
fi

run_check "REVIEW" "pip-audit" \
  "${PYTHON_BIN} -m pip_audit"

run_check "REVIEW" "bandit src" \
  "${PYTHON_BIN} -m bandit -r src"

run_check "REVIEW" "radon C hotspots" \
  "${PYTHON_BIN} -m radon cc src -s -n C -e '*/__pycache__/*,*/venv/*,*/.venv/*,*/node_modules/*,*/htmlcov/*,*/reports/*'"

run_check "REVIEW" "Any/type-ignore scan" \
  "rg -n '\\bAny\\b|typing import .*Any|cast\\(Any|# type: ignore|type: ignore\\[|ignore-errors' src tests || true"

run_check "REVIEW" "nosec inventory" \
  "rg -n '#\\s*nosec' src tests || true"

run_check "REVIEW" "mojibake inventory" \
  "rg -n 'Р[ІВЎЏЋЊЃЌЉЂ]|С[ЃЊЋЌЉЂ]' src tests frontend --glob '!frontend/dist/**' || true"

run_check "REVIEW" "domain boundary scan" \
  "rg -n 'from (fastapi|starlette|asyncpg|redis|httpx|aiohttp|telegram|langchain|langgraph)|import (fastapi|starlette|asyncpg|redis|httpx|aiohttp|telegram|langchain|langgraph)' src/domain || true"

run_check "REVIEW" "generated artifact scan" \
  "git status --short --ignored reports htmlcov frontend/dist 2>/dev/null || true"

run_check "REVIEW" "plain app import smoke" \
  "${PYTHON_BIN} -X importtime -c 'import src.interfaces.http.app'"

run_check "REVIEW" "pyinstrument import smoke" \
  "${PYTHON_BIN} -m pyinstrument -r text -m src.interfaces.http.app"

if [[ -f "frontend/package.json" ]]; then
  run_check "REVIEW" "frontend npm version" \
    "cd frontend && npm --version && node --version"

  run_check "REQUIRED" "frontend lint" \
    "cd frontend && npm run lint"

  run_check "REQUIRED" "frontend type-check" \
    "cd frontend && npm run type-check"

  run_check "REQUIRED" "frontend build" \
    "cd frontend && npm run build"
else
  append_result "REVIEW" "frontend npm version" "SKIP" "0"
  append_result "REQUIRED" "frontend lint" "SKIP" "0"
  append_result "REQUIRED" "frontend type-check" "SKIP" "0"
  append_result "REQUIRED" "frontend build" "SKIP" "0"
fi

{
  echo "# Codex extended quality gate"
  echo
  echo "- timestamp UTC: ${ISO_TS}"
  echo "- branch: ${git_branch}"
  echo "- commit: ${git_commit}"
  echo "- python_bin: \`${PYTHON_BIN}\`"
  echo "- VIRTUAL_ENV: \`${virtual_env_value}\`"
  echo "- test_env_source: \`${loaded_env_source}\`"
  echo
  echo "## Required env presence (masked)"
  echo
  echo "- DATABASE_URL: ${database_url_status}"
  echo "- ADMIN_CHAT_ID: ${admin_chat_id_status}"
  echo "- GROQ_API_KEY: ${groq_api_key_status}"
  echo "- TOKEN_ENCRYPTION_KEY: ${token_encryption_key_status}"
  echo "- JWT_SECRET_KEY: ${jwt_secret_key_status}"
  echo
  echo "## Git status"
  echo '```text'
  if [[ -n "$git_status" ]]; then
    echo "$git_status"
  fi
  echo '```'
  echo
  echo "## Results"
  echo
  echo "| Group | Check | Result | Exit |"
  echo "|---|---|---:|---:|"

  for idx in "${!RESULT_GROUPS[@]}"; do
    echo "| ${RESULT_GROUPS[$idx]} | ${RESULT_CHECKS[$idx]} | ${RESULT_RESULTS[$idx]} | ${RESULT_EXITS[$idx]} |"
  done

  echo
  echo "## Required checks"
  echo
  echo "These are hard blockers. The script exits non-zero if any of them fail:"
  echo
  echo "- python executable"
  echo "- pip check"
  echo "- ruff/mypy/pytest tool availability"
  echo "- git diff check"
  echo "- merge conflict marker scan"
  echo "- ruff format check"
  echo "- ruff check"
  echo "- mypy src"
  echo "- pytest full"
  echo "- frontend lint/type-check/build when frontend/package.json exists"
  echo
  echo "## Review-only checks"
  echo
  echo "These do not automatically fail the gate because they can require human triage or can produce contextual findings."
  echo "Codex must still avoid introducing new findings, or explain exactly why a finding is a false positive:"
  echo
  echo "- pip-audit"
  echo "- bandit"
  echo "- radon C hotspots"
  echo "- Any/type-ignore inventory"
  echo "- nosec inventory"
  echo "- mojibake inventory"
  echo "- domain boundary scan"
  echo "- generated artifact scan"
  echo "- import smoke"
  echo "- pyinstrument smoke"
  echo
  echo "## Raw artifact"
  echo
  echo "- raw log: \`${RAW}\`"
  echo
  echo "## Verdict"
  echo
  if [[ "$REQUIRED_FAILED" -eq 0 ]]; then
    echo "- PASS for mandatory quality gate"
    echo "- Review optional findings above and in raw artifact before shipping sensitive/security-related changes"
  else
    echo "- FAIL: at least one mandatory quality gate check failed"
    echo "- Fix REQUIRED failures before commit/deploy"
  fi
  echo
  echo "RAW=${RAW}"
} > "$TMP_SUMMARY"

cat "$TMP_SUMMARY" "$TMP_DETAILS" | tee "$RAW"

if [[ "$REQUIRED_FAILED" -ne 0 ]]; then
  exit 1
fi

exit 0
