from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import cast

from groq import AsyncGroq

from src.domain.project_plane.llm_routing import JsonValue
from src.infrastructure.llm.groq_keyring import configured_groq_api_keys
from src.infrastructure.llm.groq_llm_json_invocation import (
    GroqChatCompletionLike,
    GroqChatCompletionsLike,
    GroqChatLike,
    GroqLlmJsonInvocationAdapter,
    GroqLlmJsonInvocationConfig,
)
from src.infrastructure.llm.groq_router import (
    classify_groq_exception,
    retry_after_seconds_from_exception,
)

WORKBENCH_QWEN_MODEL = "qwen/qwen3-32b"

_WORKBENCH_QWEN_WORKER_ID: ContextVar[str | None] = ContextVar(
    "workbench_qwen_worker_id",
    default=None,
)


@dataclass(frozen=True, slots=True)
class _WorkbenchQwenKeySelection:
    key: str
    index: int
    key_count: int
    worker_id: str
    selection_mode: str


@dataclass(frozen=True, slots=True)
class _WorkbenchQwenRouteEvent:
    sequence: int
    status: str
    requested_model: str
    routed_model: str
    key_index: int
    key_count: int
    worker_id: str
    selection_mode: str
    fallback_reason: str = ""
    limit_kind: str = ""
    retry_after_seconds: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error_type: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "status": self.status,
            "requested_model": self.requested_model,
            "routed_model": self.routed_model,
            "key_index": self.key_index,
            "key_slot": self.key_index + 1,
            "key_count": self.key_count,
            "key_slot_label": f"{self.key_index + 1}/{self.key_count}",
            "worker_id": self.worker_id,
            "selection_mode": self.selection_mode,
            "fallback_reason": self.fallback_reason,
            "limit_kind": self.limit_kind,
            "retry_after_seconds": self.retry_after_seconds,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "error_type": self.error_type,
            "error": self.error,
        }


@contextmanager
def workbench_qwen_worker_context(worker_id: str | None) -> Iterator[None]:
    normalized = worker_id.strip() if isinstance(worker_id, str) else ""
    token = _WORKBENCH_QWEN_WORKER_ID.set(normalized or None)
    try:
        yield
    finally:
        _WORKBENCH_QWEN_WORKER_ID.reset(token)


def workbench_qwen_worker_key_slot(
    worker_id: str | None,
    *,
    key_count: int,
) -> int | None:
    if key_count < 1:
        raise ValueError("key_count must be positive")

    normalized = worker_id.strip() if isinstance(worker_id, str) else ""
    if not normalized:
        return None

    match = re.search(r"-(\d+)$", normalized)
    if match is None:
        return None

    worker_slot = int(match.group(1))
    if worker_slot < 1:
        return None

    return ((worker_slot - 1) % key_count) + 1


@dataclass(slots=True)
class _WorkbenchQwenCompletionsProxy:
    """Qwen-only Groq proxy with deterministic section-worker key affinity.

    With three configured keys:
      workbench-parallel-section-...-1 -> key slot 1
      workbench-parallel-section-...-2 -> key slot 2
      workbench-parallel-section-...-3 -> key slot 3

    This never uses model routing and never changes the model away from Qwen.
    """

    _events: list[_WorkbenchQwenRouteEvent] = field(default_factory=list)
    _sequence: int = 0
    _fallback_index: int = 0

    async def create(self, **kwargs: object) -> GroqChatCompletionLike:
        selection = self._select_key()
        model = _model_text(kwargs)
        self._sequence += 1

        try:
            client = AsyncGroq(api_key=selection.key)
            completions = cast(GroqChatCompletionsLike, client.chat.completions)
            response = await completions.create(**kwargs)
        except Exception as exc:
            limit_kind = classify_groq_exception(exc)
            retry_after = retry_after_seconds_from_exception(exc)
            self._append_event(
                _WorkbenchQwenRouteEvent(
                    sequence=self._sequence,
                    status="failed",
                    requested_model=model,
                    routed_model=model,
                    key_index=selection.index,
                    key_count=selection.key_count,
                    worker_id=selection.worker_id,
                    selection_mode=selection.selection_mode,
                    limit_kind=limit_kind.value,
                    retry_after_seconds=retry_after,
                    error_type=type(exc).__name__,
                    error=str(exc)[:300],
                )
            )
            raise

        self._append_event(
            _WorkbenchQwenRouteEvent(
                sequence=self._sequence,
                status="success",
                requested_model=model,
                routed_model=model,
                key_index=selection.index,
                key_count=selection.key_count,
                worker_id=selection.worker_id,
                selection_mode=selection.selection_mode,
                prompt_tokens=_usage_int(response, "prompt_tokens"),
                completion_tokens=_usage_int(response, "completion_tokens"),
                total_tokens=_usage_int(response, "total_tokens"),
            )
        )
        return response

    def _select_key(self) -> _WorkbenchQwenKeySelection:
        keys = configured_groq_api_keys()
        if not keys:
            raise RuntimeError("No Groq API keys are configured")

        worker_id = _WORKBENCH_QWEN_WORKER_ID.get() or ""
        key_slot = workbench_qwen_worker_key_slot(worker_id, key_count=len(keys))

        if key_slot is not None:
            return _WorkbenchQwenKeySelection(
                key=keys[key_slot - 1],
                index=key_slot - 1,
                key_count=len(keys),
                worker_id=worker_id,
                selection_mode="worker_affinity",
            )

        fallback_slot = (self._fallback_index % len(keys)) + 1
        self._fallback_index = (self._fallback_index + 1) % len(keys)
        return _WorkbenchQwenKeySelection(
            key=keys[fallback_slot - 1],
            index=fallback_slot - 1,
            key_count=len(keys),
            worker_id="",
            selection_mode="fallback_round_robin",
        )

    def _append_event(self, event: _WorkbenchQwenRouteEvent) -> None:
        self._events.append(event)
        self._events = self._events[-50:]

    def snapshot(self) -> dict[str, object]:
        events = [event.to_dict() for event in self._events]
        worker_key_slots: dict[str, str] = {}
        key_slot_counts: dict[str, int] = {}
        success_count = 0
        failure_count = 0

        for event in self._events:
            key_slot_label = f"{event.key_index + 1}/{event.key_count}"
            if event.worker_id:
                worker_key_slots[event.worker_id] = key_slot_label

            if event.status == "success":
                success_count += 1
                key_slot_counts[key_slot_label] = (
                    key_slot_counts.get(key_slot_label, 0) + 1
                )
            elif event.status == "failed":
                failure_count += 1

        return {
            "mode": "workbench_qwen_worker_affinity",
            "model": WORKBENCH_QWEN_MODEL,
            "model_routing": "disabled",
            "key_selection": "worker_affinity",
            "groq_route_event_count": len(self._events),
            "groq_route_success_count": success_count,
            "groq_route_failure_count": failure_count,
            "groq_key_slot_counts": key_slot_counts,
            "groq_worker_key_slots": worker_key_slots,
            "groq_last_route_event": events[-1] if events else {},
            "groq_route_events": events[-20:],
        }


