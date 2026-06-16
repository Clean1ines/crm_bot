from __future__ import annotations

import pytest

from src.infrastructure.db.repositories.event_repository import _event_payload


def test_event_payload_hydrates_json_string() -> None:
    assert _event_payload('{"manager_user_id":"manager-1"}') == {
        "manager_user_id": "manager-1"
    }


def test_event_payload_rejects_json_array() -> None:
    with pytest.raises(
        TypeError,
        match="events.payload must be JSON object Mapping; got str that decoded to list",
    ):
        _event_payload('["not-object"]')
