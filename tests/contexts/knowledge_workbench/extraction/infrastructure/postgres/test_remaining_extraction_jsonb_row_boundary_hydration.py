from __future__ import annotations

import json

import pytest

from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_builder_retry_action_read_repository import (
    _record_from_row,
    _retry_action_values,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_cluster_preview_repository import (
    _preview_payload,
)


def _retry_payload() -> dict[str, object]:
    return {
        "work_item_id": "work-item-1",
        "dispatch_attempt_id": "dispatch-attempt-1",
        "claim_builder_attempt_next_action_kind": _retry_action_values()[0],
        "claim_builder_requires_source_split": False,
    }


def test_retry_action_record_hydrates_payload_returned_as_json_string() -> None:
    record = _record_from_row({"payload": json.dumps(_retry_payload())})

    assert record.work_item_id == "work-item-1"
    assert record.dispatch_attempt_id == "dispatch-attempt-1"
    assert record.next_action_kind == _retry_action_values()[0]
    assert record.requires_source_split is False


def test_retry_action_record_rejects_payload_json_array() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "workflow_runtime_outbox_events.payload must be JSON object Mapping; "
            "got str that decoded to list"
        ),
    ):
        _record_from_row({"payload": '["not-object"]'})


def test_cluster_preview_hydrates_preview_payload_returned_as_json_string() -> None:
    payload = _preview_payload('{"claim_count":1,"group_count":1,"groups":[]}')

    assert payload["claim_count"] == 1
    assert payload["group_count"] == 1


def test_cluster_preview_rejects_preview_payload_json_array() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "draft_claim_cluster_previews.preview_payload must be JSON object "
            "Mapping; got str that decoded to list"
        ),
    ):
        _preview_payload('["not-object"]')
