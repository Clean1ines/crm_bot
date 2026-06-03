from __future__ import annotations

from pathlib import Path


PORTS = Path("src/application/ports/knowledge_workbench.py")
SERVICE = Path("src/application/services/faq_workbench_claim_observations_service.py")
ORCH = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
REPO = Path("src/infrastructure/db/knowledge_workbench_repository.py")
OBS_REPO = Path("src/infrastructure/db/workbench_observability_repository.py")


def test_claim_observations_port_exposes_idempotent_usage_sync() -> None:
    source = PORTS.read_text(encoding="utf-8")

    assert "class KnowledgeWorkbenchClaimObservationsRepositoryPort" in source
    assert "sync_processing_run_llm_usage_totals" in source


def test_orchestrator_preserves_invocation_total_tokens() -> None:
    source = ORCH.read_text(encoding="utf-8")

    assert "total_tokens=invocation.token_usage.total_tokens" in source
    assert "total_tokens=llm_metadata.total_tokens" in source


def test_claim_observations_service_syncs_processing_run_usage_after_persistence() -> (
    None
):
    source = SERVICE.read_text(encoding="utf-8")

    normalized = " ".join(source.split())
    assert "command.total_tokens" in normalized
    assert "command.prompt_tokens + command.completion_tokens" in normalized
    assert "sync_processing_run_llm_usage_totals" in source
    assert "processing_run_id=command.registry.processing_run_id" in source


def test_workbench_repository_recalculates_usage_from_processing_node_runs() -> None:
    source = REPO.read_text(encoding="utf-8")

    assert "async def sync_processing_run_llm_usage_totals(" in source
    assert "FROM knowledge_workbench_processing_node_runs AS node" in source
    assert "COALESCE(SUM(node.prompt_tokens), 0)::int AS total_prompt_tokens" in source
    assert (
        "COALESCE(SUM(node.completion_tokens), 0)::int AS total_completion_tokens"
        in source
    )
    assert "COALESCE(SUM(node.total_tokens), 0)::int AS total_tokens" in source
    assert "COUNT(*) FILTER" in source
    assert "total_llm_calls = usage.total_llm_calls" in source


def test_document_card_read_model_reads_synced_processing_run_usage() -> None:
    source = OBS_REPO.read_text(encoding="utf-8")

    assert "COALESCE(pr.total_prompt_tokens, 0) AS prompt_tokens" in source
    assert "COALESCE(pr.total_completion_tokens, 0) AS completion_tokens" in source
    assert "COALESCE(pr.total_tokens, 0) AS total_tokens" in source
    assert "COALESCE(pr.total_llm_calls, 0) AS llm_call_count" in source


def test_usage_sync_does_not_import_groq_or_legacy_compiler_into_application() -> None:
    combined = SERVICE.read_text(encoding="utf-8") + ORCH.read_text(encoding="utf-8")

    forbidden = (
        "AsyncGroq",
        "GroqLlmJsonInvocationAdapter",
        "RotatingAsyncGroq",
        "GROQ_API_KEY",
        "knowledge_surface_compiler",
        "process_knowledge_upload",
        "AnswerCandidate",
        "CandidateCluster",
    )
    for marker in forbidden:
        assert marker not in combined


def test_shared_inmemory_workbench_repository_supports_usage_sync() -> None:
    source = Path("tests/application/workbench/helpers.py").read_text(encoding="utf-8")

    assert "class InMemoryWorkbenchRepository" in source
    assert "async def sync_processing_run_llm_usage_totals(" in source
