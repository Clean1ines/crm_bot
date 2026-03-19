"""
Router node for LangGraph pipeline with model selection, rate limit handling,
and hybrid KB + reasoning synthesis.

This module selects the best available Groq model, builds a strict JSON prompt,
and routes the state into one of the supported decisions:
RESPOND_KB, RESPOND_TEMPLATE, LLM_GENERATE, CALL_TOOL, ESCALATE_TO_HUMAN.

The router is intentionally synthesis-first:
- KB results are treated as evidence, not raw copy-paste.
- Multi-question inputs are answered point-by-point.
- Low-confidence or sensitive requests still escalate.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from langchain_groq import ChatGroq
from pydantic import ValidationError

from src.agent.state import AgentState
from src.agent.schemas import RouterOutput
from src.core.config import settings
from src.core.logging import get_logger, log_node_execution
from src.core.model_registry import ModelRegistry
from src.services.model_selector import ModelSelector
from src.services.rate_limit_tracker import RateLimitTracker

from src.agent.router.utils import (
    truncate_text,
    safe_json_dumps,
    count_question_signals,
    has_sensitive_or_urgent_intent,
    has_complex_intent,
    extract_model_id,
)
from src.agent.router.prompt_builder import (
    format_kb_results,
    format_history,
    infer_routing_mode,
    build_router_prompt,
    DEFAULT_KB_THRESHOLD,
    DEFAULT_LLM_THRESHOLD,
    DEFAULT_KB_LIMIT,
)
from src.agent.router.output_parser import (
    parse_router_output,
    build_fallback_response_from_kb,
)

logger = get_logger(__name__)

# Global singletons for dependencies (lazy init)
_registry: Optional[ModelRegistry] = None
_tracker: Optional[RateLimitTracker] = None
_selector: Optional[ModelSelector] = None

# Timeout and retry settings from config
ROUTER_TIMEOUT_SECONDS = float(getattr(settings, "ROUTER_TIMEOUT_SECONDS", 30.0))
ROUTER_MAX_ATTEMPTS = int(getattr(settings, "ROUTER_MAX_ATTEMPTS", 3))


def _get_registry() -> ModelRegistry:
    """Return the lazily initialized global ModelRegistry."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


def _get_tracker() -> RateLimitTracker:
    """Return the lazily initialized global RateLimitTracker."""
    global _tracker
    if _tracker is None:
        _tracker = RateLimitTracker()
    return _tracker


def _get_selector() -> ModelSelector:
    """Return the lazily initialized global ModelSelector."""
    global _selector
    if _selector is None:
        _selector = ModelSelector(_get_registry(), _get_tracker())
    return _selector


def _build_llm_client(model_id: str, override_llm: Optional[ChatGroq] = None) -> ChatGroq:
    """Build a ChatGroq client for the selected model."""
    if override_llm is not None:
        return override_llm
    return ChatGroq(
        model=model_id,
        temperature=0.0,
        api_key=settings.GROQ_API_KEY,
    )


