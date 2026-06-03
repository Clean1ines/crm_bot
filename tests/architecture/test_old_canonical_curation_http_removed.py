from __future__ import annotations

from pathlib import Path


def test_old_canonical_curation_http_route_is_removed() -> None:
    assert not Path("src/interfaces/http/knowledge_curation.py").exists()

    app_source = Path("src/interfaces/http/app.py").read_text(encoding="utf-8")
    init_source = Path("src/interfaces/http/__init__.py").read_text(encoding="utf-8")

    assert "from src.interfaces.http.knowledge_curation import" not in app_source
    assert "knowledge_curation_router" not in app_source
    assert "app.include_router(knowledge_curation_router)" not in app_source
    assert "knowledge_curation" not in init_source


def test_fastapi_app_does_not_mount_old_canonical_curation_routes() -> None:
    from src.interfaces.http.app import app

    mounted_paths = {getattr(route, "path", "") for route in app.routes}

    assert not any(
        "/knowledge/" in path and "/curation" in path for path in mounted_paths
    )


def test_workbench_curation_and_publication_are_the_supported_path() -> None:
    surface_curation_source = Path(
        "src/application/services/faq_workbench_surface_curation_service.py"
    ).read_text(encoding="utf-8")
    runtime_publication_source = Path(
        "src/application/services/faq_workbench_runtime_publication_service.py"
    ).read_text(encoding="utf-8")

    assert "FaqWorkbenchSurfaceCurationService" in surface_curation_source
    assert "CurationChangeOperation" in surface_curation_source
    assert "FaqWorkbenchRuntimePublicationService" in runtime_publication_source


def test_old_canonical_curation_tests_are_removed() -> None:
    assert not Path("tests/test_knowledge_curation_domain.py").exists()
    assert not Path("tests/test_knowledge_curation_service.py").exists()
    assert not Path(
        "tests/architecture/test_kcd_stage_h_knowledge_edit_actions_guard.py"
    ).exists()
