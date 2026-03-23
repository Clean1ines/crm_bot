#!/usr/bin/env python3
"""Check that all modified files compile and imports work."""
import sys
import importlib

def check_import(module_name):
    try:
        importlib.import_module(module_name)
        print(f"✓ {module_name} imports OK")
        return True
    except Exception as e:
        print(f"✗ {module_name} failed: {e}")
        return False

def main():
    modules = [
        "src.database.models",
        "src.database.repositories.user_repository",
        "src.database.repositories.project_repository",
        "src.api.dependencies",
        "src.api.auth",
        "src.api.projects",
        "src.admin.handlers",
    ]
    all_ok = True
    for mod in modules:
        if not check_import(mod):
            all_ok = False
    if all_ok:
        print("\n✅ All modules imported successfully.")
        sys.exit(0)
    else:
        print("\n❌ Some imports failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
