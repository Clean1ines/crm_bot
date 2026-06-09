from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

OLD_ORCHESTRATION_PATHS = (
    ROOT / "src" / "application" / "services",
    ROOT / "src" / "infrastructure" / "queue" / "handlers",
)

FORBIDDEN_NEW_CANONICAL_MARKERS = (
    "ClaimExtractionWorkItemUnitOfWorkPort",
    "ProcessClaimExtractionWorkItem",
    "RunClaimExtractionWorkItem",
    "ExecuteClaimExtractionWorkItem",
)


def test_claim_extraction_orchestration_boundary_lives_in_new_context() -> None:
    expected = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "extraction"
        / "application"
        / "ports"
        / "claim_extraction_work_item_unit_of_work_port.py"
    )

    assert expected.exists()


def test_old_services_and_queue_handlers_do_not_define_new_orchestration_contracts() -> (
    None
):
    offenders: list[str] = []

    for root in OLD_ORCHESTRATION_PATHS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if path.name == "__init__.py":
                continue
            text = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN_NEW_CANONICAL_MARKERS:
                if marker in text:
                    offenders.append(
                        f"{path.relative_to(ROOT)} contains new orchestration marker {marker!r}",
                    )

    assert not offenders, (
        "New claim extraction orchestration contracts must live under "
        "src/contexts/knowledge_workbench/extraction, not legacy services or "
        "queue handlers:\n" + "\n".join(offenders)
    )


def test_create_extraction_work_items_lives_only_in_extraction_use_cases() -> None:
    expected_path = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "extraction"
        / "application"
        / "use_cases"
        / "create_extraction_work_items.py"
    )
    forbidden_source_management_path = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "source_management"
        / "application"
        / "use_cases"
        / "create_extraction_work_items.py"
    )

    assert expected_path.exists(), (
        "CreateExtractionWorkItems belongs to "
        "knowledge_workbench/extraction/application/use_cases"
    )
    assert not forbidden_source_management_path.exists(), (
        "Source Management must not own claim extraction WorkItem creation"
    )

    symbol_markers = (
        "CreateExtractionWorkItems",
        "CreateExtractionWorkItemsCommand",
        "CreateExtractionWorkItemsResult",
        "CLAIM_EXTRACTION_WORK_KIND",
    )
    run_stage_path = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "extraction"
        / "application"
        / "use_cases"
        / "run_claim_extraction_stage.py"
    )
    resume_stage_path = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "extraction"
        / "application"
        / "use_cases"
        / "resume_claim_extraction_stage.py"
    )
    async_run_stage_path = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "extraction"
        / "application"
        / "use_cases"
        / "run_claim_extraction_stage_async.py"
    )
    allowed_files = {
        expected_path,
        run_stage_path,
        async_run_stage_path,
        resume_stage_path,
    }

    offenders: list[str] = []
    workbench_context = ROOT / "src" / "contexts" / "knowledge_workbench"

    for path in workbench_context.rglob("*.py"):
        if path.name == "__init__.py":
            continue

        text = path.read_text(encoding="utf-8")
        for marker in symbol_markers:
            if marker in text and path not in allowed_files:
                offenders.append(
                    f"{path.relative_to(ROOT)} contains extraction work-item marker {marker!r}"
                )

    assert not offenders, (
        "CreateExtractionWorkItems and CLAIM_EXTRACTION_WORK_KIND must not drift "
        "back into Source Management or unrelated Workbench contexts:\n"
        + "\n".join(offenders)
    )


def test_extraction_use_case_may_create_claim_extraction_work_items() -> None:
    path = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "extraction"
        / "application"
        / "use_cases"
        / "create_extraction_work_items.py"
    )

    text = path.read_text(encoding="utf-8")

    assert "src.contexts.execution_runtime.domain.entities.work_item" in text
    assert "src.contexts.execution_runtime.domain.value_objects.work_kind" in text
    assert 'WorkKind("knowledge_workbench.claim_extraction")' in text
    assert "CLAIM_EXTRACTION_WORK_KIND" in text
