"""
Response generator node for the LangGraph pipeline.

Uses the configured LLM to craft the final answer from decision, history,
knowledge, memory, and project runtime configuration.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import os
import re
from typing import cast

from src.agent.router.prompt_builder import (
    DEFAULT_KB_LIMIT,
    build_response_prompt,
    format_kb_prompt_entry_traces,
)
from src.agent.state import AgentState
from src.domain.runtime.cta import (
    CONTINUE_EXPLANATION_CTA,
    is_action_cta,
    is_conversational_cta,
)
from src.domain.runtime.language_policy import (
    detect_language_hint,
    normalize_project_language,
)
from src.domain.runtime.project_runtime_profile import ProjectRuntimeProfile
from src.domain.runtime.evidence_references import (
    EvidenceReferenceIndex,
    UnknownEvidenceReference,
)
from src.domain.runtime.response_generation import (
    GENERATION_MODE_VALUES,
    GenerationMode,
    ResponseGenerationContext,
    ResponseGenerationResult,
    StructuredResponseResult,
)
from src.domain.runtime.tool_execution import (
    ToolExecutionStatus,
    normalize_tool_execution_status,
)
from src.domain.runtime.state_contracts import (
    ProjectRuntimeConfigurationState,
    RuntimeHistoryMessage,
    RuntimeStateInput,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.llm.completion_client import (
    ChatGroqClient,
    GroqTextCompletionClient,
)
from src.infrastructure.logging.logger import get_logger, log_node_execution

logger = get_logger(__name__)

TECHNICAL_FAILURE_FIRST_TEXT = (
    "Не получилось сгенерировать ответ из-за технической ошибки. "
    "Можете повторить запрос, а если вопрос срочный — я передам диалог менеджеру."
)

TECHNICAL_FAILURE_REPEAT_TEXT = (
    "Похоже, техническая ошибка повторилась. Я уже передал технический инцидент "
    "владельцу проекта. Можете позвать менеджера, чтобы не ждать восстановления ассистента."
)

LANGUAGE_MISMATCH_FALLBACK_RU = (
    "Хочу ответить на вашем языке корректно. "
    "Уточните, пожалуйста, вопрос ещё раз, и я помогу."
)
LANGUAGE_MISMATCH_FALLBACK_EN = (
    "I want to respond correctly in your language. "
    "Please rephrase your question, and I will help."
)
LANGUAGE_MISMATCH_FALLBACK_DE = (
    "Ich möchte korrekt in Ihrer Sprache antworten. "
    "Bitte formulieren Sie Ihre Frage noch einmal, dann helfe ich Ihnen."
)
LANGUAGE_MISMATCH_FALLBACK_ES = (
    "Quiero responder correctamente en su idioma. "
    "Por favor, reformule su pregunta y le ayudaré."
)
CONTINUATION_TOPICS = frozenset({"product", "integration"})
QUESTION_ENDINGS = ("?", "？")
ACTION_OFFER_MARKERS = (
    "менеджер",
    "звонок",
    "созвон",
    "консультац",
    "передать",
    "manager",
    "operator",
    "call",
    "consult",
)
CJK_PATTERN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


@dataclass(frozen=True, slots=True)
class ContinuationOfferDecision:
    should_offer: bool
    cta: str | None = None


@dataclass(frozen=True, slots=True)
class StructuredGenerationValidation:
    result: StructuredResponseResult | None
    parse_status: str
    schema_status: str
    evidence_reference_status: str
    failure_reason: str | None = None


REPAIRABLE_VALIDATION_FAILURES = frozenset(
    {
        "invalid_json",
        "invalid_schema",
        "invalid answerability",
        "legacy supporting_entry_ids field is forbidden",
        "invalid_supporting_evidence_refs",
        "missing_supporting_evidence_refs",
        "duplicate_supporting_evidence_refs",
        "missing_answer",
        "missing_unsupported_aspects",
        "supported_with_unsupported_aspects",
        "unsupported_answer_must_be_empty",
        "supporting_refs_invalid_for_answerability",
        "conflicting_evidence_requires_two_supporting_refs",
        "conflicting_answer_must_be_empty",
    }
)


async def _invoke_response_model(
    *,
    llm: ChatGroqClient | None,
    selected_model: str,
    base_model: str,
    prompt: str,
) -> str:
    client_llm = llm if selected_model == base_model else None
    return await GroqTextCompletionClient().complete(
        prompt,
        model_name=selected_model,
        temperature=0.3,
        max_tokens=700,
        llm=client_llm,
    )


def _merge_dialog_state_into_user_memory(
    user_memory: dict[str, list[dict[str, object]]] | None,
    dialog_state: dict[str, object] | None,
) -> dict[str, list[dict[str, object]]] | None:
    if not dialog_state:
        return user_memory

    merged: dict[str, list[dict[str, object]]] = {}
    if user_memory:
        for memory_type, items in user_memory.items():
            merged[memory_type] = [dict(item) for item in items]

    merged["dialog_state"] = [{"key": "dialog_state", "value": dialog_state}]
    return merged


def _resolve_response_model_name(state: AgentState, default_model: str) -> str:
    profile = ProjectRuntimeProfile.from_configuration(
        state.get("project_configuration")
    )
    return profile.fallback_model or default_model


def _prompt_user_memory(value: object) -> dict[str, list[dict[str, object]]] | None:
    if not isinstance(value, Mapping):
        return None

    normalized: dict[str, list[dict[str, object]]] = {}
    for raw_key, raw_items in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_items, list):
            continue

        items: list[dict[str, object]] = []
        for raw_item in raw_items:
            if isinstance(raw_item, Mapping):
                items.append(
                    {
                        str(item_key): item_value
                        for item_key, item_value in raw_item.items()
                    }
                )

        normalized[raw_key] = items

    return normalized


def _prompt_dialog_state(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return {str(key): item for key, item in value.items()}


def _prompt_history(value: object) -> list[RuntimeHistoryMessage] | None:
    if not isinstance(value, list):
        return None

    history: list[RuntimeHistoryMessage] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue

        role = item.get("role")
        content = item.get("content")
        if role is None or content is None:
            continue

        history.append(
            RuntimeHistoryMessage(
                role=str(role),
                content=str(content),
            )
        )

    return history


def _prompt_features(value: object) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None

    features: dict[str, float] = {}
    for key, raw_value in value.items():
        if not isinstance(key, str):
            continue
        try:
            features[key] = float(raw_value)
        except (TypeError, ValueError):
            continue

    return features


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _rag_debug_enabled() -> bool:
    return os.getenv("RAG_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _preview_text(value: object, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _history_item_value(item: object, field: str) -> object:
    if isinstance(item, Mapping):
        return item.get(field)
    try:
        return getattr(item, field, None)
    except Exception:
        return None


def _history_tail_preview(history: Sequence[object]) -> list[dict[str, str]]:
    previews: list[dict[str, str]] = []
    for item in history[-5:]:
        role = _history_item_value(item, "role")
        content = _history_item_value(item, "content")
        previews.append(
            {
                "role": str(role or "message"),
                "content_preview": _preview_text(content, 120) or "",
            }
        )
    return previews


def _knowledge_chunk_id(item: object) -> object:
    if not isinstance(item, Mapping):
        return None
    return item.get("id")


def _project_target_language(state: AgentState) -> str:
    configuration = state.get("project_configuration")
    settings_block: Mapping[str, object] = {}
    if isinstance(configuration, Mapping):
        raw_settings = configuration.get("settings")
        if isinstance(raw_settings, Mapping):
            settings_block = raw_settings

    target = normalize_project_language(
        str(settings_block.get("target_language") or "")
    )

    profile = ProjectRuntimeProfile.from_configuration(configuration)
    if target == "unknown":
        target = normalize_project_language(profile.target_language)
    if target == "unknown":
        target = normalize_project_language(profile.default_language)
    return target


def _language_mismatch_fallback(target_language: str) -> str:
    if target_language == "en":
        return LANGUAGE_MISMATCH_FALLBACK_EN
    if target_language == "de":
        return LANGUAGE_MISMATCH_FALLBACK_DE
    if target_language == "es":
        return LANGUAGE_MISMATCH_FALLBACK_ES
    return LANGUAGE_MISMATCH_FALLBACK_RU


def _continuation_prompt(target_language: str) -> str:
    if target_language == "en":
        return "Would you like me to explain how it works in more detail?"
    if target_language == "de":
        return "Möchten Sie genauer wissen, wie das funktioniert?"
    if target_language == "es":
        return "¿Quieres que te explique con más detalle cómo funciona?"
    return "Хотите узнать больше о том, как это работает?"


def _with_continuation_prompt(response_text: str, target_language: str) -> str:
    prompt = _continuation_prompt(target_language)
    stripped = response_text.strip()
    if not stripped:
        return stripped
    return f"{stripped}\n\n{prompt}"


def _last_question_sentence(text: str) -> str:
    stripped = text.strip()
    if not stripped.endswith(QUESTION_ENDINGS):
        return ""
    parts = [part.strip() for part in stripped.replace("\n", " ").split(".")]
    return parts[-1] if parts else stripped


def _remove_last_question_sentence(text: str) -> str:
    stripped = text.strip()
    question_index = max(stripped.rfind("?"), stripped.rfind("？"))
    if question_index < 0:
        return stripped

    prefix = stripped[:question_index].rstrip()
    sentence_starts = (
        prefix.rfind("\n\n"),
        prefix.rfind(". "),
        prefix.rfind("! "),
        prefix.rfind("? "),
    )
    cut_index = max(sentence_starts)
    if cut_index < 0:
        return ""

    return prefix[: cut_index + 1].strip()


def _sanitize_generated_action_cta(
    response_text: str,
) -> tuple[str, bool]:
    # Defensive compatibility layer: remove orphan action-offer endings from
    # legacy/free-form model text. Canonical policy state remains the only
    # source of action CTA, lifecycle changes, or handoff routing.
    question = _last_question_sentence(response_text).lower()
    if not question:
        return response_text, False

    if any(marker in question for marker in ACTION_OFFER_MARKERS):
        sanitized = _remove_last_question_sentence(response_text)
        return sanitized, True

    return response_text, False


def _no_confirmation_text(target_language: str) -> str:
    if target_language == "en":
        return (
            "The available knowledge base does not contain data that can confirm this."
        )
    if target_language == "de":
        return "Die verfügbare Wissensbasis enthält keine Daten, mit denen sich das bestätigen lässt."
    if target_language == "es":
        return "La base de conocimiento disponible no contiene datos que permitan confirmarlo."
    return "В доступной базе знаний нет данных, позволяющих подтвердить это."


def _retrieval_failed_text(target_language: str) -> str:
    if target_language == "en":
        return "I cannot check the knowledge base right now due to a technical issue."
    if target_language == "de":
        return "Ich kann die Wissensbasis gerade wegen eines technischen Problems nicht prüfen."
    if target_language == "es":
        return (
            "Ahora no puedo consultar la base de conocimiento por un problema técnico."
        )
    return "Сейчас не получается проверить базу знаний из-за технической ошибки."


def _conflicting_evidence_text(target_language: str) -> str:
    if target_language == "en":
        return "The available knowledge base contains conflicting information, so I cannot answer confidently."
    if target_language == "de":
        return "Die verfügbare Wissensbasis enthält widersprüchliche Informationen, daher kann ich nicht sicher antworten."
    if target_language == "es":
        return "La base de conocimiento disponible contiene información contradictoria, así que no puedo responder con certeza."
    return "В доступной базе знаний есть противоречивые сведения, поэтому я не могу уверенно ответить."


def _invalid_generation_text(target_language: str) -> str:
    if target_language == "en":
        return "I could not form a correct answer from the available knowledge base right now."
    if target_language == "de":
        return "Ich konnte gerade keine korrekte Antwort aus der verfügbaren Wissensbasis bilden."
    if target_language == "es":
        return "Ahora no pude formar una respuesta correcta a partir de la base de conocimiento disponible."
    return (
        "Сейчас не получилось сформировать корректный ответ по доступной базе знаний."
    )


def _contains_invalid_language_mix(response_text: str, target_language: str) -> bool:
    return target_language == "ru" and bool(CJK_PATTERN.search(response_text))


def _unwrap_json_block(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.strip().startswith("json"):
            text = text.strip()[4:]
    return text.strip()


def build_structured_response_repair_prompt(
    *,
    original_prompt: str,
    invalid_output: str,
    validation: StructuredGenerationValidation,
    known_evidence_refs: Sequence[str],
) -> str:
    refs = ", ".join(known_evidence_refs) if known_evidence_refs else "none"
    return (
        f"{original_prompt}\n\n"
        "The previous response did not satisfy the required JSON contract.\n"
        f"Failure reason: {validation.failure_reason or 'invalid_generation'}\n"
        f"Allowed evidence refs: {refs}\n"
        f"Invalid output chars: {len(invalid_output)}\n\n"
        "Repair instructions:\n"
        "- Return only valid JSON and no markdown.\n"
        "- Use only the field supporting_evidence_refs for evidence references.\n"
        "- Do not return the legacy field supporting_entry_ids.\n"
        "- Use only evidence refs listed above, exactly as written and case-sensitive.\n"
        "- Do not add facts, sources, internal IDs, hashes, source IDs, or document IDs.\n"
        "- Do not change answerability unless it is necessary to fix the contract error.\n"
    )


def _generation_metadata(
    *,
    generation_mode: str | None,
    retrieval_status: str,
    model_answerability: str | None,
    supporting_entry_ids: list[str] | None = None,
    unsupported_aspects: list[str] | None = None,
    supporting_evidence_refs: list[str] | None = None,
    parse_status: str,
    schema_status: str,
    evidence_reference_status: str,
    semantic_grounding_status: str,
    semantic_grounding_failure_reason: str | None = None,
    fallback_reason: str | None = None,
    generation_attempt_count: int = 0,
    initial_validation_failure_reason: str | None = None,
    repair_attempted: bool = False,
    repair_validation_failure_reason: str | None = None,
    repair_succeeded: bool = False,
) -> dict[str, object]:
    return {
        "generation_mode": generation_mode,
        "retrieval_status": retrieval_status,
        "model_answerability": model_answerability,
        "supporting_entry_ids": supporting_entry_ids or [],
        "supporting_evidence_refs": supporting_evidence_refs or [],
        "unsupported_aspects": unsupported_aspects or [],
        "generation_output_parse_status": parse_status,
        "generation_schema_status": schema_status,
        "evidence_reference_status": evidence_reference_status,
        "semantic_grounding_status": semantic_grounding_status,
        "semantic_grounding_failure_reason": semantic_grounding_failure_reason,
        "fallback_reason": fallback_reason,
        "generation_attempt_count": generation_attempt_count,
        "initial_validation_failure_reason": initial_validation_failure_reason,
        "repair_attempted": repair_attempted,
        "repair_validation_failure_reason": repair_validation_failure_reason,
        "repair_succeeded": repair_succeeded,
    }


def _response_patch(
    *,
    response_text: str,
    metadata: dict[str, object],
    cta: str | None = None,
    topic: str | None = None,
) -> dict[str, object]:
    patch = dict(
        ResponseGenerationResult(
            response_text=response_text,
            metadata=metadata,
            cta=cta,
            topic=topic,
        ).to_state_patch()
    )
    patch.update(
        {
            "generation_mode": metadata.get("generation_mode"),
            "model_answerability": metadata.get("model_answerability"),
            "model_evidence_refs": metadata.get("supporting_evidence_refs", []),
            "supporting_entry_ids": metadata.get("supporting_entry_ids", []),
            "resolved_supporting_entry_ids": metadata.get("supporting_entry_ids", []),
            "unsupported_aspects": metadata.get("unsupported_aspects", []),
            "generation_output_parse_status": metadata.get(
                "generation_output_parse_status"
            ),
            "generation_schema_status": metadata.get("generation_schema_status"),
            "evidence_reference_status": metadata.get("evidence_reference_status"),
            "semantic_grounding_status": metadata.get("semantic_grounding_status"),
            "semantic_grounding_failure_reason": metadata.get(
                "semantic_grounding_failure_reason"
            ),
            "fallback_reason": metadata.get("fallback_reason"),
        }
    )
    return patch


def _continuation_offer_decision(
    context: ResponseGenerationContext,
    *,
    response_text: str,
    is_fallback_response: bool,
) -> ContinuationOfferDecision:
    if is_fallback_response:
        return ContinuationOfferDecision(False)
    if response_text.strip().endswith(QUESTION_ENDINGS):
        return ContinuationOfferDecision(False)
    if context.decision not in {"LLM_GENERATE", "RESPOND_KB"}:
        return ContinuationOfferDecision(False)
    if context.topic not in CONTINUATION_TOPICS:
        return ContinuationOfferDecision(False)
    if is_action_cta(context.cta) or is_conversational_cta(context.cta):
        return ContinuationOfferDecision(False)
    if context.turn_relation in {"short_reply", "continuation"}:
        return ContinuationOfferDecision(False)
    if _dialog_repeat_count(context.dialog_state) > 1:
        return ContinuationOfferDecision(False)
    return ContinuationOfferDecision(True, CONTINUE_EXPLANATION_CTA)


def _dialog_repeat_count(value: object) -> int:
    if not isinstance(value, Mapping):
        return 0
    raw = value.get("repeat_count")
    return _coerce_int(raw, default=0)


def build_answer_preview_prompt(
    *,
    user_input: str,
    knowledge_chunks: list[object],
    project_configuration: Mapping[str, object] | None,
    target_language: str,
) -> str:
    resolved_target_language: str = normalize_project_language(target_language)
    if resolved_target_language == "unknown":
        resolved_target_language = _project_target_language(
            cast(
                AgentState,
                {
                    "user_input": user_input,
                    "project_configuration": project_configuration or {},
                },
            )
        )
    return build_response_prompt(
        decision="LLM_GENERATE",
        user_input=user_input,
        conversation_summary="",
        history=[],
        knowledge_chunks=knowledge_chunks,
        generation_mode="KNOWLEDGE_ANSWER",
        tool_result=None,
        user_memory=None,
        features=None,
        project_configuration=cast(
            ProjectRuntimeConfigurationState | None,
            project_configuration,
        ),
        target_language=resolved_target_language,
    )


async def complete_response_prompt(
    prompt: str,
    *,
    project_configuration: Mapping[str, object] | None = None,
    llm: ChatGroqClient | None = None,
    model_name: str | None = None,
) -> str:
    base_model = model_name or settings.GROQ_MODEL
    selected_model = _resolve_response_model_name(
        cast(AgentState, {"project_configuration": project_configuration or {}}),
        base_model,
    )
    client_llm = llm if selected_model == base_model else None
    return await GroqTextCompletionClient().complete(
        prompt,
        model_name=selected_model,
        temperature=0.3,
        max_tokens=500,
        llm=client_llm,
    )


def _technical_failure_patch(state: AgentState, exc: Exception) -> dict[str, object]:
    previous_count = _coerce_int(state.get("technical_failure_count"), 0)
    next_count = previous_count + 1

    response_text = (
        TECHNICAL_FAILURE_REPEAT_TEXT
        if next_count >= 2
        else TECHNICAL_FAILURE_FIRST_TEXT
    )

    patch = _response_patch(
        response_text=response_text,
        metadata=_generation_metadata(
            generation_mode=str(state.get("generation_mode") or "UNKNOWN"),
            retrieval_status=str(state.get("knowledge_retrieval_status") or "unknown"),
            model_answerability=None,
            parse_status="not_called",
            schema_status="not_called",
            evidence_reference_status="not_called",
            semantic_grounding_status="not_applicable",
            fallback_reason="generation_exception",
        ),
    )
    patch.update(
        {
            "technical_failure_count": next_count,
            "technical_failure_stage": "response_generator",
            "technical_failure_error": type(exc).__name__,
            "requires_human": False,
        }
    )

    patch["technical_incident_created"] = bool(
        state.get("technical_incident_created") or False
    )

    return patch


def _validate_structured_response(
    raw_content: str,
    *,
    context: ResponseGenerationContext,
) -> StructuredGenerationValidation:
    try:
        payload = json.loads(_unwrap_json_block(raw_content))
    except json.JSONDecodeError:
        return StructuredGenerationValidation(
            result=None,
            parse_status="invalid_json",
            schema_status="invalid_payload",
            evidence_reference_status="not_called",
            failure_reason="invalid_json",
        )
    if not isinstance(payload, Mapping):
        return StructuredGenerationValidation(
            result=None,
            parse_status="invalid_schema",
            schema_status="invalid_payload",
            evidence_reference_status="not_called",
            failure_reason="invalid_schema",
        )

    try:
        result = StructuredResponseResult.from_mapping(payload)
    except ValueError as exc:
        reason = str(exc)
        return StructuredGenerationValidation(
            result=None,
            parse_status="valid",
            schema_status="invalid_enum"
            if reason == "invalid answerability"
            else "invalid_payload",
            evidence_reference_status="not_called",
            failure_reason=reason,
        )

    if context.generation_mode != GenerationMode.KNOWLEDGE_ANSWER:
        if result.supporting_evidence_refs:
            return StructuredGenerationValidation(
                result=None,
                parse_status="valid",
                schema_status="invalid_answerability_contract",
                evidence_reference_status="not_applicable",
                failure_reason="non_kb_response_with_supporting_refs",
            )
        if result.answerability != "supported":
            return StructuredGenerationValidation(
                result=None,
                parse_status="valid",
                schema_status="invalid_answerability_contract",
                evidence_reference_status="not_applicable",
                failure_reason="non_kb_response_must_be_supported",
            )
        if result.unsupported_aspects:
            return StructuredGenerationValidation(
                result=None,
                parse_status="valid",
                schema_status="invalid_answerability_contract",
                evidence_reference_status="not_applicable",
                failure_reason="non_kb_response_with_unsupported_aspects",
            )
        if not result.answer:
            return StructuredGenerationValidation(
                result=None,
                parse_status="valid",
                schema_status="missing_required_answer",
                evidence_reference_status="not_applicable",
                failure_reason="missing_answer",
            )
        return StructuredGenerationValidation(
            result=result,
            parse_status="valid",
            schema_status="valid",
            evidence_reference_status="not_applicable",
        )

    refs = result.supporting_evidence_refs
    if len(refs) != len(set(refs)):
        return StructuredGenerationValidation(
            result=None,
            parse_status="valid",
            schema_status="valid",
            evidence_reference_status="invalid_for_answerability",
            failure_reason="duplicate_supporting_evidence_refs",
        )

    if result.answerability in {"supported", "partially_supported"}:
        if not result.answer:
            return StructuredGenerationValidation(
                result=None,
                parse_status="valid",
                schema_status="missing_required_answer",
                evidence_reference_status="not_called",
                failure_reason="missing_answer",
            )
        if not refs:
            return StructuredGenerationValidation(
                result=None,
                parse_status="valid",
                schema_status="valid",
                evidence_reference_status="missing_required_refs",
                failure_reason="missing_supporting_evidence_refs",
            )

    if result.answerability == "partially_supported" and not result.unsupported_aspects:
        return StructuredGenerationValidation(
            result=None,
            parse_status="valid",
            schema_status="invalid_answerability_contract",
            evidence_reference_status="valid",
            failure_reason="missing_unsupported_aspects",
        )

    if result.answerability == "supported" and result.unsupported_aspects:
        return StructuredGenerationValidation(
            result=None,
            parse_status="valid",
            schema_status="invalid_answerability_contract",
            evidence_reference_status="valid",
            failure_reason="supported_with_unsupported_aspects",
        )

    if result.answerability == "unsupported":
        if result.answer:
            return StructuredGenerationValidation(
                result=None,
                parse_status="valid",
                schema_status="invalid_answerability_contract",
                evidence_reference_status="not_called",
                failure_reason="unsupported_answer_must_be_empty",
            )
        if refs:
            return StructuredGenerationValidation(
                result=None,
                parse_status="valid",
                schema_status="valid",
                evidence_reference_status="invalid_for_answerability",
                failure_reason="supporting_refs_invalid_for_answerability",
            )
        if not result.unsupported_aspects:
            return StructuredGenerationValidation(
                result=None,
                parse_status="valid",
                schema_status="invalid_answerability_contract",
                evidence_reference_status="valid",
                failure_reason="missing_unsupported_aspects",
            )

    if result.answerability == "conflicting_evidence":
        distinct_refs = set(refs)
        if len(refs) < 2 or len(distinct_refs) < 2:
            return StructuredGenerationValidation(
                result=None,
                parse_status="valid",
                schema_status="valid",
                evidence_reference_status="invalid_for_answerability",
                failure_reason="conflicting_evidence_requires_two_supporting_refs",
            )
        if result.answer:
            return StructuredGenerationValidation(
                result=None,
                parse_status="valid",
                schema_status="invalid_answerability_contract",
                evidence_reference_status="valid",
                failure_reason="conflicting_answer_must_be_empty",
            )

    evidence_index = EvidenceReferenceIndex.from_knowledge_chunks(
        context.knowledge_chunks,
        limit=DEFAULT_KB_LIMIT,
    )
    try:
        resolved_entry_ids = evidence_index.resolve_aliases(refs)
    except UnknownEvidenceReference:
        return StructuredGenerationValidation(
            result=None,
            parse_status="valid",
            schema_status="valid",
            evidence_reference_status="unknown_refs",
            failure_reason="invalid_supporting_evidence_refs",
        )

    return StructuredGenerationValidation(
        result=result.with_resolved_entry_ids(resolved_entry_ids),
        parse_status="valid",
        schema_status="valid",
        evidence_reference_status="valid",
    )


def _safe_generation_fallback(
    *,
    generation_mode: str | None,
    target_language: str,
    retrieval_status: str,
    parse_status: str = "not_called",
    schema_status: str = "not_called",
    evidence_reference_status: str = "not_called",
    semantic_grounding_status: str = "not_applicable",
    fallback_reason: str,
) -> dict[str, object]:
    if fallback_reason == "retrieval_failed":
        response_text = _retrieval_failed_text(target_language)
    elif fallback_reason == "conflicting_evidence":
        response_text = _conflicting_evidence_text(target_language)
    elif fallback_reason in {
        "invalid_generation",
        "generation_mode_contract_violation",
        "retrieval_contract_violation",
        "tool_result_contract_violation",
        "orphan_action_cta_removed",
    }:
        response_text = _invalid_generation_text(target_language)
    else:
        response_text = _no_confirmation_text(target_language)

    return _response_patch(
        response_text=response_text,
        metadata=_generation_metadata(
            generation_mode=generation_mode,
            retrieval_status=retrieval_status,
            model_answerability=None,
            parse_status=parse_status,
            schema_status=schema_status,
            evidence_reference_status=evidence_reference_status,
            semantic_grounding_status=semantic_grounding_status,
            fallback_reason=fallback_reason,
        ),
    )


def _emit_generation_trace(
    *,
    trace_extra: dict[str, object] | None,
    status: str,
    patch: Mapping[str, object],
    response_cta: str | None,
    response_topic: str | None,
    is_fallback_response: bool,
    parse_status: str,
    generated_action_cta_detected: bool,
    error_type: str | None = None,
    error_preview: str | None = None,
) -> None:
    if not _rag_debug_enabled():
        return
    raw_metadata = patch.get("metadata")
    metadata: Mapping[str, object] = (
        raw_metadata if isinstance(raw_metadata, Mapping) else {}
    )
    logger.info(
        "RAG generation context trace",
        extra={
            **(trace_extra or {}),
            "generation_status": status,
            "error_type": error_type,
            "error_preview": error_preview,
            "generated_response_preview": _preview_text(patch.get("response_text")),
            "fallback_response_preview": (
                _preview_text(patch.get("response_text"))
                if is_fallback_response
                else None
            ),
            "response_cta": response_cta,
            "response_topic": response_topic,
            "is_fallback_response": is_fallback_response,
            "generation_mode": metadata.get("generation_mode"),
            "model_answerability": metadata.get("model_answerability"),
            "supporting_entry_ids": metadata.get("supporting_entry_ids", []),
            "unsupported_aspects": metadata.get("unsupported_aspects", []),
            "generation_output_parse_status": metadata.get(
                "generation_output_parse_status", parse_status
            ),
            "generation_schema_status": metadata.get("generation_schema_status"),
            "evidence_reference_status": metadata.get("evidence_reference_status"),
            "semantic_grounding_status": metadata.get("semantic_grounding_status"),
            "semantic_grounding_failure_reason": metadata.get(
                "semantic_grounding_failure_reason"
            ),
            "fallback_reason": metadata.get("fallback_reason"),
            "generation_attempt_count": metadata.get("generation_attempt_count", 0),
            "initial_validation_failure_reason": metadata.get(
                "initial_validation_failure_reason"
            ),
            "repair_attempted": metadata.get("repair_attempted", False),
            "repair_validation_failure_reason": metadata.get(
                "repair_validation_failure_reason"
            ),
            "repair_succeeded": metadata.get("repair_succeeded", False),
            "canonical_response_cta": response_cta,
            "generated_action_cta_detected": generated_action_cta_detected,
        },
    )


def _generation_mode_contract_violation(
    context: ResponseGenerationContext,
) -> str | None:
    if context.generation_mode not in GENERATION_MODE_VALUES:
        return "missing_or_invalid_generation_mode"
    return None


def _retrieval_contract_violation(context: ResponseGenerationContext) -> str | None:
    if context.generation_mode != GenerationMode.KNOWLEDGE_ANSWER:
        return None

    has_chunks = bool(context.knowledge_chunks)
    status = context.knowledge_retrieval_status
    if status == "retrieved" and has_chunks:
        return None
    if status == "empty" and not has_chunks:
        return None
    if status == "failed" and not has_chunks:
        return None
    if status == "retrieved":
        return "retrieved_without_entries"
    if status in {"empty", "failed"}:
        return f"{status}_with_entries"
    return f"invalid_knowledge_retrieval_status:{status}"


def _semantic_grounding_status_for(result: StructuredResponseResult) -> str:
    if result.answerability in {"supported", "partially_supported"}:
        return "unchecked"
    return "not_applicable"


def _tool_failure_text(target_language: str) -> str:
    if target_language == "en":
        return "The requested action could not be completed due to a technical issue."
    if target_language == "de":
        return "Die angeforderte Aktion konnte wegen eines technischen Problems nicht abgeschlossen werden."
    if target_language == "es":
        return "La acción solicitada no se pudo completar por un problema técnico."
    return "Не получилось выполнить запрошенное действие из-за технической ошибки."


def _tool_result_contract_violation(context: ResponseGenerationContext) -> str | None:
    if context.generation_mode != GenerationMode.TOOL_RESULT_RESPONSE:
        return None

    status = normalize_tool_execution_status(context.tool_execution_status)
    if status is None:
        return "missing_or_invalid_tool_execution_status"
    if status is ToolExecutionStatus.REQUIRES_HUMAN:
        return "requires_human_tool_result_in_response_generator"
    if status is ToolExecutionStatus.FAILED:
        return None
    if context.tool_result is None and not _has_tool_response_text(context):
        return "missing_or_malformed_tool_result"
    return None


def _has_tool_response_text(context: ResponseGenerationContext) -> bool:
    return bool((context.tool_response_text or "").strip())


def _tool_result_failed(context: ResponseGenerationContext) -> bool:
    if context.generation_mode != GenerationMode.TOOL_RESULT_RESPONSE:
        return False
    return (
        normalize_tool_execution_status(context.tool_execution_status)
        is ToolExecutionStatus.FAILED
    )


def create_response_generator_node(
    llm: ChatGroqClient | None = None,
    model_name: str | None = None,
):
    """
    Create the response-generator graph node.

    Args:
        llm: Optional pre-configured base LLM client.
        model_name: Optional base model override.

    Returns:
        Async LangGraph node that emits a response_text state patch.
    """

    base_model = model_name or settings.GROQ_MODEL

    async def _response_generator_node_impl(state: AgentState) -> dict[str, object]:
        context = ResponseGenerationContext.from_state(cast(RuntimeStateInput, state))
        if context.decision not in {
            "LLM_GENERATE",
            "RESPOND_KB",
            "CALL_TOOL",
        }:
            logger.debug(
                "Skipping response generation, decision not generative",
                extra={"decision": context.decision},
            )
            return {}

        input_lang = detect_language_hint(context.user_input)
        target_lang = _project_target_language(state)
        if target_lang == "unknown":
            target_lang = input_lang

        logger.debug(
            "Preparing response prompt",
            extra={
                "decision": context.decision,
                "history_count": len(context.history),
                "knowledge_chunk_count": len(context.knowledge_chunks),
                "has_dialog_state": bool(context.dialog_state),
                "knowledge_retrieval_status": context.knowledge_retrieval_status,
                "generation_mode": context.generation_mode,
            },
        )

        generation_trace_extra: dict[str, object] | None = None
        if _rag_debug_enabled():
            generation_trace_extra = {
                "thread_id": state.get("thread_id"),
                "project_id": state.get("project_id"),
                "model_name": _resolve_response_model_name(state, base_model),
                "decision": context.decision,
                "generation_mode": context.generation_mode,
                "user_input_preview": _preview_text(context.user_input),
                "history_count": len(context.history),
                "history_tail_preview": _history_tail_preview(context.history),
                "conversation_summary_preview": _preview_text(
                    context.conversation_summary
                ),
                "retrieved_entries_count": len(context.knowledge_chunks),
                "retrieved_entry_ids": [
                    entry_id
                    for item in context.knowledge_chunks[:5]
                    if (entry_id := _knowledge_chunk_id(item)) is not None
                ],
                "prompt_entries": format_kb_prompt_entry_traces(
                    context.knowledge_chunks
                ),
                "retrieval_status": context.knowledge_retrieval_status,
                "prompt_chars": 0,
                "user_input_len": len(context.user_input),
            }

        mode_violation = _generation_mode_contract_violation(context)
        if mode_violation:
            logger.error(
                "Response generation mode contract violation",
                extra={
                    "generation_mode": context.generation_mode,
                    "decision": context.decision,
                    "violation": mode_violation,
                },
            )
            patch = _safe_generation_fallback(
                generation_mode=str(context.generation_mode or "UNKNOWN"),
                target_language=target_lang,
                retrieval_status=context.knowledge_retrieval_status,
                semantic_grounding_status="not_applicable",
                fallback_reason="generation_mode_contract_violation",
            )
            _emit_generation_trace(
                trace_extra=generation_trace_extra,
                status="skipped",
                patch=patch,
                response_cta=None,
                response_topic=None,
                is_fallback_response=True,
                parse_status="not_called",
                generated_action_cta_detected=False,
            )
            return patch

        assert context.generation_mode is not None
        generation_mode = context.generation_mode.value
        retrieval_violation = _retrieval_contract_violation(context)
        if retrieval_violation:
            logger.error(
                "Response generation retrieval contract violation",
                extra={
                    "generation_mode": context.generation_mode,
                    "retrieval_status": context.knowledge_retrieval_status,
                    "entries_count": len(context.knowledge_chunks),
                    "violation": retrieval_violation,
                },
            )
            patch = _safe_generation_fallback(
                generation_mode=str(context.generation_mode or "UNKNOWN"),
                target_language=target_lang,
                retrieval_status=context.knowledge_retrieval_status,
                semantic_grounding_status="not_applicable",
                fallback_reason="retrieval_contract_violation",
            )
            _emit_generation_trace(
                trace_extra=generation_trace_extra,
                status="skipped",
                patch=patch,
                response_cta=None,
                response_topic=None,
                is_fallback_response=True,
                parse_status="not_called",
                generated_action_cta_detected=False,
            )
            return patch

        if context.generation_mode == GenerationMode.KNOWLEDGE_ANSWER:
            if context.knowledge_retrieval_status == "failed":
                patch = _safe_generation_fallback(
                    generation_mode=generation_mode,
                    target_language=target_lang,
                    retrieval_status=context.knowledge_retrieval_status,
                    fallback_reason="retrieval_failed",
                )
                _emit_generation_trace(
                    trace_extra=generation_trace_extra,
                    status="skipped",
                    patch=patch,
                    response_cta=None,
                    response_topic=None,
                    is_fallback_response=True,
                    parse_status="not_called",
                    generated_action_cta_detected=False,
                )
                return patch
            if context.knowledge_retrieval_status == "empty":
                patch = _safe_generation_fallback(
                    generation_mode=generation_mode,
                    target_language=target_lang,
                    retrieval_status=context.knowledge_retrieval_status,
                    fallback_reason="no_evidence",
                )
                _emit_generation_trace(
                    trace_extra=generation_trace_extra,
                    status="skipped",
                    patch=patch,
                    response_cta=None,
                    response_topic=None,
                    is_fallback_response=True,
                    parse_status="not_called",
                    generated_action_cta_detected=False,
                )
                return patch

        tool_violation = _tool_result_contract_violation(context)
        if tool_violation:
            logger.error(
                "Response generation tool result contract violation",
                extra={
                    "generation_mode": context.generation_mode,
                    "tool_execution_status": context.tool_execution_status,
                    "has_tool_result": context.tool_result is not None,
                    "violation": tool_violation,
                },
            )
            patch = _safe_generation_fallback(
                generation_mode=str(context.generation_mode or "UNKNOWN"),
                target_language=target_lang,
                retrieval_status=context.knowledge_retrieval_status,
                semantic_grounding_status="not_applicable",
                fallback_reason="tool_result_contract_violation",
            )
            _emit_generation_trace(
                trace_extra=generation_trace_extra,
                status="skipped",
                patch=patch,
                response_cta=None,
                response_topic=None,
                is_fallback_response=True,
                parse_status="not_called",
                generated_action_cta_detected=False,
            )
            return patch

        if _tool_result_failed(context):
            patch = _response_patch(
                response_text=_tool_failure_text(target_lang),
                metadata=_generation_metadata(
                    generation_mode=generation_mode,
                    retrieval_status=context.knowledge_retrieval_status,
                    model_answerability=None,
                    parse_status="not_called",
                    schema_status="not_called",
                    evidence_reference_status="not_applicable",
                    semantic_grounding_status="not_applicable",
                    fallback_reason="tool_failed",
                ),
            )
            _emit_generation_trace(
                trace_extra=generation_trace_extra,
                status="skipped",
                patch=patch,
                response_cta=None,
                response_topic=None,
                is_fallback_response=True,
                parse_status="not_called",
                generated_action_cta_detected=False,
            )
            return patch

        if (
            context.generation_mode == GenerationMode.TOOL_RESULT_RESPONSE
            and context.tool_result is None
            and _has_tool_response_text(context)
        ):
            patch = _response_patch(
                response_text=str(context.tool_response_text).strip(),
                metadata=_generation_metadata(
                    generation_mode=generation_mode,
                    retrieval_status=context.knowledge_retrieval_status,
                    model_answerability="supported",
                    parse_status="not_called",
                    schema_status="not_applicable",
                    evidence_reference_status="not_applicable",
                    semantic_grounding_status="not_applicable",
                    fallback_reason=None,
                ),
            )
            _emit_generation_trace(
                trace_extra=generation_trace_extra,
                status="skipped",
                patch=patch,
                response_cta=None,
                response_topic=None,
                is_fallback_response=False,
                parse_status="not_called",
                generated_action_cta_detected=False,
            )
            return patch

        merged_memory = _merge_dialog_state_into_user_memory(
            _prompt_user_memory(context.user_memory),
            _prompt_dialog_state(context.dialog_state),
        )
        prompt = build_response_prompt(
            decision=context.decision,
            user_input=context.user_input,
            conversation_summary=context.conversation_summary,
            history=_prompt_history(context.history),
            knowledge_chunks=context.knowledge_chunks,
            generation_mode=generation_mode,
            tool_result=(
                context.tool_result
                if context.generation_mode is GenerationMode.TOOL_RESULT_RESPONSE
                else None
            ),
            user_memory=merged_memory,
            features=_prompt_features(context.features),
            project_configuration=context.project_configuration,
            target_language=target_lang,
            conversation_context=context.conversation_context,
            recent_ticket_resolutions=context.recent_ticket_resolutions,
        )
        if generation_trace_extra is not None:
            generation_trace_extra["prompt_chars"] = len(prompt)

        try:
            selected_model = _resolve_response_model_name(state, base_model)
            raw_response_text = await _invoke_response_model(
                llm=llm,
                selected_model=selected_model,
                base_model=base_model,
                prompt=prompt,
            )
            is_fallback_response = False
            validation = _validate_structured_response(
                raw_response_text,
                context=context,
            )
            generation_attempt_count = 1
            initial_validation_failure_reason = validation.failure_reason
            repair_attempted = False
            repair_validation_failure_reason: str | None = None
            known_evidence_refs = EvidenceReferenceIndex.from_knowledge_chunks(
                context.knowledge_chunks,
                limit=DEFAULT_KB_LIMIT,
            ).known_aliases()
            if (
                validation.result is None
                and validation.failure_reason in REPAIRABLE_VALIDATION_FAILURES
            ):
                repair_attempted = True
                repair_prompt = build_structured_response_repair_prompt(
                    original_prompt=prompt,
                    invalid_output=raw_response_text,
                    validation=validation,
                    known_evidence_refs=known_evidence_refs,
                )
                raw_response_text = await _invoke_response_model(
                    llm=llm,
                    selected_model=selected_model,
                    base_model=base_model,
                    prompt=repair_prompt,
                )
                generation_attempt_count = 2
                validation = _validate_structured_response(
                    raw_response_text,
                    context=context,
                )
                repair_validation_failure_reason = validation.failure_reason
            structured_result = validation.result
            if structured_result is None:
                patch = _safe_generation_fallback(
                    generation_mode=generation_mode,
                    target_language=target_lang,
                    retrieval_status=context.knowledge_retrieval_status,
                    parse_status=validation.parse_status,
                    schema_status=validation.schema_status,
                    evidence_reference_status=validation.evidence_reference_status,
                    semantic_grounding_status="not_applicable",
                    fallback_reason="invalid_generation",
                )
                raw_metadata = patch.get("metadata")
                metadata = (
                    dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
                )
                metadata["fallback_reason"] = (
                    validation.failure_reason or "invalid_generation"
                )
                metadata["generation_attempt_count"] = generation_attempt_count
                metadata["initial_validation_failure_reason"] = (
                    initial_validation_failure_reason
                )
                metadata["repair_attempted"] = repair_attempted
                metadata["repair_validation_failure_reason"] = (
                    repair_validation_failure_reason
                )
                metadata["repair_succeeded"] = False
                patch["metadata"] = metadata
                patch["fallback_reason"] = metadata["fallback_reason"]
                _emit_generation_trace(
                    trace_extra=generation_trace_extra,
                    status="success",
                    patch=patch,
                    response_cta=None,
                    response_topic=None,
                    is_fallback_response=True,
                    parse_status="failed",
                    generated_action_cta_detected=False,
                )
                return patch

            response_text = structured_result.answer or ""
            fallback_reason: str | None = None
            output_lang = detect_language_hint(response_text)
            if (
                response_text
                and target_lang != "unknown"
                and output_lang != "unknown"
                and target_lang != output_lang
            ) or _contains_invalid_language_mix(response_text, target_lang):
                logger.warning(
                    "Response language mismatch detected; using safe fallback",
                    extra={
                        "input_lang": input_lang,
                        "target_lang": target_lang,
                        "output_lang": output_lang,
                        "decision": context.decision,
                    },
                )
                response_text = _language_mismatch_fallback(target_lang)
                is_fallback_response = True
                fallback_reason = "language_validation_failed"
                structured_result = StructuredResponseResult(
                    answerability="unsupported",
                    answer=response_text,
                    unsupported_aspects=["language_validation_failed"],
                )

            if (
                structured_result.answerability == "unsupported"
                and fallback_reason != "language_validation_failed"
            ):
                response_text = _no_confirmation_text(target_lang)
                is_fallback_response = True
                fallback_reason = "unsupported"
            elif structured_result.answerability == "conflicting_evidence":
                response_text = _conflicting_evidence_text(target_lang)
                is_fallback_response = True
                fallback_reason = "conflicting_evidence"

            response_cta: str | None = None
            response_topic: str | None = None
            (
                response_text,
                generated_action_cta_detected,
            ) = _sanitize_generated_action_cta(response_text)
            if generated_action_cta_detected and not response_text.strip():
                response_text = _invalid_generation_text(target_lang)
                is_fallback_response = True
                fallback_reason = "orphan_action_cta_removed"

            continuation_decision = _continuation_offer_decision(
                context,
                response_text=response_text,
                is_fallback_response=is_fallback_response,
            )
            if continuation_decision.should_offer:
                response_text = _with_continuation_prompt(response_text, target_lang)
                response_cta = continuation_decision.cta
                response_topic = context.topic

            metadata = _generation_metadata(
                generation_mode=generation_mode,
                retrieval_status=context.knowledge_retrieval_status,
                model_answerability=structured_result.answerability,
                supporting_entry_ids=structured_result.supporting_entry_ids,
                supporting_evidence_refs=structured_result.supporting_evidence_refs,
                unsupported_aspects=structured_result.unsupported_aspects,
                parse_status=validation.parse_status,
                schema_status=validation.schema_status,
                evidence_reference_status=validation.evidence_reference_status,
                semantic_grounding_status=_semantic_grounding_status_for(
                    structured_result
                ),
                fallback_reason=fallback_reason,
                generation_attempt_count=generation_attempt_count,
                initial_validation_failure_reason=initial_validation_failure_reason,
                repair_attempted=repair_attempted,
                repair_validation_failure_reason=repair_validation_failure_reason,
                repair_succeeded=repair_attempted and structured_result is not None,
            )
            metadata["generated_action_cta_detected"] = generated_action_cta_detected
            metadata["canonical_response_cta"] = response_cta

            patch = _response_patch(
                response_text=response_text,
                metadata=metadata,
                cta=response_cta,
                topic=response_topic,
            )
            _emit_generation_trace(
                trace_extra=generation_trace_extra,
                status="success",
                patch=patch,
                response_cta=response_cta,
                response_topic=response_topic,
                is_fallback_response=is_fallback_response,
                parse_status="valid",
                generated_action_cta_detected=generated_action_cta_detected,
            )

            logger.debug(
                "Response generated",
                extra={
                    "response_length": len(response_text),
                    "decision": context.decision,
                    "model": selected_model,
                },
            )
            return patch
        except Exception as exc:
            if _rag_debug_enabled():
                fallback_patch = _technical_failure_patch(state, exc)
                _emit_generation_trace(
                    trace_extra={
                        **(generation_trace_extra or {}),
                        "thread_id": state.get("thread_id"),
                        "project_id": state.get("project_id"),
                        "model_name": _resolve_response_model_name(state, base_model),
                        "decision": context.decision,
                        "prompt_entries": format_kb_prompt_entry_traces(
                            context.knowledge_chunks
                        ),
                        "prompt_chars": len(prompt),
                    },
                    status="failed",
                    patch=fallback_patch,
                    response_cta=None,
                    response_topic=None,
                    is_fallback_response=True,
                    parse_status="failed",
                    generated_action_cta_detected=False,
                    error_type=type(exc).__name__,
                    error_preview=_preview_text(str(exc)),
                )
            logger.exception(
                "Response generation failed",
                extra={
                    "decision": context.decision,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "technical_failure_user_choice",
                },
            )
            return _technical_failure_patch(state, exc)

    def _get_response_input_size(state: AgentState) -> int:
        context = ResponseGenerationContext.from_state(cast(RuntimeStateInput, state))
        return (
            len(context.user_input)
            + len(context.conversation_summary or "")
            + len(str(context.history))
            + len(str(context.knowledge_chunks))
            + len(str(context.user_memory or {}))
            + len(str(context.project_configuration or {}))
            + len(str(context.dialog_state or {}))
        )

    def _get_response_output_size(result: dict[str, object]) -> int:
        return len(str(result.get("response_text") or ""))

    async def response_generator_node(state: AgentState) -> dict[str, object]:
        return await log_node_execution(
            "response_generator",
            _response_generator_node_impl,
            state,
            get_input_size=_get_response_input_size,
            get_output_size=_get_response_output_size,
        )

    return response_generator_node
