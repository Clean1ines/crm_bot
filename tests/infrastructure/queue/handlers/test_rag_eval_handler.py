from __future__ import annotations

import pytest

from src.infrastructure.queue.handlers.rag_eval import (
    _coerce_int,
    _optional_int,
    _payload_text,
    _retry_after_seconds,
    handle_run_full_rag_eval,
)
from src.infrastructure.queue.job_exceptions import PermanentJobError
from src.infrastructure.queue.job_types import KNOWN_TASK_TYPES, TASK_RUN_FULL_RAG_EVAL


def test_run_full_rag_eval_task_type_is_registered() -> None:
    assert TASK_RUN_FULL_RAG_EVAL == "run_full_rag_eval"
    assert TASK_RUN_FULL_RAG_EVAL in KNOWN_TASK_TYPES


def test_coerce_int_clamps_invalid_and_out_of_range_values() -> None:
    assert _coerce_int("3", default=1, minimum=1, maximum=5) == 3
    assert _coerce_int("999", default=1, minimum=1, maximum=5) == 5
    assert _coerce_int("-2", default=1, minimum=1, maximum=5) == 1
    assert _coerce_int("bad", default=2, minimum=1, maximum=5) == 2


def test_optional_int_accepts_empty_as_none_and_clamps_values() -> None:
    assert _optional_int(None, minimum=1, maximum=50000) is None
    assert _optional_int("", minimum=1, maximum=50000) is None
    assert _optional_int("42", minimum=1, maximum=50000) == 42
    assert _optional_int("999999", minimum=1, maximum=50000) == 50000


def test_payload_text_rejects_missing_required_key() -> None:
    with pytest.raises(PermanentJobError, match="missing document_id"):
        _payload_text({"project_id": "project-1"}, "document_id")


def test_retry_after_seconds_parses_groq_message() -> None:
    exc = RuntimeError("Rate limit reached. Please try again in 3.07s.")
    assert _retry_after_seconds(exc) == pytest.approx(3.07)


@pytest.mark.asyncio
async def test_handle_run_full_rag_eval_rejects_non_object_payload() -> None:
    with pytest.raises(PermanentJobError, match="payload must be an object"):
        await handle_run_full_rag_eval(
            {"payload": "bad"},
            db_pool=object(),  # type: ignore[arg-type]
        )
