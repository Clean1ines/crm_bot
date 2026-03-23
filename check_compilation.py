#!/usr/bin/env python3
"""Check that all Python files in the project compile and all modules can be imported.

This script:
1. Checks syntax of all .py files (except excluded directories).
2. Attempts to import every module under src/ (excluding __pycache__, migrations, frontend, etc.).
3. Loads environment variables from .env if present to satisfy config dependencies.
4. Exits with code 1 if any errors are found.
"""

import os
import sys
import ast
import importlib
import pathlib
from typing import List, Tuple

# Add project root to PYTHONPATH to allow imports
sys.path.insert(0, os.path.abspath('.'))

# Optional: load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("Loaded environment from .env")
except ImportError:
    print("Warning: python-dotenv not installed, skipping .env load")

# Directories to exclude when scanning
EXCLUDE_DIRS = {'.venv', 'venv', 'env', '__pycache__', 'frontend', 'migrations', 'db_audit', '.vscode', 'node_modules', 'dist', 'build'}

def find_py_files(root_dir: str) -> List[str]:
    """Return list of all .py files under root_dir, excluding EXCLUDE_DIRS."""
    py_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Remove excluded directories in-place
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for file in filenames:
            if file.endswith('.py'):
                full_path = os.path.join(dirpath, file)
                py_files.append(full_path)
    return py_files

def check_syntax(file_path: str) -> Tuple[bool, str]:
    """Check Python syntax of a file. Return (ok, error_message)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source, filename=file_path)
        return True, ""
    except SyntaxError as e:
        return False, f"{file_path}:{e.lineno}:{e.offset} {e.msg}"
    except Exception as e:
        return False, f"{file_path}: {e}"

def module_name_from_path(file_path: str, root: str) -> str:
    """Convert file path relative to root to module name (dots)."""
    rel_path = os.path.relpath(file_path, root)
    # Remove .py extension
    rel_path = rel_path[:-3]
    # Replace os.sep with .
    return rel_path.replace(os.sep, '.')

def check_import(module_name: str) -> Tuple[bool, str]:
    """Attempt to import a module. Return (ok, error_message)."""
    try:
        importlib.import_module(module_name)
        return True, ""
    except Exception as e:
        return False, f"{module_name}: {e}"

def main():
    project_root = os.path.abspath('.')
    src_dir = os.path.join(project_root, 'src')
    if not os.path.isdir(src_dir):
        print("Error: src directory not found. Are you running from project root?")
        sys.exit(1)

    # 1. Syntax check all .py files in src (and also root if any)
    print("=== Syntax check ===")
    all_py_files = []
    for root_dir in [project_root, src_dir]:
        if os.path.isdir(root_dir):
            all_py_files.extend(find_py_files(root_dir))

    syntax_errors = []
    for f in sorted(all_py_files):
        ok, err = check_syntax(f)
        if ok:
            print(f"✓ {f}")
        else:
            print(f"✗ {err}")
            syntax_errors.append(err)

    if syntax_errors:
        print(f"\n❌ {len(syntax_errors)} syntax errors found.")
        sys.exit(1)
    else:
        print(f"✅ Syntax OK for {len(all_py_files)} files.\n")

    # 2. Import check all modules under src/
    print("=== Import check ===")
    module_files = find_py_files(src_dir)
    module_names = [module_name_from_path(f, project_root) for f in module_files]

    # Remove __init__.py modules (they may be imported automatically)
    module_names = [m for m in module_names if not m.endswith('.__init__')]

    import_errors = []
    for name in sorted(module_names):
        ok, err = check_import(name)
        if ok:
            print(f"✓ {name}")
        else:
            print(f"✗ {err}")
            import_errors.append(err)

    if import_errors:
        print(f"\n❌ {len(import_errors)} import errors found.")
        sys.exit(1)
    else:
        print(f"✅ All {len(module_names)} modules imported successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
