from __future__ import annotations

from pathlib import Path


POLICY_INTEGRATION_TARGETS = {
    "src/application/workbench/answer_deduplication.py": (
        "knowledge_workbench.answer_unit_policy",
        "decide_answer_unit_merge",
    ),
    "src/application/services/faq_workbench_surface_materialization_service.py": (
        "knowledge_workbench.evidence_refs",
        "require_grounded_evidence",
        "dedupe_evidence_refs",
    ),
    "src/application/services/faq_workbench_registry_application_service.py": (
        "knowledge_workbench.registry_merge_policy",
        "knowledge_workbench.question_relations",
        "decide_registry_merge",
    ),
    "src/application/workbench_observability/import_quality.py": (
        "knowledge_workbench.import_quality_policy",
        "decide_import_quality_action",
    ),
}

DOMAIN_POLICY_FILES = (
    "src/domain/project_plane/knowledge_workbench/answer_unit_policy.py",
    "src/domain/project_plane/knowledge_workbench/evidence_refs.py",
    "src/domain/project_plane/knowledge_workbench/question_relations.py",
    "src/domain/project_plane/knowledge_workbench/registry_merge_policy.py",
    "src/domain/project_plane/knowledge_workbench/import_quality_policy.py",
)

LEGACY_DONOR_RUNTIME_MARKERS = (
    "knowledge_answer_resolution_service",
    "knowledge_compiled_entry_cleanup",
    "knowledge_canonical_publication_builder",
    "knowledge_structured_ingestion_service",
    "knowledge_processing_report_builder",
    "knowledge_answer_candidate_builder",
    "knowledge_compiler_batch_builder",
    "knowledge_compilation",
    "AnswerCandidate",
    "CandidateCluster",
    "CompilerRun",
    "CompilerBatch",
    "CompilerRunStatus",
    "KnowledgeAnswerCandidatePort",
)


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_workbench_application_uses_uplifted_domain_policies() -> None:
    for path, required_markers in POLICY_INTEGRATION_TARGETS.items():
        source = _read(path)

        for marker in required_markers:
            assert marker in source, f"{path} must use {marker}"


def test_workbench_policy_integration_does_not_import_legacy_donors() -> None:
    for path in POLICY_INTEGRATION_TARGETS:
        source = _read(path)

        for marker in LEGACY_DONOR_RUNTIME_MARKERS:
            assert marker not in source, f"{path} must not reference {marker}"


def test_uplifted_domain_policy_modules_stay_free_of_legacy_runtime() -> None:
    for path in DOMAIN_POLICY_FILES:
        source = _read(path)

        for marker in LEGACY_DONOR_RUNTIME_MARKERS:
            assert marker not in source, f"{path} must not reference {marker}"


def test_old_donor_services_are_not_workbench_runtime_dependencies() -> None:
    workbench_runtime_targets = (
        "src/application/services/faq_workbench_document_processing_orchestrator.py",
        "src/application/services/faq_workbench_registry_application_service.py",
        "src/application/services/faq_workbench_claim_observations_service.py",
        "src/application/services/faq_workbench_surface_materialization_service.py",
        "src/application/services/faq_workbench_runtime_publication_service.py",
        "src/application/workbench/answer_deduplication.py",
        "src/application/workbench_observability/import_quality.py",
        "src/infrastructure/queue/handlers/workbench_document.py",
        "src/interfaces/composition/faq_workbench_upload.py",
    )

    donor_module_imports = (
        "src.application.services.knowledge_answer_resolution_service",
        "src.application.services.knowledge_compiled_entry_cleanup",
        "src.application.services.knowledge_canonical_publication_builder",
        "src.application.services.knowledge_structured_ingestion_service",
        "src.application.services.knowledge_processing_report_builder",
        "src.application.services.knowledge_answer_candidate_builder",
        "src.application.services.knowledge_compiler_batch_builder",
    )

    for path in workbench_runtime_targets:
        source = _read(path)

        for marker in donor_module_imports:
            assert marker not in source, f"{path} must not import {marker}"
