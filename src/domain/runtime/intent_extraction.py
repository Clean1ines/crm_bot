from dataclasses import dataclass, field
from typing import Mapping

from src.domain.runtime.state_contracts import (
    RuntimeHistoryMessage,
    RuntimeMemory,
    RuntimeStateInput,
    RuntimeStatePatch,
)


@dataclass(slots=True)
class IntentExtractionPayload:
    intent: str
    cta: str
    features: Mapping[str, float]
    topic: str
    cta_hint: str | None = None
    emotion: str = "neutral"
    is_repeat_like: bool = False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "IntentExtractionPayload":
        raw_features = payload.get("features")
        features: dict[str, float] = {}

        if isinstance(raw_features, Mapping):
            for key, value in raw_features.items():
                try:
                    features[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue

        cta_hint = payload.get("cta_hint")
        return cls(
            intent=str(payload.get("intent") or "unknown"),
            cta=str(payload.get("cta") or "none"),
            features=features,
            topic=str(payload.get("topic") or "other"),
            cta_hint=str(cta_hint) if cta_hint is not None else None,
            emotion=str(payload.get("emotion") or "neutral"),
            is_repeat_like=bool(payload.get("is_repeat_like", False)),
        )


@dataclass(slots=True)
class IntentExtractionContext:
    user_input: str = ""
    conversation_summary: str | None = None
    history: list[RuntimeHistoryMessage] = field(default_factory=list)
    user_memory: RuntimeMemory | None = None

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "IntentExtractionContext":
        return cls(
            user_input=str(state.get("user_input") or ""),
            conversation_summary=state.get("conversation_summary"),
            history=list(state.get("history") or []),
            user_memory=state.get("user_memory"),
        )


@dataclass(slots=True)
class IntentExtractionResult:
    intent: str
    cta: str
    features: Mapping[str, float]
    topic: str
    cta_hint: str | None
    emotion: str
    is_repeat_like: bool

    @classmethod
    def from_llm_payload(
        cls, payload: Mapping[str, object]
    ) -> "IntentExtractionResult":
        validated = IntentExtractionPayload.from_mapping(payload)
        return cls(
            intent=validated.intent,
            cta=validated.cta,
            features=validated.features,
            topic=validated.topic,
            cta_hint=validated.cta_hint,
            emotion=validated.emotion,
            is_repeat_like=validated.is_repeat_like,
        )

    def to_state_patch(self) -> RuntimeStatePatch:
        return {
            "intent": self.intent,
            "cta": self.cta,
            "features": self.features,
            "topic": self.topic,
            "cta_hint": self.cta_hint,
            "emotion": self.emotion,
            "is_repeat_like": self.is_repeat_like,
        }
