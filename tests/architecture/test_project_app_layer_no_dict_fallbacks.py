from __future__ import annotations

from pathlib import Path


DELETED_LEGACY_SERVICE = Path("src/application/services/knowledge_service.py")


def test_legacy_knowledge_service_facade_is_deleted() -> None:
    assert not DELETED_LEGACY_SERVICE.exists()


def test_project_app_layer_does_not_import_legacy_knowledge_service_facade() -> None:
    offenders: list[str] = []
    forbidden = (
        "from src.application.services.knowledge_service import",
        "src.application.services.knowledge_service",
        "KnowledgeService(",
    )

    for root in (
        Path("src/application"),
        Path("src/interfaces"),
        Path("src/infrastructure"),
    ):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8", errors="ignore")
            for marker in forbidden:
                if marker in source:
                    offenders.append(f"{path}: {marker}")

    assert offenders == []
