from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import cast

from groq import AsyncGroq

from src.domain.project_plane.llm_routing import JsonValue
from src.infrastructure.llm.groq_llm_json_invocation import (
    GroqChatLike,
    GroqLlmJsonInvocationAdapter,
    GroqLlmJsonInvocationConfig,
)

WORKBENCH_QWEN_MODEL = "qwen/qwen3-32b"


@dataclass(slots=True)
class _DirectGroqJsonClient:
    """Direct Groq client wrapper matching the JSON adapter client protocol.

    AsyncGroq itself does not expose route_observability_snapshot and its chat
    attribute is read-only from the protocol perspective, so the Workbench-only
    adapter wraps it instead of passing AsyncGroq directly.
    """

    chat: GroqChatLike

    @classmethod
    def create(cls) -> _DirectGroqJsonClient:
        return cls(
            chat=cast(GroqChatLike, AsyncGroq(api_key=_first_groq_api_key()).chat)
        )

    def route_observability_snapshot(self) -> dict[str, object]:
        return {
            "mode": "workbench_qwen_direct",
            "model": WORKBENCH_QWEN_MODEL,
            "model_routing": "disabled",
        }


class WorkbenchQwenLlmJsonInvocationAdapter(GroqLlmJsonInvocationAdapter):
    """Workbench-only Groq JSON invocation.

    Workbench Prompt A and Prompt C must not use the global Groq model router,
    because that router intentionally starts with llama-3.1-8b-instant.

    This adapter keeps the shared LlmJsonInvocationPort result contract but uses
    a direct AsyncGroq client and a fixed qwen/qwen3-32b model.
    """

    @classmethod
    def create_default(
        cls,
        *,
        config: GroqLlmJsonInvocationConfig | None = None,
    ) -> WorkbenchQwenLlmJsonInvocationAdapter:
        resolved = config or GroqLlmJsonInvocationConfig(
            default_model=WORKBENCH_QWEN_MODEL,
            max_completion_tokens=4096,
        )

        if resolved.default_model != WORKBENCH_QWEN_MODEL:
            resolved = GroqLlmJsonInvocationConfig(
                default_model=WORKBENCH_QWEN_MODEL,
                max_completion_tokens=resolved.max_completion_tokens,
                temperature=resolved.temperature,
            )

        return cls(
            client=_DirectGroqJsonClient.create(),
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


def _first_groq_api_key() -> str:
    direct = os.getenv("GROQ_API_KEY")
    if direct:
        return direct

    for name in sorted(os.environ):
        if name.startswith("GROQ_API_KEY") and os.environ[name]:
            return os.environ[name]

    raise RuntimeError(
        "Workbench Qwen invocation requires GROQ_API_KEY or GROQ_API_KEY_*"
    )


__all__ = [
    "WORKBENCH_QWEN_MODEL",
    "WorkbenchQwenLlmJsonInvocationAdapter",
    "sanitize_workbench_qwen_json_text",
]
