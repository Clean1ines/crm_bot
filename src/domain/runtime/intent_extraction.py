from dataclasses import dataclass, field, replace
from typing import Mapping

from src.domain.runtime.cta import (
    ACTION_CTAS,
    CONTINUE_EXPLANATION_CTA,
    normalize_cta,
    normalize_short_reply_language,
    normalize_short_reply_kind,
)
from src.domain.runtime.dialog_state import DialogState
from src.domain.runtime.language_policy import (
    LanguageHint,
    detect_language_hint,
    normalize_project_language,
)
from src.domain.runtime.state_contracts import (
    RuntimeHistoryMessage,
    RuntimeMemory,
    RuntimeStateInput,
    RuntimeStatePatch,
)

PRICE_OBJECTION_MARKERS = ("дорого", "слишком дорого", "expensive", "too expensive")
ISSUE_MARKERS = ("не работает", "ошибка", "сломалось", "error", "issue", "problem")
KNOWN_DOMAINS = frozenset(
    {"business", "out_of_domain", "greeting", "ambiguous", "technical_failure"}
)
KNOWN_TURN_RELATIONS = frozenset(
    {"new_topic", "continuation", "short_reply", "reopening", "unknown"}
)
KNOWN_INTENTS = frozenset(
    {"pricing", "support", "sales", "feedback", "handoff_request", "other", "unknown"}
)
KNOWN_TOPICS = frozenset(
    {
        "pricing",
        "product",
        "integration",
        "support",
        "feedback",
        "other",
        "handoff",
        "angry",
    }
)
KNOWN_CTAS = frozenset(
    {"call_manager", "book_consultation", CONTINUE_EXPLANATION_CTA, "none"}
)
KNOWN_EMOTIONS = frozenset({"neutral", "positive", "negative", "angry"})


@dataclass(slots=True)
class IntentExtractionPayload:
    intent: str
    cta: str
    features: Mapping[str, float]
    topic: str
    cta_hint: str | None = None
    emotion: str = "neutral"
    is_repeat_like: bool = False
    domain: str = "business"
    turn_relation: str = "unknown"
    should_search_kb: bool = True
    should_generate_answer: bool = True
    should_offer_manager: bool = False
    knowledge_query: str | None = None

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
        domain = _normalized_enum_value(
            payload.get("domain"), KNOWN_DOMAINS, "business"
        )
        should_search_kb = _coerce_bool(
            payload.get("should_search_kb"),
            default=domain == "business",
        )
        should_generate_answer = _coerce_bool(
            payload.get("should_generate_answer"),
            default=domain == "business",
        )

        if domain in {"out_of_domain", "greeting", "ambiguous"}:
            should_search_kb = False
            should_generate_answer = False

        return cls(
            intent=_normalized_enum_value(
                payload.get("intent"), KNOWN_INTENTS, "unknown"
            ),
            cta=_normalized_enum_value(payload.get("cta"), KNOWN_CTAS, "none"),
            features=features,
            topic=_normalized_enum_value(payload.get("topic"), KNOWN_TOPICS, "other"),
            cta_hint=str(cta_hint) if cta_hint is not None else None,
            emotion=_normalized_enum_value(
                payload.get("emotion"), KNOWN_EMOTIONS, "neutral"
            ),
            is_repeat_like=_coerce_bool(payload.get("is_repeat_like"), default=False),
            domain=domain,
            turn_relation=_normalized_enum_value(
                payload.get("turn_relation"),
                KNOWN_TURN_RELATIONS,
                "unknown",
            ),
            should_search_kb=should_search_kb,
            should_generate_answer=should_generate_answer,
            should_offer_manager=_coerce_bool(
                payload.get("should_offer_manager"),
                default=False,
            ),
            knowledge_query=None,
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
    target_language: LanguageHint = "unknown"

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "IntentExtractionContext":
        return cls(
            user_input=str(state.get("user_input") or ""),
            conversation_summary=state.get("conversation_summary"),
            history=list(state.get("history") or []),
            user_memory=state.get("user_memory"),
            topic=_optional_text(state.get("topic")),
            cta=normalize_cta(state.get("cta")),
            dialog_state=_dialog_state_or_none(state.get("dialog_state")),
            target_language=_target_language_from_state(state),
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
    domain: str
    turn_relation: str
    should_search_kb: bool
    should_generate_answer: bool
    should_offer_manager: bool
    knowledge_query: str | None = None
    resolved_cta: str | None = None
    resolved_cta_reply: str | None = None

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
            domain=validated.domain,
            turn_relation=validated.turn_relation,
            should_search_kb=validated.should_search_kb,
            should_generate_answer=validated.should_generate_answer,
            should_offer_manager=validated.should_offer_manager,
            knowledge_query=validated.knowledge_query,
            resolved_cta=None,
            resolved_cta_reply=None,
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
                language=_continuation_language(context),
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
                domain="business",
                intent="pricing",
                topic="pricing",
                cta="none",
                emotion="negative",
                is_repeat_like=True,
                should_search_kb=True,
                should_generate_answer=True,
            )
        if reply_kind == "issue_report":
            return replace(
                self,
                domain="business",
                intent="support",
                topic="integration" if previous_topic == "integration" else "support",
                cta="none",
                emotion="negative",
                is_repeat_like=True,
                should_search_kb=True,
                should_generate_answer=True,
            )
        return self

    def to_state_patch(self) -> RuntimeStatePatch:
        patch: RuntimeStatePatch = {
            "intent": self.intent,
            "cta": self.cta,
            "features": self.features,
            "topic": self.topic,
            "cta_hint": self.cta_hint,
            "emotion": self.emotion,
            "is_repeat_like": self.is_repeat_like,
            "domain": self.domain,
            "turn_relation": self.turn_relation,
            "should_search_kb": self.should_search_kb,
            "should_generate_answer": self.should_generate_answer,
            "should_offer_manager": self.should_offer_manager,
        }
        patch["knowledge_query"] = self.knowledge_query
        patch["resolved_cta"] = self.resolved_cta
        patch["resolved_cta_reply"] = self.resolved_cta_reply
        return patch


def _coerce_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "да"}:
            return True
        if normalized in {"false", "0", "no", "n", "нет"}:
            return False
    return bool(value)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized_enum_value(
    value: object,
    allowed: frozenset[str],
    default: str,
) -> str:
    text = _optional_text(value)
    if text is None:
        return default
    normalized = text.strip().lower()
    return normalized if normalized in allowed else default


