from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_after_upload_composition_does_not_reference_removed_work_item_retry_timer() -> (
    None
):
    source = (
        ROOT
        / "src/interfaces/composition/knowledge_extraction_workflow_after_upload.py"
    ).read_text(encoding="utf-8")

    assert "next" + "_attempt" + "_at" not in source
