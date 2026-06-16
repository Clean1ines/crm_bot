from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_knowledge_extraction_saga_state_repository import (
    _required_mapping,
)


def test_checkpoint_payload_reader_accepts_mapping_from_asyncpg_jsonb() -> None:
    payload = {"completed": 1}

    assert (
        _required_mapping({"checkpoint_payload": payload}, "checkpoint_payload")
        == payload
    )


def test_checkpoint_payload_reader_accepts_json_string_from_serialized_write_path() -> (
    None
):
    payload = _required_mapping(
        {"checkpoint_payload": '{"completed": 1, "phase": "SOURCE_UNITS_CREATED"}'},
        "checkpoint_payload",
    )

    assert payload == {
        "completed": 1,
        "phase": "SOURCE_UNITS_CREATED",
    }


def test_checkpoint_payload_reader_rejects_json_arrays() -> None:
    with pytest.raises(TypeError, match="decode to mapping"):
        _required_mapping({"checkpoint_payload": '["bad"]'}, "checkpoint_payload")