def create_router_node(
    llm: Optional[ChatGroq] = None,
    registry: Optional[ModelRegistry] = None,
    tracker: Optional[RateLimitTracker] = None,
    selector: Optional[ModelSelector] = None,
):
    """
    Factory function that creates a router node with model selection and rate limit handling.

    The node now behaves as a hybrid KB + reasoning router:
    - the prompt encourages synthesis across multiple KB snippets;
    - KB hits are not treated as raw copy-paste answers;
    - multi-question requests are answered point-by-point;
    - routing decisions remain JSON-only and schema-validated.

    Args:
        llm: Optional ChatGroq instance (kept for compatibility and tests).
        registry: Optional ModelRegistry instance. If None, a global singleton is used.
        tracker: Optional RateLimitTracker instance. If None, a global singleton is used.
        selector: Optional ModelSelector instance. If None, a selector is created from registry/tracker.

    Returns:
        An async function that takes an AgentState dict and returns a dict
        with the router's decision and related fields.
    """
    reg = registry if registry is not None else _get_registry()
    trk = tracker if tracker is not None else _get_tracker()
    sel = selector if selector is not None else ModelSelector(reg, trk)

    async def _router_node_impl(state: AgentState) -> Dict[str, Any]:
        """
        Analyze the current state and decide the next action with a Groq model.

        This node:
        - prepares compact KB and history context;
        - selects the best model based on complexity and rate limits;
        - retries with alternative models on 429;
        - validates strict JSON output;
        - falls back to deterministic KB synthesis if the model output is invalid.

        Args:
            state: Current agent state.

        Returns:
            Dictionary with normalized router output fields.
        """
        user_input = (state.get("user_input") or "").strip()
        project_id = state.get("project_id")
        thread_id = state.get("thread_id")
        conversation_summary = truncate_text(
            str(state.get("conversation_summary") or "Нет краткого содержания."),
            600,
        )
        client_profile = state.get("client_profile")
        history = state.get("history") or []
        raw_kb_results = state.get("knowledge_chunks") or state.get("kb_results") or []

        if not user_input:
            logger.warning(
                "router_node called with empty user_input",
                project_id=project_id,
                thread_id=thread_id,
            )
            return {
                "decision": "ESCALATE_TO_HUMAN",
                "requires_human": True,
                "response_text": "Не удалось обработать запрос (пустой ввод). Передано менеджеру.",
                "confidence": 0.0,
                "tool_name": None,
                "tool_args": {},
            }

        kb_context, top_score, kb_count = format_kb_results(raw_kb_results)
        question_count = count_question_signals(user_input)
        routing_mode = infer_routing_mode(
            kb_count=kb_count,
            top_score=top_score,
            question_count=question_count,
            kb_threshold=DEFAULT_KB_THRESHOLD,
        )

        complex_needed = (
            routing_mode in {"HYBRID_SYNTHESIS", "KB_AUGMENTED_LLM", "LLM_ONLY"}
            or len(user_input) > 120
            or has_complex_intent(user_input)
            or has_sensitive_or_urgent_intent(user_input)
        )

        model_id = await sel.get_best_model(complex_needed=complex_needed)
        logger.info(
            "Selected model for router",
            model=model_id,
            complex_needed=complex_needed,
            routing_mode=routing_mode,
            project_id=project_id,
            thread_id=thread_id,
            kb_count=kb_count,
            top_score=round(top_score, 3),
        )

        prompt = build_router_prompt(
            user_input=user_input,
            client_profile=safe_json_dumps(client_profile if client_profile is not None else None),
            conversation_summary=conversation_summary,
            recent_history=format_history(history, limit=5),
            kb_context=kb_context,
            kb_top_score=top_score,
            kb_count=kb_count,
            question_count=question_count,
            routing_mode=routing_mode,
            kb_threshold=DEFAULT_KB_THRESHOLD,
            llm_threshold=DEFAULT_LLM_THRESHOLD,
        )

        logger.debug(
            "Router context prepared",
            project_id=project_id,
            thread_id=thread_id,
            user_input_preview=truncate_text(user_input, 120),
            kb_count=kb_count,
            question_count=question_count,
            routing_mode=routing_mode,
        )

        if llm is not None:
            logger.debug(
                "Using injected LLM instance for router first attempt",
                project_id=project_id,
                thread_id=thread_id,
            )

        current_llm = _build_llm_client(model_id, override_llm=llm)
        used_models = {model_id}
        response = None
        last_error: Optional[Exception] = None

        for attempt in range(ROUTER_MAX_ATTEMPTS):
            try:
                logger.debug(
                    "Calling router LLM",
                    attempt=attempt + 1,
                    model=model_id,
                    project_id=project_id,
                    thread_id=thread_id,
                )
                response = await asyncio.wait_for(
                    current_llm.ainvoke(prompt),
                    timeout=ROUTER_TIMEOUT_SECONDS,
                )
                last_error = None
                break
            except asyncio.TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "Router LLM timed out",
                    attempt=attempt + 1,
                    model=model_id,
                    timeout_seconds=ROUTER_TIMEOUT_SECONDS,
                    project_id=project_id,
                    thread_id=thread_id,
                )
            except Exception as exc:
                last_error = exc
                error_message = str(exc).lower()

                if "429" in error_message or "rate limit" in error_message:
                    logger.warning(
                        "Router model hit rate limit",
                        attempt=attempt + 1,
                        model=model_id,
                        project_id=project_id,
                        thread_id=thread_id,
                    )

                    if attempt < ROUTER_MAX_ATTEMPTS - 1:
                        candidate_models = reg.get_models_sorted_by_priority(complex_needed)
                        switched = False

                        for candidate in candidate_models:
                            candidate_model_id = extract_model_id(candidate)
                            if candidate_model_id and candidate_model_id not in used_models:
                                model_id = candidate_model_id
                                used_models.add(candidate_model_id)
                                current_llm = _build_llm_client(model_id)
                                switched = True
                                logger.info(
                                    "Switching to alternative router model",
                                    model=model_id,
                                    attempt=attempt + 1,
                                    project_id=project_id,
                                    thread_id=thread_id,
                                )
                                break

                        if not switched:
                            fallback_model = str(
                                getattr(settings, "DEFAULT_MODEL", model_id)
                            )
                            if fallback_model not in used_models:
                                model_id = fallback_model
                                used_models.add(fallback_model)
                                current_llm = _build_llm_client(model_id)
                                logger.warning(
                                    "Falling back to default router model",
                                    model=model_id,
                                    project_id=project_id,
                                    thread_id=thread_id,
                                )
                            else:
                                logger.warning(
                                    "No unused alternative model found for router retry",
                                    project_id=project_id,
                                    thread_id=thread_id,
                                )
                        continue

                    logger.error(
                        "All router attempts were rate-limited",
                        project_id=project_id,
                        thread_id=thread_id,
                    )
                    break

                logger.exception(
                    "Router LLM call failed",
                    model=model_id,
                    project_id=project_id,
                    thread_id=thread_id,
                )
                raise

        if response is None:
            fallback_text = build_fallback_response_from_kb(
                kb_results=raw_kb_results,
                user_input=user_input,
            )
            if raw_kb_results:
                logger.warning(
                    "Router fell back to deterministic KB synthesis",
                    project_id=project_id,
                    thread_id=thread_id,
                    kb_count=kb_count,
                )
                return {
                    "decision": "RESPOND_KB",
                    "response_text": fallback_text,
                    "tool_name": None,
                    "tool_args": {},
                    "requires_human": False,
                    "confidence": max(0.55, min(0.85, top_score or 0.55)),
                }

            logger.error(
                "Router could not obtain an LLM response and has no KB fallback",
                project_id=project_id,
                thread_id=thread_id,
                last_error=str(last_error) if last_error else None,
            )
            return {
                "decision": "ESCALATE_TO_HUMAN",
                "requires_human": True,
                "response_text": "Произошла техническая ошибка при обработке запроса. Передано менеджеру.",
                "confidence": 0.0,
                "tool_name": None,
                "tool_args": {},
            }

        raw_content = getattr(response, "content", "") or ""
        try:
            router_output = parse_router_output(raw_content)
            logger.debug(
                "Router output validated",
                decision=router_output.decision,
                project_id=project_id,
                thread_id=thread_id,
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error(
                "Failed to parse or validate router output",
                error=str(exc),
                raw_preview=truncate_text(raw_content, 500),
                project_id=project_id,
                thread_id=thread_id,
            )

            fallback_text = build_fallback_response_from_kb(
                kb_results=raw_kb_results,
                user_input=user_input,
            )

            if raw_kb_results:
                return {
                    "decision": "RESPOND_KB",
                    "response_text": fallback_text,
                    "tool_name": None,
                    "tool_args": {},
                    "requires_human": False,
                    "confidence": max(0.5, min(0.8, top_score or 0.5)),
                }

            return {
                "decision": "ESCALATE_TO_HUMAN",
                "requires_human": True,
                "response_text": "Произошла ошибка при обработке запроса. Передано менеджеру.",
                "confidence": 0.0,
                "tool_name": None,
                "tool_args": {},
            }

        decision = getattr(router_output, "decision", None) or "LLM_GENERATE"
        response_text = (getattr(router_output, "response", "") or "").strip()
        tool_name = getattr(router_output, "tool", None)
        tool_args = getattr(router_output, "tool_args", None) or {}
        requires_human = bool(
            getattr(router_output, "requires_human", False)
            or decision == "ESCALATE_TO_HUMAN"
        )
        confidence = float(getattr(router_output, "confidence", 0.0) or 0.0)

        # Normalization rules keep the router resilient and preserve a helpful response.
        if decision == "CALL_TOOL" and not tool_name:
            logger.warning(
                "Router requested CALL_TOOL without tool name; escalating",
                project_id=project_id,
                thread_id=thread_id,
            )
            return {
                "decision": "ESCALATE_TO_HUMAN",
                "requires_human": True,
                "response_text": "Запрос требует дополнительной обработки. Я передал его менеджеру.",
                "confidence": max(confidence, 0.5),
                "tool_name": None,
                "tool_args": {},
            }

        if not response_text and raw_kb_results:
            response_text = build_fallback_response_from_kb(
                kb_results=raw_kb_results,
                user_input=user_input,
            )

        if not response_text and decision != "ESCALATE_TO_HUMAN":
            response_text = (
                "Сейчас не удалось сформировать точный ответ. "
                "Если хочешь, я передам вопрос менеджеру."
            )

        if decision == "ESCALATE_TO_HUMAN" and not response_text:
            response_text = "Я передал запрос менеджеру."

        result = {
            "decision": decision,
            "response_text": response_text,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "requires_human": requires_human,
            "confidence": confidence,
        }

        logger.info(
            "Router decision finalized",
            decision=result["decision"],
            confidence=result["confidence"],
            requires_human=result["requires_human"],
            model_used=model_id,
            project_id=project_id,
            thread_id=thread_id,
            kb_count=kb_count,
            top_score=round(top_score, 3),
            routing_mode=routing_mode,
        )
        return result

    def _get_router_input_size(state: AgentState) -> int:
        return len(state.get("user_input", "")) + len(state.get("knowledge_chunks", []))

    def _get_router_output_size(result: Dict[str, Any]) -> int:
        return len(result.get("response_text", ""))

    async def router_node(state: AgentState) -> Dict[str, Any]:
        return await log_node_execution(
            "router",
            _router_node_impl,
            state,
            get_input_size=_get_router_input_size,
            get_output_size=_get_router_output_size
        )

    return router_node