@dataclass(slots=True)
class _WorkbenchQwenChatProxy:
    completions: GroqChatCompletionsLike


@dataclass(slots=True)
class _WorkbenchQwenJsonClient:
    chat: GroqChatLike
    completions_proxy: _WorkbenchQwenCompletionsProxy

    @classmethod
    def create(cls) -> _WorkbenchQwenJsonClient:
        completions = _WorkbenchQwenCompletionsProxy()
        return cls(
            chat=_WorkbenchQwenChatProxy(completions=completions),
            completions_proxy=completions,
        )

    def route_observability_snapshot(self) -> dict[str, object]:
        return self.completions_proxy.snapshot()


class WorkbenchQwenLlmJsonInvocationAdapter(GroqLlmJsonInvocationAdapter):
    """Workbench-only Groq JSON invocation.

    Prompt A and Prompt C use exactly qwen/qwen3-32b.
    Model routing is disabled.
    Prompt A section workers bind deterministically to Groq key slots.
    """

    @classmethod
    def create_default(
        cls,
        *,
        config: GroqLlmJsonInvocationConfig | None = None,
    ) -> WorkbenchQwenLlmJsonInvocationAdapter:
        resolved = config or GroqLlmJsonInvocationConfig(
            default_model=WORKBENCH_QWEN_MODEL,
            max_completion_tokens=None,
        )

        if (
            resolved.default_model != WORKBENCH_QWEN_MODEL
            or resolved.max_completion_tokens is not None
        ):
            resolved = GroqLlmJsonInvocationConfig(
                default_model=WORKBENCH_QWEN_MODEL,
                max_completion_tokens=None,
                temperature=resolved.temperature,
            )

        return cls(
            client=_WorkbenchQwenJsonClient.create(),
            config=resolved,
        )

    def _loads_json_value(self, raw_text: str) -> JsonValue:
        sanitized = sanitize_workbench_qwen_json_text(raw_text)
        return cast(JsonValue, json.loads(sanitized))


def sanitize_workbench_qwen_json_text(raw_text: str) -> str:
    """Strip Qwen reasoning wrappers and return the first JSON object."""

    text = raw_text.strip()
    text = re.sub(r"(?is)^\s*<think>.*?</think>\s*", "", text, count=1).strip()

    if text.startswith("```"):
        text = re.sub(r"(?is)^```(?:json)?\s*", "", text, count=1)
        text = re.sub(r"(?is)\s*```\s*$", "", text, count=1).strip()

    if text.startswith("{") and text.endswith("}"):
        return text

    return _extract_first_json_object(text)


def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("LLM response does not contain JSON object")

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
                continue
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError("LLM response contains unterminated JSON object")


def _model_text(kwargs: dict[str, object]) -> str:
    model = kwargs.get("model")
    return model if isinstance(model, str) and model.strip() else WORKBENCH_QWEN_MODEL


def _usage_int(response: GroqChatCompletionLike, field_name: str) -> int:
    usage = response.usage
    if usage is None:
        return 0

    value = getattr(usage, field_name, None)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


__all__ = [
    "WORKBENCH_QWEN_MODEL",
    "WorkbenchQwenLlmJsonInvocationAdapter",
    "sanitize_workbench_qwen_json_text",
    "workbench_qwen_worker_context",
    "workbench_qwen_worker_key_slot",
]
