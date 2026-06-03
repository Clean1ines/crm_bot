from __future__ import annotations

from pathlib import Path


PORT = Path("src/application/ports/faq_workbench_claim_observations_generator.py")
GENERATOR = Path("src/infrastructure/llm/faq_workbench_claim_observations_generator.py")
ORCH = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
DOMAIN_INVOCATION = Path("src/domain/project_plane/llm_routing/invocations.py")


def test_llm_invocation_result_carries_failure_metadata() -> None:
    source = DOMAIN_INVOCATION.read_text(encoding="utf-8")

    assert "class LlmInvocationStatus" in source
    assert "RATE_LIMITED" in source
    assert "DAILY_LIMITED" in source
    assert "REQUEST_TOO_LARGE" in source
    assert "OUTPUT_TOO_LARGE" in source
    assert "PROVIDER_ERROR" in source
    assert "NETWORK_ERROR" in source
    assert "INVALID_JSON" in source
    assert "failure: LlmInvocationFailure | None" in source
    assert "attempts: tuple[LlmRouteAttempt, ...]" in source


def test_claim_observations_generator_raises_typed_invocation_error() -> None:
    port_source = PORT.read_text(encoding="utf-8")
    generator_source = GENERATOR.read_text(encoding="utf-8")

    assert (
        "class FaqWorkbenchClaimObservationsGenerationError(RuntimeError)" in port_source
    )
    assert "self.result = result" in port_source
    assert "self.status = result.status" in port_source
    assert "self.error_kind = error_kind" in port_source
    assert "class FaqWorkbenchClaimObservationsInvocationError(" in generator_source
    assert "FaqWorkbenchClaimObservationsGenerationError" in generator_source
    assert (
        "raise FaqWorkbenchClaimObservationsInvocationError(result)" in generator_source
    )


def test_typed_error_is_available_for_orchestrator_m6d2_followup() -> None:
    port_source = PORT.read_text(encoding="utf-8")
    generator_source = GENERATOR.read_text(encoding="utf-8")

    assert '"FaqWorkbenchClaimObservationsInvocationError"' in generator_source
    assert "FaqWorkbenchClaimObservationsGenerationError" in port_source
    assert "LlmJsonInvocationResult" in port_source


def test_application_orchestrator_still_has_no_groq_imports() -> None:
    source = ORCH.read_text(encoding="utf-8")

    forbidden = (
        "AsyncGroq",
        "GroqLlmJsonInvocationAdapter",
        "RotatingAsyncGroq",
        "GROQ_API_KEY",
    )
    for marker in forbidden:
        assert marker not in source


def test_claim_observations_generation_error_is_application_port_contract() -> None:
    port_source = PORT.read_text(encoding="utf-8")
    generator_source = GENERATOR.read_text(encoding="utf-8")

    assert (
        "class FaqWorkbenchClaimObservationsGenerationError(RuntimeError)" in port_source
    )
    assert "self.result = result" in port_source
    assert "self.error_kind = error_kind" in port_source
    assert "class FaqWorkbenchClaimObservationsInvocationError(" in generator_source
    assert "FaqWorkbenchClaimObservationsGenerationError" in generator_source


def test_application_orchestrator_can_catch_port_error_without_infra_import() -> None:
    source = ORCH.read_text(encoding="utf-8")

    assert "FaqWorkbenchClaimObservationsInvocationError" not in source
    assert (
        "src.infrastructure.llm.faq_workbench_claim_observations_generator" not in source
    )


def test_claim_observations_service_persists_generation_error_as_failed_node() -> None:
    source = Path(
        "src/application/services/faq_workbench_claim_observations_service.py"
    ).read_text(encoding="utf-8")

    assert "persist_claim_observations_generation_error" in source
    assert "ProcessingNodeStatus.FAILED" in source
    assert "ProcessingNodeArtifactType.ERROR_REPORT" in source
    assert "sync_processing_run_llm_usage_totals" in source


def test_orchestrator_catches_port_generation_error_without_infra_import() -> None:
    source = ORCH.read_text(encoding="utf-8")

    assert "except FaqWorkbenchClaimObservationsGenerationError as exc:" in source
    assert "persist_claim_observations_generation_error" in source
    assert "FaqWorkbenchClaimObservationsInvocationError" not in source
    assert (
        "src.infrastructure.llm.faq_workbench_claim_observations_generator" not in source
    )


