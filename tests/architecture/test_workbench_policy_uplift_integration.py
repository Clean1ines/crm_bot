from __future__ import annotations

from pathlib import Path


OLD_SURFACE_MATERIALIZATION = Path(
    "src/application/services/faq_workbench_surface_materialization_service.py"
)
OLD_SURFACE_CURATION = Path(
    "src/application/services/faq_workbench_surface_curation_service.py"
)
CURRENT_DELETE = Path("src/application/workbench_commands/delete_document.py")
CURRENT_CLEAR = Path("src/application/workbench_commands/clear_project.py")
CURRENT_PUBLISH_READY = Path("src/application/workbench_commands/publish_ready.py")


def test_old_surface_materialization_and_curation_services_are_deleted() -> None:
    assert not OLD_SURFACE_MATERIALIZATION.exists()
    assert not OLD_SURFACE_CURATION.exists()


def test_workbench_policy_integration_uses_current_command_boundaries() -> None:
    for path in (CURRENT_DELETE, CURRENT_CLEAR, CURRENT_PUBLISH_READY):
        assert path.exists(), f"missing current Workbench command boundary: {path}"

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (CURRENT_DELETE, CURRENT_CLEAR, CURRENT_PUBLISH_READY)
    )

    assert "faq_workbench_surface_materialization_service" not in combined
    assert "faq_workbench_surface_curation_service" not in combined
    assert "KnowledgeService(" not in combined


def test_old_donor_services_are_not_workbench_command_dependencies() -> None:
    forbidden = (
        "faq_workbench_surface_materialization_service",
        "faq_workbench_surface_curation_service",
        "KnowledgeService(",
    )

    offenders: list[str] = []
    for root in (
        Path("src/application/workbench_commands"),
        Path("src/interfaces/composition"),
    ):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8", errors="ignore")
            for marker in forbidden:
                if marker in source:
                    offenders.append(f"{path}: {marker}")

    assert offenders == []
