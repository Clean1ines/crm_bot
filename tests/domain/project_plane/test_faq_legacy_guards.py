from __future__ import annotations

from pathlib import Path


RETIRED_MODULE = Path("src/domain/project_plane/knowledge_preprocessing.py")
SRC_ROOT = Path("src")


def test_legacy_knowledge_preprocessing_module_is_retired_trap_only() -> None:
    source = RETIRED_MODULE.read_text(encoding="utf-8")

    assert "class RetiredLegacyKnowledgePreprocessingError" in source
    assert "def __getattr__(name: str) -> object:" in source
    assert "belongs to the retired legacy knowledge preprocessing layer" in source
    assert "MODE_FAQ" not in source
    assert "parse_preprocessing_payload" not in source
    assert "normalize_preprocessing_mode" not in source


def test_production_code_does_not_import_retired_knowledge_preprocessing() -> None:
    offenders: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        if path == RETIRED_MODULE:
            continue
        source = path.read_text(encoding="utf-8")
        if "src.domain.project_plane.knowledge_preprocessing import" in source:
            offenders.append(str(path))
        if "from src.domain.project_plane import knowledge_preprocessing" in source:
            offenders.append(str(path))

    assert offenders == []


def test_current_knowledge_processing_modes_are_not_in_retired_module() -> None:
    source = Path("src/domain/project_plane/knowledge_processing_modes.py").read_text(
        encoding="utf-8"
    )

    assert "MODE_FAQ" in source
    assert "MODE_PRICE_LIST" in source
    assert "normalize_knowledge_processing_mode" in source
    assert "require_faq_workbench_mode" in source
    assert "RetiredLegacyKnowledgePreprocessingError" not in source
