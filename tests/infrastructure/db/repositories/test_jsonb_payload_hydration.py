from __future__ import annotations

import pytest

from src.infrastructure.db.repositories.jsonb_payload_hydration import (
    hydrate_jsonb_object_payload,
)


def test_generic_db_jsonb_object_hydrates_mapping() -> None:
    payload = hydrate_jsonb_object_payload(
        {"event": "created"},
        field_name="events.payload",
    )

    assert dict(payload) == {"event": "created"}


def test_generic_db_jsonb_object_hydrates_json_string() -> None:
    payload = hydrate_jsonb_object_payload(
        '{"event":"created"}',
        field_name="events.payload",
    )

    assert dict(payload) == {"event": "created"}


def test_generic_db_jsonb_object_rejects_array_string() -> None:
    with pytest.raises(
        TypeError,
        match="events.payload must be JSON object Mapping; got str that decoded to list",
    ):
        hydrate_jsonb_object_payload('["created"]', field_name="events.payload")


def test_generic_db_jsonb_object_rejects_none_for_required_payload() -> None:
    with pytest.raises(
        TypeError,
        match="events.payload must be JSON object Mapping; got NoneType",
    ):
        hydrate_jsonb_object_payload(None, field_name="events.payload")
