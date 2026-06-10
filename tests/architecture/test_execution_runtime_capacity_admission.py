from pathlib import Path


def test_execution_runtime_capacity_admission_required_markers_exist() -> None:
    files = (
        Path(
            "src/contexts/execution_runtime/application/use_cases/"
            "lease_admitted_work_items.py",
        ),
        Path("src/contexts/capacity_runtime/domain/capacity_decision.py"),
        Path("src/contexts/capacity_runtime/domain/capacity_policy.py"),
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)

    required = (
        "LeaseAdmittedWorkItems",
        "CapacityAdmissionPolicy",
        "CapacityRequest",
        "requested_items",
        "max_admissible_items",
        "LeaseDueWorkItem",
        "WorkItemLeaseRepositoryPort",
    )
    for marker in required:
        assert marker in source


def test_lease_admitted_work_items_has_no_provider_workbench_or_infra_imports() -> None:
    source = Path(
        "src/contexts/execution_runtime/application/use_cases/"
        "lease_admitted_work_items.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "Groq",
        "qwen",
        "llm_runtime",
        "knowledge_workbench",
        "artifact_runtime",
        "capacity_runtime.infrastructure",
        "Postgres",
        "asyncpg",
        "source_unit",
        "Prompt",
        "commit(",
        "rollback(",
    )
    for marker in forbidden:
        assert marker not in source


def test_capacity_runtime_has_no_execution_provider_workbench_or_infra_imports() -> (
    None
):
    roots = (
        Path("src/contexts/capacity_runtime/domain/capacity_decision.py"),
        Path("src/contexts/capacity_runtime/domain/capacity_policy.py"),
    )
    forbidden = (
        "Groq",
        "qwen",
        "knowledge_workbench",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "Postgres",
        "asyncpg",
    )

    offenders: list[str] = []
    for path in roots:
        source = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in source:
                offenders.append(f"{path}: {marker}")

    assert offenders == []
