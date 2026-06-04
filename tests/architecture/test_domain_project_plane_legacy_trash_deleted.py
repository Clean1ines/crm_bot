from __future__ import annotations

from pathlib import Path


DELETED_LEGACY_DOMAIN_FILES = (
    "src/application/services/knowledge_normalization_service.py",
    "src/application/services/markdown_structure_extractor.py",
    "src/application/ports/knowledge_document_parser_port.py",
    "src/domain/project_plane/knowledge_chunks.py",
    "src/domain/project_plane/knowledge_document_structure.py",
    "src/domain/project_plane/knowledge_chunk_classification.py",
    "src/domain/project_plane/knowledge_semantic_markers.py",
    "src/domain/project_plane/knowledge_acquisition.py",
    "src/domain/project_plane/knowledge_faq_resume_policy.py",
    "src/domain/project_plane/knowledge_semantic_builder.py",
    "src/domain/project_plane/knowledge_preprocessing_cleanup.py",
)


def test_zero_ref_legacy_domain_trash_files_are_deleted() -> None:
    for file_path in DELETED_LEGACY_DOMAIN_FILES:
        assert not Path(file_path).exists(), f"{file_path} should stay deleted"


def test_deleted_legacy_domain_trash_is_not_imported_by_production_code() -> None:
    deleted_modules = tuple(
        ".".join(Path(file_path).with_suffix("").parts)
        for file_path in DELETED_LEGACY_DOMAIN_FILES
    )

    offenders: list[str] = []
    for path in Path("src").rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="ignore")
        for module in deleted_modules:
            basename = module.rsplit(".", 1)[-1]
            if module in source or f"project_plane.{basename}" in source:
                offenders.append(f"{path}: {module}")

    assert offenders == []


def test_legacy_faq_resume_policy_test_is_deleted() -> None:
    assert not Path(
        "tests/domain/project_plane/test_knowledge_faq_resume_policy.py"
    ).exists()


def test_current_resume_path_is_workbench_manual_resume_not_legacy_faq_policy() -> None:
    assert Path("src/application/workbench_commands/manual_resume.py").exists()

    this_file = Path(__file__).resolve()
    offenders: list[str] = []
    for root in (Path("src"), Path("tests")):
        for candidate in root.rglob("*.py"):
            if candidate.resolve() == this_file:
                continue
            source = candidate.read_text(encoding="utf-8", errors="ignore")
            if "knowledge_faq_resume_policy" in source:
                offenders.append(str(candidate))

    assert offenders == []


def test_old_normalization_parser_island_tests_are_deleted() -> None:
    deleted_tests = (
        "tests/domain/test_knowledge_chunk_classification.py",
        "tests/domain/test_knowledge_document_structure.py",
        "tests/domain/test_knowledge_semantic_markers.py",
    )

    for file_path in deleted_tests:
        assert not Path(file_path).exists(), f"{file_path} should stay deleted"


def test_old_normalization_parser_island_is_not_imported_anywhere() -> None:
    forbidden = (
        "knowledge_normalization_service",
        "KnowledgeNormalizationService",
        "markdown_structure_extractor",
        "MarkdownStructureExtractor",
        "knowledge_document_parser_port",
        "KnowledgeDocumentParserPort",
        "src.domain.project_plane.knowledge_chunks",
        "src.domain.project_plane.knowledge_document_structure",
        "src.domain.project_plane.knowledge_chunk_classification",
        "src.domain.project_plane.knowledge_semantic_markers",
        "src.domain.project_plane.knowledge_acquisition",
        "KnowledgeChunkRole",
        "KnowledgeChunkDraft",
        "ParsedKnowledgeDocument",
        "KnowledgeDocumentSource",
        "classify_knowledge_chunk_role",
        "SemanticSourceUnit",
        "MarkdownKnowledgeSection",
    )

    self_files = {
        Path(__file__).resolve(),
        Path("tests/architecture/test_new_only_knowledge_ports.py").resolve(),
    }
    offenders: list[str] = []

    for root in (Path("src"), Path("tests")):
        for candidate in root.rglob("*.py"):
            if candidate.resolve() in self_files:
                continue
            source = candidate.read_text(encoding="utf-8", errors="ignore")
            for marker in forbidden:
                if marker in source:
                    offenders.append(f"{candidate}: {marker}")

    assert offenders == []


def test_current_workbench_sectioning_path_replaces_old_parser_island() -> None:
    assert Path("src/application/workbench/upload_service.py").exists()
    assert Path("src/domain/project_plane/knowledge_workbench").exists()
    assert Path("src/domain/project_plane/knowledge_workbench/__init__.py").exists()
    assert Path(
        "src/application/services/faq_workbench_claim_observations_service.py"
    ).exists()

    workbench_exports = Path(
        "src/domain/project_plane/knowledge_workbench/__init__.py"
    ).read_text(encoding="utf-8")
    assert "DocumentSection" in workbench_exports
