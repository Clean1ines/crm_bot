from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.jsonb_payload_hydration import (
    hydrate_jsonb_text_array_payload,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    _text_tuple,
)


def test_text_array_payload_hydrates_json_string() -> None:
    values = hydrate_jsonb_text_array_payload(
        '[" question one ", "", "question two"]',
        field_name="knowledge_workbench_rag_eval.text_array",
    )

    assert values == ("question one", "question two")


def test_text_tuple_accepts_jsonb_array_returned_as_string() -> None:
    assert _text_tuple('["claim-1","claim-2"]') == ("claim-1", "claim-2")


def test_text_tuple_rejects_json_object_string() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "knowledge_workbench_rag_eval.text_array must be JSON text array; got dict"
        ),
    ):
        _text_tuple('{"source_claim_refs":["claim-1"]}')


def test_text_tuple_rejects_invalid_json_string() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "knowledge_workbench_rag_eval.text_array must be JSON text array; "
            "got invalid JSON str"
        ),
    ):
        _text_tuple("not json")
