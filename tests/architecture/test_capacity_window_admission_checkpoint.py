from pathlib import Path


def test_capacity_admission_audit_document_exists() -> None:
    path = Path("docs/architecture/capacity_window_admission_current_audit.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "capacity_retry_at" in text
    assert "WorkItem retry timer" in text
    assert "durable CapacityWindow" in text


def test_capacity_retry_at_is_not_work_item_timer_in_runtime_code() -> None:
    forbidden_paths = [
        Path("src/contexts/execution_runtime"),
    ]
    for root in forbidden_paths:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "capacity_retry_at" not in text
            assert "reset_at" not in text
            assert "minute_reset_at" not in text
            assert "daily_reset_at" not in text


def test_capacity_projection_filters_work_item_retry_timer_fields() -> None:
    projector = Path(
        "src/contexts/knowledge_workbench/observability/application/projectors/"
        "capacity_window_frontend_workflow_event_projector.py"
    )
    text = projector.read_text(encoding="utf-8")
    assert "next_attempt_at" in text
    assert "work_item_retry_timer" in text
    assert "retry_owner" in text
