from __future__ import annotations

from pathlib import Path


QUEUE_DOMAIN = Path(
    "src/domain/project_plane/knowledge_workbench/registry_application_queue.py"
)
RUNTIME_COVERAGE = Path(
    "tests/architecture/test_workbench_graph_runtime_coverage_audit.py"
)
REGISTRY_APP_SERVICE = Path(
    "src/application/services/faq_workbench_registry_application_service.py"
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_registry_application_queue_domain_declares_single_writer_freshness_gate() -> (
    None
):
    source = _read(QUEUE_DOMAIN)

    assert "RegistryApplicationQueueItem" in source
    assert "RegistryApplicationFreshnessDecision" in source
    assert "decide_registry_application_freshness" in source
    assert "ensure_registry_application_can_mutate" in source
    assert "REBASE_REQUIRED" in source
    assert "WAIT_FOR_SNAPSHOT" in source
    assert "SKIP_TERMINAL" in source

    forbidden = (
        "RegistryUpdateAppliedBy.LLM_ADVISORY",
        "create_registry_update_applications",
        "upsert_question_registry_entries",
    )
    for marker in forbidden:
        assert marker not in source


def test_runtime_gap_stays_explicit_until_real_single_writer_queue_is_wired() -> None:
    coverage_source = _read(RUNTIME_COVERAGE)
    registry_app_source = _read(REGISTRY_APP_SERVICE)

    assert "single-writer registry application queue" in coverage_source
    assert "No real parallel worker leasing" in coverage_source

    assert "ApplyFactRegistrySnapshotCommand" in registry_app_source
    assert "ApplyFactRegistrySnapshotCommand" in registry_app_source
    assert "canonical_facts" in registry_app_source
    assert "fact_relations" in registry_app_source
