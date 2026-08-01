from dataclasses import dataclass, field, replace
import re
from typing import Literal, Mapping, cast

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
from src.domain.runtime.knowledge_query import (
    KnowledgeQuerySource,
)
from src.domain.runtime.policy.handoff_request import is_explicit_handoff_request
from src.domain.runtime.policy.intent_topic import (
    recognized_feature_map,
    unrecognized_feature_keys,
)
from src.domain.runtime.state_contracts import (
    RuntimeHistoryMessage,
    MemoryCandidateState,
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
MAX_KNOWLEDGE_QUERY_CHARS = 240
CONTEXTUAL_KNOWLEDGE_QUERY_TURN_RELATIONS = frozenset({"continuation", "reopening"})
KNOWN_REPEAT_RELATIONS = frozenset(
    {"none", "clarification", "repeat_answered", "repeat_unresolved"}
)
KNOWN_MEMORY_TYPES = frozenset({"profile", "preferences", "context", "agreements"})
MAX_CURRENT_SUBJECT_CHARS = 80
MAX_MEMORY_CANDIDATES = 3
MAX_MEMORY_VALUE_CHARS = 240
MEMORY_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


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
    knowledge_query_source: KnowledgeQuerySource = KnowledgeQuerySource.NONE
    knowledge_query_rejected_reason: str | None = None
    current_subject: str | None = None
    repeat_relation: str = "none"
    dissatisfaction: bool = False
    memory_candidates: list[MemoryCandidateState] = field(default_factory=list)

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
        features = {
            key: float(value)
            for key, value in recognized_feature_map(features).items()
            if isinstance(value, (int, float))
        }

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
        turn_relation = _normalized_enum_value(
            payload.get("turn_relation"),
            KNOWN_TURN_RELATIONS,
            "unknown",
        )
        knowledge_query, knowledge_query_rejected_reason = (
            _normalize_payload_knowledge_query(
                payload.get("knowledge_query"),
                domain=domain,
                should_search_kb=should_search_kb,
                turn_relation=turn_relation,
            )
        )

        repeat_relation = _normalized_enum_value(
            payload.get("repeat_relation"), KNOWN_REPEAT_RELATIONS, "none"
        )
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
            is_repeat_like=repeat_relation in {"repeat_answered", "repeat_unresolved"},
            domain=domain,
            turn_relation=turn_relation,
            should_search_kb=should_search_kb,
            should_generate_answer=should_generate_answer,
            should_offer_manager=_coerce_bool(
                payload.get("should_offer_manager"),
                default=False,
            ),
            knowledge_query=knowledge_query,
            knowledge_query_source=(
                KnowledgeQuerySource.MODEL_CONTEXTUAL
                if knowledge_query
                else KnowledgeQuerySource.NONE
            ),
            knowledge_query_rejected_reason=knowledge_query_rejected_reason,
            current_subject=_bounded_optional_text(
                payload.get("current_subject"), MAX_CURRENT_SUBJECT_CHARS
            ),
            repeat_relation=repeat_relation,
            dissatisfaction=_coerce_bool(payload.get("dissatisfaction"), default=False),
            memory_candidates=_normalize_memory_candidates(
                payload.get("memory_candidates"),
                user_input=str(payload.get("_user_input") or ""),
            ),
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
    knowledge_query_source: KnowledgeQuerySource = KnowledgeQuerySource.NONE
    resolved_cta: str | None = None
    resolved_cta_reply: str | None = None
    current_subject: str | None = None
    repeat_relation: str = "none"
    dissatisfaction: bool = False
    memory_candidates: list[MemoryCandidateState] = field(default_factory=list)
    normalization_flags: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_llm_payload(
        cls, payload: Mapping[str, object], *, user_input: str = ""
    ) -> "IntentExtractionResult":
        validated = IntentExtractionPayload.from_mapping(
            {**dict(payload), "_user_input": user_input}
        )
        raw_features = payload.get("features")
        unknown_feature_keys = unrecognized_feature_keys(
            raw_features if isinstance(raw_features, Mapping) else None
        )
        result = cls(
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
            knowledge_query_source=validated.knowledge_query_source,
            current_subject=validated.current_subject,
            repeat_relation=validated.repeat_relation,
            dissatisfaction=validated.dissatisfaction,
            memory_candidates=list(validated.memory_candidates),
            resolved_cta=None,
            resolved_cta_reply=None,
            normalization_flags=(
                {"unrecognized_feature_keys": unknown_feature_keys}
                if unknown_feature_keys
                else {}
            ),
        )
        if validated.knowledge_query_rejected_reason:
            return replace(
                result,
                normalization_flags={
                    **dict(result.normalization_flags),
                    "knowledge_query_rejected_reason": (
                        validated.knowledge_query_rejected_reason
                    ),
                    "knowledge_query_source": KnowledgeQuerySource.NONE.value,
                },
            )
        if validated.knowledge_query:
            return replace(
                result,
                normalization_flags={
                    **dict(result.normalization_flags),
                    "knowledge_query_source": (
                        KnowledgeQuerySource.MODEL_CONTEXTUAL.value
                    ),
                },
            )
        return result

    def normalized_for_context(
        self,
        context: IntentExtractionContext,
    ) -> "IntentExtractionResult":
        reply_kind = _short_reply_kind(context.user_input)
        if reply_kind is None:
            normalized = _normalize_contextual_knowledge_query(
                _normalize_handoff_classification(self, context),
                context,
            )
            return _with_repeat_relation_invariant(
                _normalize_business_question_route(normalized, context)
            )

        previous_topic = _previous_topic(context)
        previous_cta = _previous_cta(context)

        if reply_kind == "affirmative":
            return _with_repeat_relation_invariant(
                _normalize_affirmative_reply(
                    self,
                    previous_topic=previous_topic,
                    previous_cta=previous_cta,
                    language=_continuation_language(context),
                )
            )
        if reply_kind == "negative":
            return _with_repeat_relation_invariant(
                _normalize_negative_reply(
                    self,
                    previous_topic=previous_topic,
                    previous_cta=previous_cta,
                )
            )
        if reply_kind == "price_objection":
            return _with_repeat_relation_invariant(
                replace(
                    self,
                    domain="business",
                    intent="pricing",
                    topic="pricing",
                    cta="none",
                    emotion="negative",
                    should_search_kb=True,
                    should_generate_answer=True,
                )
            )
        if reply_kind == "issue_report":
            return _with_repeat_relation_invariant(
                replace(
                    self,
                    domain="business",
                    intent="support",
                    topic=(
                        "integration" if previous_topic == "integration" else "support"
                    ),
                    cta="none",
                    emotion="negative",
                    should_search_kb=True,
                    should_generate_answer=True,
                )
            )
        return _with_repeat_relation_invariant(self)

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
        patch["knowledge_query_source"] = self.knowledge_query_source.value
        patch["resolved_cta"] = self.resolved_cta
        patch["resolved_cta_reply"] = self.resolved_cta_reply
        patch["current_subject"] = self.current_subject
        patch["repeat_relation"] = cast(
            Literal["none", "clarification", "repeat_answered", "repeat_unresolved"],
            self.repeat_relation,
        )
        patch["dissatisfaction"] = self.dissatisfaction
        patch["memory_candidates"] = list(self.memory_candidates)
        patch["normalization_flags"] = dict(self.normalization_flags)
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


def _bounded_optional_text(value: object, limit: int) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    return text[:limit].strip() or None


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


def _same_normalized_text(left: str | None, right: str | None) -> bool:
    return (
        " ".join(str(left or "").split()).lower()
        == " ".join(str(right or "").split()).lower()
    )


def _normalize_payload_knowledge_query(
    value: object,
    *,
    domain: str,
    should_search_kb: bool,
    turn_relation: str,
) -> tuple[str | None, str | None]:
    query = _optional_text(value)
    if query is None:
        return None, None
    if len(query) > MAX_KNOWLEDGE_QUERY_CHARS:
        return None, "too_long"
    if domain != "business":
        return None, "non_business_domain"
    if not should_search_kb:
        return None, "search_disabled"
    if turn_relation not in CONTEXTUAL_KNOWLEDGE_QUERY_TURN_RELATIONS:
        return None, "not_contextual_turn"
    return query, None


def _dialog_state_or_none(value: object) -> DialogState | None:
    if not isinstance(value, Mapping):
        return None
    return DialogState(
        last_intent=_optional_text(value.get("last_intent")),
        last_cta=normalize_cta(value.get("last_cta")),
        last_topic=_optional_text(value.get("last_topic")),
        repeat_count=int(value.get("repeat_count") or 0),
        last_repeat_increment_reason=_repeat_increment_reason(
            value.get("last_repeat_increment_reason")
        ),
        last_repeat_reset_reason=_repeat_reset_reason(
            value.get("last_repeat_reset_reason")
        ),
        lead_status=str(value.get("lead_status") or "cold"),
        lifecycle=str(value.get("lifecycle") or "cold"),
        handoff_confirmation_pending=bool(
            value.get("handoff_confirmation_pending", False)
        ),
    )


def _repeat_increment_reason(value: object) -> str | None:
    text = _optional_text(value)
    return text if text == "explicit_repeat_like" else None


def _repeat_reset_reason(value: object) -> str | None:
    text = _optional_text(value)
    if text in {"not_repeat_like", "new_topic", "topic_changed", "intent_changed"}:
        return text
    return None


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


def _normalize_handoff_classification(
    result: IntentExtractionResult,
    context: IntentExtractionContext,
) -> IntentExtractionResult:
    has_handoff_classification = result.intent == "handoff_request" or (
        result.topic == "handoff"
        and normalize_cta(result.cta) == "call_manager"
        and result.should_generate_answer is False
    )
    if not has_handoff_classification:
        return result

    if is_explicit_handoff_request(context.user_input):
        return result

    return replace(
        result,
        domain="business",
        intent="support",
        topic="support",
        cta="none",
        should_search_kb=True,
        should_generate_answer=True,
        should_offer_manager=False,
        knowledge_query=None,
        knowledge_query_source=KnowledgeQuerySource.NONE,
        normalization_flags={
            **dict(result.normalization_flags),
            "handoff_intent_downgraded": True,
            "handoff_intent_downgrade_reason": "mention_without_explicit_request",
        },
    )


def _normalize_business_question_route(
    result: IntentExtractionResult,
    context: IntentExtractionContext,
) -> IntentExtractionResult:
    if result.domain != "business":
        return result
    if is_explicit_handoff_request(context.user_input):
        return result
    if result.intent in {"handoff_request", "angry"} or result.topic in {
        "handoff",
        "angry",
    }:
        return result
    if result.resolved_cta in ACTION_CTAS:
        return result
    if result.should_search_kb and result.should_generate_answer:
        return result

    return replace(
        result,
        should_search_kb=True,
        should_generate_answer=True,
        normalization_flags={
            **dict(result.normalization_flags),
            "routing_flags_overridden": True,
            "routing_flag_override_reason": "ordinary_business_question",
        },
    )


def _with_repeat_relation_invariant(
    result: IntentExtractionResult,
) -> IntentExtractionResult:
    return replace(
        result,
        is_repeat_like=result.repeat_relation
        in {"repeat_answered", "repeat_unresolved"},
    )


def _normalize_contextual_knowledge_query(
    result: IntentExtractionResult,
    context: IntentExtractionContext,
) -> IntentExtractionResult:
    if result.knowledge_query is None:
        return result
    if result.resolved_cta_reply == "negative":
        return replace(
            result,
            knowledge_query=None,
            knowledge_query_source=KnowledgeQuerySource.NONE,
            normalization_flags={
                **dict(result.normalization_flags),
                "knowledge_query_rejected_reason": "negative_cta_reply",
            },
        )
    if not result.should_search_kb:
        return replace(
            result,
            knowledge_query=None,
            knowledge_query_source=KnowledgeQuerySource.NONE,
            normalization_flags={
                **dict(result.normalization_flags),
                "knowledge_query_rejected_reason": "search_disabled",
            },
        )
    if result.turn_relation not in CONTEXTUAL_KNOWLEDGE_QUERY_TURN_RELATIONS:
        return replace(
            result,
            knowledge_query=None,
            knowledge_query_source=KnowledgeQuerySource.NONE,
            normalization_flags={
                **dict(result.normalization_flags),
                "knowledge_query_rejected_reason": "not_contextual_turn",
            },
        )
    if _same_normalized_text(result.knowledge_query, context.user_input):
        return replace(
            result,
            knowledge_query=None,
            knowledge_query_source=KnowledgeQuerySource.NONE,
            normalization_flags={
                **dict(result.normalization_flags),
                "knowledge_query_rejected_reason": "same_as_user_input",
            },
        )
    return result


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
            knowledge_query_source=KnowledgeQuerySource.CANONICAL_CONTINUE_EXPLANATION,
            normalization_flags={
                **dict(result.normalization_flags),
                "knowledge_query_source": (
                    KnowledgeQuerySource.CANONICAL_CONTINUE_EXPLANATION.value
                ),
            },
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
            knowledge_query_source=KnowledgeQuerySource.NONE,
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


def _normalize_memory_candidates(
    value: object,
    *,
    user_input: str,
) -> list[MemoryCandidateState]:
    if not isinstance(value, list):
        return []

    candidates: list[MemoryCandidateState] = []
    seen_keys: set[str] = set()
    normalized_input = _normalize_evidence_text(user_input)
    for raw in value:
        if len(candidates) >= MAX_MEMORY_CANDIDATES:
            break
        if not isinstance(raw, Mapping):
            continue
        key = _optional_text(raw.get("key"))
        type_ = _normalized_enum_value(raw.get("type"), KNOWN_MEMORY_TYPES, "")
        confidence = _coerce_float(raw.get("confidence"), default=0.0)
        if key is None or not MEMORY_KEY_PATTERN.fullmatch(key):
            continue
        if key in seen_keys or not type_ or confidence < 0.85:
            continue
        evidence_quote = _bounded_optional_text(
            raw.get("evidence_quote"), MAX_MEMORY_VALUE_CHARS
        )
        if evidence_quote is None:
            continue
        if _normalize_evidence_text(evidence_quote) not in normalized_input:
            continue
        raw_value = raw.get("value")
        if raw_value is None or raw_value == "":
            continue
        if isinstance(raw_value, (dict, list)):
            continue
        candidate_value: object = raw_value
        if isinstance(raw_value, str):
            candidate_value = raw_value.strip()[:MAX_MEMORY_VALUE_CHARS]
            if not candidate_value:
                continue
        seen_keys.add(key)
        candidates.append(
            MemoryCandidateState(
                key=key,
                value=candidate_value,
                type=type_,
                confidence=confidence,
                evidence_quote=evidence_quote,
            )
        )
    return candidates


def _normalize_evidence_text(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _coerce_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        try:
            return max(0.0, min(1.0, float(value.strip())))
        except ValueError:
            return default
    return default
