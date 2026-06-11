from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.contexts.llm_runtime.application.results.llm_dispatch_output_artifact_payload import (
    LLM_DISPATCH_OUTPUT_ARTIFACT_KIND_VALUE,
    LlmDispatchOutputArtifactPayload,
)


def _dispatch_payload() -> dict[str, object]:
    return {
        "work_item_id": "work-1",
        "schedule_payload": {
            "provider_messages": (
                {
                    "role": "user",
                    "content": "Extract facts",
                },
            ),
            "prompt_a_provenance": {
                "workflow_run_id": "run-1",
                "stage_run_id": "draft_observation_extraction",
                "source_unit_ref": "source-unit-1",
                "work_item_id": "work-1",
                "prompt_id": "faq_claim_observations",
                "prompt_version": "v1",
            },
        },
        "llm_allocation": {
            "slot_index": 0,
        },
        "llm_execution_settings": {
            "reasoning_enabled": False,
        },
    }


def _output_payload() -> dict[str, object]:
    return {
        "raw_text": '{"ok": true}',
        "usage": {
            "input_tokens": 7,
            "output_tokens": 11,
            "total_tokens": 18,
        },
    }


def _payload(
    *,
    dispatch_payload: Mapping[str, object] | None = None,
    output_payload: Mapping[str, object] | None = None,
) -> LlmDispatchOutputArtifactPayload:
    return LlmDispatchOutputArtifactPayload(
        attempt_id="attempt-1",
        work_item_id="work-1",
        attempt_number=2,
        worker_ref="worker-1",
        dispatch_payload=_dispatch_payload()
        if dispatch_payload is None
        else dispatch_payload,
        output_payload=_output_payload() if output_payload is None else output_payload,
        finished_at="2026-06-11T12:01:00+00:00",
    )


def test_artifact_kind_value_is_stable() -> None:
    assert LLM_DISPATCH_OUTPUT_ARTIFACT_KIND_VALUE == "llm_dispatch_output"


def test_to_mapping_preserves_llm_dispatch_output_payload_shape() -> None:
    assert _payload().to_mapping() == {
        "attempt_id": "attempt-1",
        "work_item_id": "work-1",
        "attempt_number": 2,
        "worker_ref": "worker-1",
        "dispatch_payload": {
            "work_item_id": "work-1",
            "schedule_payload": {
                "provider_messages": [
                    {
                        "role": "user",
                        "content": "Extract facts",
                    },
                ],
                "prompt_a_provenance": {
                    "workflow_run_id": "run-1",
                    "stage_run_id": "draft_observation_extraction",
                    "source_unit_ref": "source-unit-1",
                    "work_item_id": "work-1",
                    "prompt_id": "faq_claim_observations",
                    "prompt_version": "v1",
                },
            },
            "llm_allocation": {
                "slot_index": 0,
            },
            "llm_execution_settings": {
                "reasoning_enabled": False,
            },
        },
        "output_payload": {
            "raw_text": '{"ok": true}',
            "usage": {
                "input_tokens": 7,
                "output_tokens": 11,
                "total_tokens": 18,
            },
        },
        "finished_at": "2026-06-11T12:01:00+00:00",
    }


def test_from_mapping_round_trip() -> None:
    mapping = _payload().to_mapping()

    result = LlmDispatchOutputArtifactPayload.from_mapping(mapping)

    assert result.to_mapping() == mapping


def test_raw_text_returns_output_payload_raw_text() -> None:
    assert _payload().raw_text() == '{"ok": true}'


def test_prompt_a_provenance_seed_returns_schedule_seed() -> None:
    provenance = _payload().prompt_a_provenance_seed()

    assert provenance == {
        "workflow_run_id": "run-1",
        "stage_run_id": "draft_observation_extraction",
        "source_unit_ref": "source-unit-1",
        "work_item_id": "work-1",
        "prompt_id": "faq_claim_observations",
        "prompt_version": "v1",
    }


def test_missing_raw_text_rejected() -> None:
    with pytest.raises(ValueError, match="raw_text"):
        _payload(output_payload={"usage": {}})


def test_missing_schedule_payload_rejected() -> None:
    dispatch_payload = dict(_dispatch_payload())
    del dispatch_payload["schedule_payload"]

    with pytest.raises(ValueError, match="schedule_payload"):
        _payload(dispatch_payload=dispatch_payload)


def test_missing_prompt_a_provenance_rejected() -> None:
    dispatch_payload = _dispatch_payload()
    schedule_payload = dict(dispatch_payload["schedule_payload"])
    del schedule_payload["prompt_a_provenance"]
    dispatch_payload["schedule_payload"] = schedule_payload

    with pytest.raises(ValueError, match="prompt_a_provenance"):
        _payload(dispatch_payload=dispatch_payload)


def test_missing_provider_messages_rejected() -> None:
    dispatch_payload = _dispatch_payload()
    schedule_payload = dict(dispatch_payload["schedule_payload"])
    del schedule_payload["provider_messages"]
    dispatch_payload["schedule_payload"] = schedule_payload

    with pytest.raises(ValueError, match="provider_messages"):
        _payload(dispatch_payload=dispatch_payload)


def test_non_json_values_rejected_on_mapping_conversion() -> None:
    payload = _payload(output_payload={"raw_text": "{}", "bad": object()})

    with pytest.raises(TypeError, match="non-json"):
        payload.to_mapping()
