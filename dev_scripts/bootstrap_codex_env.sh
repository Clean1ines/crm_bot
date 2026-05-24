#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.codex_venv}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ENV_FAIL: python executable not found: ${PYTHON_BIN}" >&2
  exit 20
fi

python_version="$(${PYTHON_BIN} - << 'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

if [[ "${python_version}" != "3.12" ]]; then
  echo "ENV_FAIL: expected Python 3.12.x, got ${python_version}" >&2
  exit 20
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r requirements.txt -r requirements-dev.txt

"${VENV_DIR}/bin/python" - << 'PY'
required = ["pytest", "pytest_asyncio", "pytest_cov", "pytest_env", "ruff", "mypy"]
missing = []
for module in required:
    try:
        __import__(module)
    except Exception as exc:
        missing.append(f"{module}: {exc}")
if missing:
    print("ENV_FAIL: missing required test modules")
    for item in missing:
        print(f"- {item}")
    raise SystemExit(20)
print("test toolchain OK")
PY

echo "PYTHON_BIN=${VENV_DIR}/bin/python"