def test_claim_observations_repository_port_exposes_generation_error_lifecycle_contract() -> (
    None
):
    source = Path("src/application/ports/knowledge_workbench.py").read_text(
        encoding="utf-8"
    )

    assert "class KnowledgeWorkbenchClaimObservationsRepositoryPort" in source
    assert "persist_claim_observations_generation_error_lifecycle" in source
    assert "document_status: KnowledgeDocumentStatus" in source
    assert "processing_run_status: ProcessingRunStatus" in source
    assert "resume_policy: ResumePolicy" in source
    assert "last_error" not in source


def test_generation_error_lifecycle_is_connected_from_service_to_repository() -> None:
    service_source = Path(
        "src/application/services/faq_workbench_claim_observations_service.py"
    ).read_text(encoding="utf-8")
    repo_source = Path(
        "src/infrastructure/db/knowledge_workbench_repository.py"
    ).read_text(encoding="utf-8")

    assert "_claim_observations_generation_error_lifecycle" in service_source
    assert "persist_claim_observations_generation_error_lifecycle(" in service_source
    assert "ProcessingRunStatus.PAUSED_QUOTA" in service_source
    assert "ProcessingRunStatus.PAUSED_PROVIDER" in service_source
    assert "ProcessingRunStatus.FAILED_VALIDATION" in service_source
    assert "ProcessingRunStatus.FAILED_FATAL" in service_source
    assert "ResumePolicy.AUTO_ALLOWED" in service_source
    assert "ResumePolicy.FORBIDDEN" in service_source

    assert (
        "async def persist_claim_observations_generation_error_lifecycle(" in repo_source
    )
    assert "UPDATE knowledge_workbench_documents" in repo_source
    assert "UPDATE knowledge_workbench_processing_runs" in repo_source
    assert "last_error_report_id = $7" in repo_source
    assert "last_user_message = $8" in repo_source
    assert "last_internal_error = $9" in repo_source


def test_card_builder_knows_llm_generation_error_reason_codes() -> None:
    source = Path("src/application/workbench/document_card_builder.py").read_text(
        encoding="utf-8"
    )

    assert "groq_daily_limit" in source
    assert "groq_rate_limit" in source
    assert "provider_error" in source
    assert "failed_validation" in source
    assert "failed_fatal" in source


def test_retired_workbench_document_handler_does_not_handle_section_generation_errors() -> None:
    source = Path("src/infrastructure/queue/handlers/workbench_document.py").read_text(
        encoding="utf-8"
    )

    assert "legacy process_workbench_document task is retired" in source
    assert "PermanentJobError" in source
    assert "FaqWorkbenchClaimObservationsGenerationError" not in source
    assert "persist_claim_observations_generation_error" not in source
    assert "WorkbenchProcessingCancelledError" not in source
    assert "TransientJobError" not in source


def test_registry_merge_error_handling_mirrors_claim_observations_failure_path() -> None:
    service_source = Path(
        "src/application/services/faq_workbench_registry_merge_service.py"
    ).read_text(encoding="utf-8")
    port_source = Path("src/application/ports/knowledge_workbench.py").read_text(
        encoding="utf-8"
    )
    repo_source = Path(
        "src/infrastructure/db/knowledge_workbench_repository.py"
    ).read_text(encoding="utf-8")

    assert "persist_registry_merge_generation_error" in service_source
    assert "RegistryMergeGenerationErrorLifecycleTransition" in service_source
    assert "ProcessingRunStatus.PAUSED_QUOTA" in service_source
    assert "ProcessingRunStatus.PAUSED_PROVIDER" in service_source
    assert "ProcessingRunStatus.FAILED_VALIDATION" in service_source
    assert "ProcessingRunStatus.FAILED_FATAL" in service_source
    assert "ResumePolicy.AUTO_ALLOWED" in service_source
    assert "ResumePolicy.FORBIDDEN" in service_source

    assert "persist_registry_merge_generation_error_lifecycle" in port_source
    assert "persist_registry_merge_generation_error_lifecycle" in repo_source
    assert "TransientJobError" not in Path(
        "src/infrastructure/queue/handlers/workbench_document.py"
    ).read_text(encoding="utf-8")
