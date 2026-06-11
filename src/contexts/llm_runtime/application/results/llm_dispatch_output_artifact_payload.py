from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias, cast


JsonScalar: TypeAlias = None | bool | int | float | str
JsonInputValue: TypeAlias = (
    JsonScalar
    | list["JsonInputValue"]
    | dict[
        str,
        "JsonInputValue",
    ]
)

LLM_DISPATCH_OUTPUT_ARTIFACT_KIND_VALUE = "llm_dispatch_output"


@dataclass(frozen=True, slots=True)
class LlmDispatchOutputArtifactPayload:
    attempt_id: str
    work_item_id: str
    attempt_number: int
    worker_ref: str
    dispatch_payload: Mapping[str, object]
    output_payload: Mapping[str, object]
    finished_at: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")
        _require_non_empty_text(self.work_item_id, field_name="work_item_id")
        _require_non_empty_text(self.worker_ref, field_name="worker_ref")
        _require_non_empty_text(self.finished_at, field_name="finished_at")

        if not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be int")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be > 0")

        if not isinstance(self.dispatch_payload, Mapping):
            raise TypeError("dispatch_payload must be Mapping")
        if not isinstance(self.output_payload, Mapping):
            raise TypeError("output_payload must be Mapping")

        _require_non_empty_text(self.raw_text(), field_name="raw_text")
        schedule_payload = self.schedule_payload()
        self.prompt_a_provenance_seed()

        if "provider_messages" not in schedule_payload:
            raise ValueError("schedule_payload.provider_messages is required")
        provider_messages = schedule_payload["provider_messages"]
        if not isinstance(provider_messages, list | tuple):
            raise TypeError("schedule_payload.provider_messages must be list or tuple")

    def to_mapping(self) -> dict[str, JsonInputValue]:
        return {
            "attempt_id": self.attempt_id,
            "work_item_id": self.work_item_id,
            "attempt_number": self.attempt_number,
            "worker_ref": self.worker_ref,
            "dispatch_payload": _json_mapping(self.dispatch_payload),
            "output_payload": _json_mapping(self.output_payload),
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
    ) -> LlmDispatchOutputArtifactPayload:
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be Mapping")

        return cls(
            attempt_id=_require_text_field(payload, "attempt_id"),
            work_item_id=_require_text_field(payload, "work_item_id"),
            attempt_number=_require_int_field(payload, "attempt_number"),
            worker_ref=_require_text_field(payload, "worker_ref"),
            dispatch_payload=_require_mapping_field(payload, "dispatch_payload"),
            output_payload=_require_mapping_field(payload, "output_payload"),
            finished_at=_require_text_field(payload, "finished_at"),
        )

    def raw_text(self) -> str:
        if "raw_text" not in self.output_payload:
            raise ValueError("output_payload.raw_text is required")
        raw_text = self.output_payload["raw_text"]
        if not isinstance(raw_text, str):
            raise TypeError("output_payload.raw_text must be str")
        return raw_text

    def schedule_payload(self) -> Mapping[str, object]:
        if "schedule_payload" not in self.dispatch_payload:
            raise ValueError("dispatch_payload.schedule_payload is required")
        schedule_payload = self.dispatch_payload["schedule_payload"]
        if not isinstance(schedule_payload, Mapping):
            raise TypeError("dispatch_payload.schedule_payload must be Mapping")
        return cast(Mapping[str, object], schedule_payload)

    def prompt_a_provenance_seed(self) -> Mapping[str, object]:
        schedule_payload = self.schedule_payload()
        if "prompt_a_provenance" not in schedule_payload:
            raise ValueError("schedule_payload.prompt_a_provenance is required")
        provenance = schedule_payload["prompt_a_provenance"]
        if not isinstance(provenance, Mapping):
            raise TypeError("schedule_payload.prompt_a_provenance must be Mapping")
        return cast(Mapping[str, object], provenance)


def _require_text_field(payload: Mapping[str, object], field_name: str) -> str:
    if field_name not in payload:
        raise ValueError(f"{field_name} is required")
    value = payload[field_name]
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    _require_non_empty_text(value, field_name=field_name)
    return value


def _require_int_field(payload: Mapping[str, object], field_name: str) -> int:
    if field_name not in payload:
        raise ValueError(f"{field_name} is required")
    value = payload[field_name]
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _require_mapping_field(
    payload: Mapping[str, object],
    field_name: str,
) -> Mapping[str, object]:
    if field_name not in payload:
        raise ValueError(f"{field_name} is required")
    value = payload[field_name]
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be Mapping")
    return cast(Mapping[str, object], value)


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _json_mapping(value: Mapping[str, object]) -> dict[str, JsonInputValue]:
    normalized: dict[str, JsonInputValue] = {}
    for key, item in value.items():
        normalized[key] = _json_value(item)
    return normalized


def _json_value(value: object) -> JsonInputValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return _json_mapping(cast(Mapping[str, object], value))
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    raise TypeError("payload contains non-json value")
