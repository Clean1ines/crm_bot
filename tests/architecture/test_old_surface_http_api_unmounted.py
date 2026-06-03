from __future__ import annotations

from pathlib import Path


def test_old_surface_http_router_is_not_mounted_in_app() -> None:
    source = Path("src/interfaces/http/app.py").read_text(encoding="utf-8")

    assert "knowledge_surface_router" not in source
    assert "src.interfaces.http.knowledge_surface" not in source
    assert "app.include_router(knowledge_surface_router)" not in source


def test_http_package_root_does_not_force_import_old_surface_lifecycle() -> None:
    source = Path("src/interfaces/http/__init__.py").read_text(encoding="utf-8")

    assert "knowledge_surface" not in source


def test_old_surface_http_modules_are_removed() -> None:
    removed_files = (
        Path("src/interfaces/http/knowledge_surface.py"),
        Path("src/interfaces/http/knowledge_surface_lifecycle.py"),
        Path("src/interfaces/http/knowledge_surface_upload_guard.py"),
    )

    for path in removed_files:
        assert not path.exists(), f"{path} should be removed after Workbench cutover"
