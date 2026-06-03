from __future__ import annotations

from pathlib import Path


REMOVED_LEGACY_SERVICE_FILES = (
    "src/application/services/knowledge_answer_candidate_builder.py",
    "src/application/services/knowledge_compiler_batch_builder.py",
    "src/application/services/knowledge_structured_ingestion_service.py",
    "src/application/services/knowledge_answer_resolution_service.py",
    "src/application/services/knowledge_stage_e_publication_helpers.py",
    "src/application/services/knowledge_canonical_publication_builder.py",
    "src/application/services/knowledge_compiled_entry_cleanup.py",
    "src/application/services/knowledge_surface_ingestion_service.py",
    "src/application/services/knowledge_processing_report_builder.py",
    "src/application/services/knowledge_semantic_ingestion_helpers.py",
)

FORBIDDEN_RUNTIME_IMPORTS = (
    "src.application.services.knowledge_answer_candidate_builder",
    "src.application.services.knowledge_compiler_batch_builder",
    "src.application.services.knowledge_structured_ingestion_service",
    "src.application.services.knowledge_answer_resolution_service",
    "src.application.services.knowledge_stage_e_publication_helpers",
    "src.application.services.knowledge_canonical_publication_builder",
    "src.application.services.knowledge_compiled_entry_cleanup",
    "src.application.services.knowledge_surface_ingestion_service",
    "src.application.services.knowledge_processing_report_builder",
    "src.application.services.knowledge_semantic_ingestion_helpers",
)


def test_legacy_service_builder_files_are_removed() -> None:
    for path in REMOVED_LEGACY_SERVICE_FILES:
        assert not Path(path).exists(), f"{path} must be physically removed"


def test_src_no_longer_imports_removed_legacy_services() -> None:
    for source_path in Path("src").rglob("*.py"):
        source = source_path.read_text(encoding="utf-8")

        for forbidden in FORBIDDEN_RUNTIME_IMPORTS:
            assert forbidden not in source, (
                f"{source_path} must not import removed legacy service {forbidden}"
            )
