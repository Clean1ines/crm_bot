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
