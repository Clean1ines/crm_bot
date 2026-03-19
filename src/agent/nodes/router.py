"""
Router node for LangGraph pipeline with model selection and rate limit handling.

Uses ModelRegistry, RateLimitTracker, and ModelSelector to pick the best available
model based on current rate limits and task complexity. Handles 429 errors by
retrying with alternative models.
"""

import asyncio
import json
from typing import Dict, Any, Optional

from langchain_groq import ChatGroq
from pydantic import ValidationError

from src.core.config import settings
from src.core.logging import get_logger
from src.agent.state import AgentState
from src.agent.schemas import RouterOutput
from src.core.model_registry import ModelRegistry
from src.services.rate_limit_tracker import RateLimitTracker
from src.services.model_selector import ModelSelector

logger = get_logger(__name__)

# Global singletons for dependencies (lazy init)
_registry: Optional[ModelRegistry] = None
_tracker: Optional[RateLimitTracker] = None
_selector: Optional[ModelSelector] = None


def _get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


def _get_tracker() -> RateLimitTracker:
    global _tracker
    if _tracker is None:
        _tracker = RateLimitTracker()
    return _tracker


def _get_selector() -> ModelSelector:
    global _selector
    if _selector is None:
        _selector = ModelSelector(_get_registry(), _get_tracker())
    return _selector


# Router prompt (Russian, strict JSON output, few-shot examples)
ROUTER_PROMPT_TEMPLATE = """
Ты — routing LLM для клиентского бота платформы поддержки. Твоя задача — прочитать входящее сообщение пользователя и вернуть строго валидный JSON (ни строчки лишней) с ключами:
- decision: одна из ["RESPOND_KB","RESPOND_TEMPLATE","LLM_GENERATE","CALL_TOOL","ESCALATE_TO_HUMAN"]
- response: string (краткий текст для отправки пользователю, либо пустая строка)
- tool: string|null (имя инструмента для вызова, например 'crm.create_user', 'ticket.create', 'kb.search')
- tool_args: object (аргументы инструмента)
- requires_human: boolean
- confidence: number (0.00 - 1.00)

Входные переменные, доступные тебе:
- user_input: {user_input}
- client_profile: {client_profile}
- kb_results: {kb_results}
- recent_history: {recent_history}
- config: {{KB_THRESHOLD:0.5, LLM_THRESHOLD:0.70}}

Правила принятия решения:
1) Если в kb_results есть элемент с score >= config.KB_THRESHOLD → decision = "RESPOND_KB", response = kb_results[0].answer, requires_human=false, confidence = min(0.95, score).
2) Выполни cheap routing (регексы и keyword map): слова/шаблоны для delivery|price|refund|returns|integration|api. Для точных совпадений возвращай "RESPOND_TEMPLATE" с коротким объяснением и confidence 0.85+.
3) Если в user_input присутствуют слова жалобы/угрозы/refund/chargeback/публичный отзыв или sentiment/anger>=0.7 → ESCALATE_TO_HUMAN with high confidence (>=0.95).
4) Если none of the above → LLM_GENERATE: сгенерируй вежливый, полезный ответ. 
   Используй информацию из kb_results (даже если score < KB_THRESHOLD) для составления ответа. 
   Особенно если пользователь задал несколько вопросов, постарайся найти в kb_results ответы 
   на некоторые из них и включить их в ответ. Если kb_results содержат релевантные данные, 
   обязательно используй их. В конце можешь добавить опцию 'Хотите связаться с менеджером?' 
   если тема сложная или остались неотвеченные вопросы.
5) Всегда: если client_profile == null → tool = 'crm.create_user' или 'crm.collect_profile' (предпочтительно collect_profile) и в tool_args укажи telegram_id, username (если известны) и asking_fields (см. onboarding).
6) При формировании JSON-ответа убедись, что он строго валиден: все строки в двойных кавычках, специальные символы (например, кавычки внутри текста) экранированы обратным слешем. Не используй неэкранированные управляющие символы.

Few-shot примеры:

Input: "Сколько стоит доставка?"
kb_results: [{{"answer":"Доставка 300₽", "score":0.88}}]
→ Output: {{"decision": "RESPOND_KB", "response": "Доставка 300₽", "tool": null, "tool_args": {{}}, "requires_human": false, "confidence": 0.88}}

Input: "Хочу подключить нашу Postgres базу и OAuth"
client_profile exists
→ Output: {{"decision": "LLM_GENERATE", "response": "Для подключения внешних систем обычно требуется участие менеджера. Хотите, чтобы я создал запрос для менеджера?", "tool": null, "tool_args": {{}}, "requires_human": true, "confidence": 0.90}}

Input: "Что такое task? Как добавить менеджера?"
→ Output: {{"decision": "LLM_GENERATE", "response": "**Что такое task?**\nЗадача — запись в таблице tasks, содержит thread_id, user_id, title, description, priority, status (open/in_progress/done).\n\n**Как добавить менеджера?**\nВ админ-боте нажмите 'Добавить менеджера' — менеджер должен открыть manager-бот и нажать 'Присоединиться'. После этого запишите его chat_id.", "tool": null, "tool_args": {{}}, "requires_human": false, "confidence": 0.85}}

Возвращай ТОЛЬКО JSON, без пояснений.
"""


