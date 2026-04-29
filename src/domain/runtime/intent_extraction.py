from dataclasses import dataclass, field, replace
from typing import Mapping

from src.domain.runtime.dialog_state import DialogState
from src.domain.runtime.state_contracts import (
    RuntimeHistoryMessage,
    RuntimeMemory,
    RuntimeStateInput,
    RuntimeStatePatch,
)

AFFIRMATIVE_REPLIES = frozenset({"да", "ага", "угу", "ок", "окей", "yes", "yep"})
NEGATIVE_REPLIES = frozenset({"нет", "неа", "не", "no", "nope"})
PRICE_OBJECTION_MARKERS = ("дорого", "слишком дорого", "expensive", "too expensive")
ISSUE_MARKERS = ("не работает", "ошибка", "сломалось", "error", "issue", "problem")
ACTION_CTAS = frozenset({"call_manager", "book_consultation"})


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
    topic: str | None = None
    cta: str | None = None
    dialog_state: DialogState | None = None

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "IntentExtractionContext":
        return cls(
            user_input=str(state.get("user_input") or ""),
            conversation_summary=state.get("conversation_summary"),
            history=list(state.get("history") or []),
            user_memory=state.get("user_memory"),
            topic=_optional_text(state.get("topic")),
            cta=_optional_text(state.get("cta")),
            dialog_state=_dialog_state_or_none(state.get("dialog_state")),
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

    def normalized_for_context(
        self,
        context: IntentExtractionContext,
    ) -> "IntentExtractionResult":
        reply_kind = _short_reply_kind(context.user_input)
        if reply_kind is None:
            return self

        previous_topic = _previous_topic(context)
        previous_cta = _previous_cta(context)

        if reply_kind == "affirmative":
            return _normalize_affirmative_reply(
                self,
                previous_topic=previous_topic,
                previous_cta=previous_cta,
            )
        if reply_kind == "negative":
            return _normalize_negative_reply(
                self,
                previous_topic=previous_topic,
                previous_cta=previous_cta,
            )
        if reply_kind == "price_objection":
            return replace(
                self,
                intent="pricing",
                topic="pricing",
                cta="none",
                emotion="negative",
                is_repeat_like=True,
            )
        if reply_kind == "issue_report":
            return replace(
                self,
                intent="support",
                topic="integration" if previous_topic == "integration" else "support",
                cta="none",
                emotion="negative",
                is_repeat_like=True,
            )
        return self

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


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dialog_state_or_none(value: object) -> DialogState | None:
    if not isinstance(value, Mapping):
        return None
    return DialogState(
        last_intent=_optional_text(value.get("last_intent")),
        last_cta=_optional_text(value.get("last_cta")),
        last_topic=_optional_text(value.get("last_topic")),
        repeat_count=int(value.get("repeat_count") or 0),
        lead_status=str(value.get("lead_status") or "cold"),
        lifecycle=str(value.get("lifecycle") or "cold"),
    )


def _short_reply_kind(text: str) -> str | None:
    normalized = _normalized_reply_text(text)
    if normalized is None:
        return None
    if normalized in AFFIRMATIVE_REPLIES:
        return "affirmative"
    if normalized in NEGATIVE_REPLIES:
        return "negative"
    if any(marker in normalized for marker in PRICE_OBJECTION_MARKERS):
        return "price_objection"
    if any(marker in normalized for marker in ISSUE_MARKERS):
        return "issue_report"
    return None


def _normalized_reply_text(text: str) -> str | None:
    normalized = " ".join(str(text).strip().lower().split())
    if not normalized:
        return None

    word_count = len(normalized.split())
    if len(normalized) <= 32 or word_count <= 4:
        return normalized

    if any(marker in normalized for marker in PRICE_OBJECTION_MARKERS + ISSUE_MARKERS):
        return normalized

    return None


def _previous_topic(context: IntentExtractionContext) -> str | None:
    if context.topic:
        return context.topic
    if context.dialog_state:
        return context.dialog_state.get("last_topic")
    return None


def _previous_cta(context: IntentExtractionContext) -> str | None:
    if context.cta:
        return context.cta
    if context.dialog_state:
        dialog_cta = context.dialog_state.get("last_cta")
        if dialog_cta:
            return dialog_cta
    return _cta_from_last_assistant_message(context.history)


def _cta_from_last_assistant_message(
    history: list[RuntimeHistoryMessage],
) -> str | None:
    for message in reversed(history):
        if message.get("role") != "assistant":
            continue
        content = str(message.get("content") or "").lower()
        if any(marker in content for marker in ("менеджер", "operator", "manager")):
            return "call_manager"
        if any(marker in content for marker in ("созвон", "консультац", "consult")):
            return "book_consultation"
        return None
    return None


def _normalize_affirmative_reply(
    result: IntentExtractionResult,
    *,
    previous_topic: str | None,
    previous_cta: str | None,
) -> IntentExtractionResult:
    if previous_cta in ACTION_CTAS:
        return replace(
            result,
            intent="sales",
            topic=previous_topic or result.topic,
            cta=previous_cta,
        )
    if result.intent in {"other", "unknown"} and previous_topic:
        return replace(result, intent="sales", topic=previous_topic)
    return result


def _normalize_negative_reply(
    result: IntentExtractionResult,
    *,
    previous_topic: str | None,
    previous_cta: str | None,
) -> IntentExtractionResult:
    if previous_cta in ACTION_CTAS:
        return replace(
            result,
            topic=previous_topic or result.topic,
            cta="none",
        )
    return result