def _dialog_state_or_none(value: object) -> DialogState | None:
    if not isinstance(value, Mapping):
        return None
    return DialogState(
        last_intent=_optional_text(value.get("last_intent")),
        last_cta=normalize_cta(value.get("last_cta")),
        last_topic=_optional_text(value.get("last_topic")),
        repeat_count=int(value.get("repeat_count") or 0),
        lead_status=str(value.get("lead_status") or "cold"),
        lifecycle=str(value.get("lifecycle") or "cold"),
        handoff_confirmation_pending=bool(
            value.get("handoff_confirmation_pending", False)
        ),
    )


def _target_language_from_state(state: RuntimeStateInput) -> LanguageHint:
    configuration = state.get("project_configuration")
    if not isinstance(configuration, Mapping):
        return "unknown"
    settings = configuration.get("settings")
    if not isinstance(settings, Mapping):
        return "unknown"
    return normalize_project_language(str(settings.get("target_language") or ""))


def _short_reply_kind(text: str) -> str | None:
    normalized = _normalized_reply_text(text)
    if normalized is None:
        return None
    if reply_kind := normalize_short_reply_kind(normalized):
        return reply_kind
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
    state_cta = normalize_cta(context.cta)
    if state_cta:
        return state_cta
    if context.dialog_state:
        dialog_cta = normalize_cta(context.dialog_state.get("last_cta"))
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
    language: LanguageHint = "unknown",
) -> IntentExtractionResult:
    if previous_cta in ACTION_CTAS:
        return replace(
            result,
            domain="business",
            intent="sales",
            topic=previous_topic or result.topic,
            cta=previous_cta,
            resolved_cta=previous_cta,
            resolved_cta_reply="affirmative",
            turn_relation="short_reply",
            should_search_kb=False,
            should_generate_answer=True,
            should_offer_manager=False,
        )
    if previous_cta == CONTINUE_EXPLANATION_CTA:
        return replace(
            result,
            domain="business",
            intent="sales",
            topic=previous_topic or result.topic,
            cta=CONTINUE_EXPLANATION_CTA,
            resolved_cta=CONTINUE_EXPLANATION_CTA,
            resolved_cta_reply="affirmative",
            turn_relation="continuation",
            should_search_kb=True,
            should_generate_answer=True,
            should_offer_manager=False,
            knowledge_query=_continuation_knowledge_query(
                previous_topic,
                language=language,
            ),
        )
    if result.intent in {"other", "unknown"} and previous_topic:
        return replace(result, domain="business", intent="sales", topic=previous_topic)
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
            domain="business",
            topic=previous_topic or result.topic,
            cta="none",
            resolved_cta=previous_cta,
            resolved_cta_reply="negative",
            turn_relation="short_reply",
            should_search_kb=False,
            should_generate_answer=True,
            should_offer_manager=False,
        )
    if previous_cta == CONTINUE_EXPLANATION_CTA:
        return replace(
            result,
            domain="business",
            topic=previous_topic or result.topic,
            cta="none",
            resolved_cta=CONTINUE_EXPLANATION_CTA,
            resolved_cta_reply="negative",
            turn_relation="short_reply",
            should_search_kb=False,
            should_generate_answer=True,
            should_offer_manager=False,
            knowledge_query=None,
        )
    return result


def _continuation_language(context: IntentExtractionContext) -> LanguageHint:
    reply_language = normalize_short_reply_language(context.user_input)
    if reply_language != "unknown":
        return reply_language

    detected_language = detect_language_hint(context.user_input)
    if detected_language != "unknown":
        return detected_language

    return context.target_language


def _continuation_knowledge_query(
    previous_topic: str | None,
    *,
    language: LanguageHint = "ru",
) -> str:
    topic = (previous_topic or "product").strip().lower()
    language = language if language in {"ru", "en", "de", "es"} else "ru"
    localized_queries = {
        "ru": {
            "product": "подробнее как работает продукт и его возможности",
            "integration": "подробнее как работает интеграция",
        },
        "en": {
            "product": "more details about how the product works and its capabilities",
            "integration": "more details about how the integration works",
        },
        "de": {
            "product": "weitere Einzelheiten zur Funktionsweise und zu den Möglichkeiten des Produkts",
            "integration": "weitere Einzelheiten zur Funktionsweise der Integration",
        },
        "es": {
            "product": "más detalles sobre cómo funciona el producto y sus capacidades",
            "integration": "más detalles sobre cómo funciona la integración",
        },
    }
    fallback_queries = {
        "ru": f"подробнее по теме {topic}",
        "en": f"more details about {topic}",
        "de": f"weitere Einzelheiten zu {topic}",
        "es": f"más detalles sobre {topic}",
    }
    return localized_queries[language].get(topic, fallback_queries[language])