def create_router_node(
    llm: Optional[ChatGroq] = None,
    registry: Optional[ModelRegistry] = None,
    tracker: Optional[RateLimitTracker] = None,
    selector: Optional[ModelSelector] = None
):
    """
    Factory function that creates a router node with model selection and rate limit handling.

    Args:
        llm: Optional ChatGroq instance (not used, kept for compatibility).
        registry: Optional ModelRegistry instance. If None, a global singleton is used.
        tracker: Optional RateLimitTracker instance. If None, a global singleton is used.
        selector: Optional ModelSelector instance. If None, a global singleton is used.

    Returns:
        An async function that takes an AgentState dict and returns a dict
        with the router's decision and related fields.
    """
    # Use provided dependencies or fall back to global singletons
    reg = registry if registry is not None else _get_registry()
    trk = tracker if tracker is not None else _get_tracker()
    sel = selector if selector is not None else _get_selector()

    async def router_node(state: AgentState) -> Dict[str, Any]:
        """
        Analyze the state and decide the next action using an LLM.
        Selects an appropriate model based on rate limits and complexity.
        Handles 429 errors by retrying with other models.
        """
        user_input = state.get("user_input", "")
        if not user_input:
            logger.warning("router_node called with empty user_input")
            return {
                "decision": "ESCALATE_TO_HUMAN",
                "requires_human": True,
                "response_text": "Не удалось обработать запрос (пустой ввод). Передано менеджеру.",
                "confidence": 0.0
            }

        # Determine complexity (simple heuristic: longer messages or those containing certain words are complex)
        complex_needed = len(user_input) > 100 or any(word in user_input.lower() for word in ["интеграц", "подключ", "сложн", "помоги", "api", "postgres", "n8n", "google sheets"])
        model_id = await sel.get_best_model(complex_needed=complex_needed)
        logger.info("Selected model", extra={"model": model_id, "complex": complex_needed})

        # Prepare context for prompt
        conv_summary = state.get("conversation_summary") or "Нет краткого содержания."
        client_profile = state.get("client_profile") or {}
        kb_results = state.get("knowledge_chunks") or []
        kb_str = json.dumps(kb_results, ensure_ascii=False, indent=2) if kb_results else "[]"
        history = state.get("history") or []
        recent_history = history[-3:] if len(history) > 3 else history
        history_str = json.dumps(recent_history, ensure_ascii=False, indent=2) if recent_history else "[]"

        prompt = ROUTER_PROMPT_TEMPLATE.format(
            user_input=user_input,
            client_profile=json.dumps(client_profile, ensure_ascii=False, indent=2),
            kb_results=kb_str,
            recent_history=history_str
        )

        logger.debug("Calling router LLM", extra={
            "user_input_preview": user_input[:50],
            "kb_count": len(kb_results),
            "model": model_id
        })

        # Instantiate the selected model (or reuse a cached one)
        current_llm = ChatGroq(
            model=model_id,
            temperature=0.0,
            api_key=settings.GROQ_API_KEY,
        )

        # Attempt call with potential retry/fallback
        max_attempts = 3
        used_models = set()
        used_models.add(model_id)

        for attempt in range(max_attempts):
            try:
                response = await current_llm.ainvoke(prompt)
                # TODO: extract headers and update tracker when possible
                break
            except Exception as e:
                if "429" in str(e) or "rate limit" in str(e).lower():
                    logger.warning("Rate limit hit", extra={"model": model_id, "attempt": attempt})
                    # If we have more attempts, try another model
                    if attempt < max_attempts - 1:
                        # Select a different model (exclude used ones)
                        models = reg.get_models_sorted_by_priority(complex_needed)
                        for m in models:
                            if m["id"] not in used_models:
                                model_id = m["id"]
                                used_models.add(model_id)
                                current_llm = ChatGroq(
                                    model=model_id,
                                    temperature=0.0,
                                    api_key=settings.GROQ_API_KEY,
                                )
                                logger.info("Switching to alternative model", extra={"model": model_id})
                                break
                        else:
                            # No alternative model found, fallback to default
                            model_id = settings.DEFAULT_MODEL
                            current_llm = ChatGroq(
                                model=model_id,
                                temperature=0.0,
                                api_key=settings.GROQ_API_KEY,
                            )
                            logger.warning("No alternative models, falling back to default", extra={"model": model_id})
                        continue
                    else:
                        # Final attempt with default model (even if already tried)
                        logger.error("All models rate-limited, using default")
                        current_llm = ChatGroq(
                            model=settings.DEFAULT_MODEL,
                            temperature=0.0,
                            api_key=settings.GROQ_API_KEY,
                        )
                        response = await current_llm.ainvoke(prompt)
                        break
                else:
                    # Other error, raise
                    logger.exception("LLM call failed", extra={"model": model_id})
                    raise

        # Process response (same as before)
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            data = json.loads(content)
            router_output = RouterOutput.parse_obj(data)
            logger.debug("Router LLM response validated", extra={"decision": router_output.decision})
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Failed to parse or validate router LLM response", extra={"error": str(e), "raw": content})
            return {
                "decision": "ESCALATE_TO_HUMAN",
                "requires_human": True,
                "response_text": "Произошла ошибка при обработке запроса. Передано менеджеру.",
                "confidence": 0.0
            }

        result = {
            "decision": router_output.decision,
            "response_text": router_output.response,
            "tool_name": router_output.tool,
            "tool_args": router_output.tool_args,
            "requires_human": router_output.requires_human,
            "confidence": router_output.confidence
        }

        logger.info("Router decision", extra={
            "decision": result["decision"],
            "confidence": result["confidence"],
            "requires_human": result["requires_human"],
            "model_used": model_id
        })
        return result

    return router_node
