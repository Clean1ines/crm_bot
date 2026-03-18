"""
Router node for LangGraph pipeline.

Uses an LLM to analyze the user input, conversation context, and knowledge base results,
and decides the next action: respond directly, call a tool, or escalate to human.
"""

import json
from typing import Dict, Any, Optional

from langchain_groq import ChatGroq

from src.core.config import settings
from src.core.logging import get_logger
from src.agent.state import AgentState

logger = get_logger(__name__)

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
- config: {{KB_THRESHOLD:0.78, LLM_THRESHOLD:0.70}}

Правила принятия решения:
1) Если в kb_results есть элемент с score >= config.KB_THRESHOLD → decision = "RESPOND_KB", response = kb_results[0].answer, requires_human=false, confidence = min(0.95, score).
2) Выполни cheap routing (регексы и keyword map): слова/шаблоны для delivery|price|refund|returns|integration|api. Для точных совпадений возвращай "RESPOND_TEMPLATE" с коротким объяснением и confidence 0.85+.
3) Если user явно просит подключить внешние системы/предоставить доступ/интеграцию → CALL_TOOL = "ticket.create" (см. tool_args ниже), response — краткое подтверждение, requires_human=true, confidence 0.9.
4) Если в user_input присутствуют слова жалобы/угрозы/refund/chargeback/публичный отзыв или sentiment/anger>=0.7 → ESCALATE_TO_HUMAN with high confidence (>=0.95).
5) Если none of the above → LLM_GENERATE: сгенерируй вежливый, полезный ответ (<=350 chars). В конце включи краткую опцию: 'Хотите связаться с менеджером?' если тема может потребовать эскалации.
6) Всегда: если client_profile == null → tool = 'crm.create_user' или 'crm.collect_profile' (предпочтительно collect_profile) и в tool_args укажи telegram_id, username (если известны) и asking_fields (см. onboarding).
7) Для CALL_TOOL 'ticket.create' — формируй tool_args: {{project_id, thread_id, user_id, title, description, priority}} (description — include user_input + top 3 kb_results + recent_history summary).

Few-shot примеры:

Input: "Сколько стоит доставка?"
kb_results: [{{"answer":"Доставка 300₽", "score":0.88}}]
→ Output: {{"decision": "RESPOND_KB", "response": "Доставка 300₽", "tool": null, "tool_args": {{}}, "requires_human": false, "confidence": 0.88}}

Input: "Хочу подключить нашу Postgres базу и OAuth"
client_profile exists
→ Output: {{"decision": "CALL_TOOL", "response": "Да — на фронтенде вы можете добавить кастомный endpoint и маппинг полей. Для полной интеграции мы создадим тикет менеджеру и согласуем доступы.", "tool": "ticket.create", "tool_args": {{"title": "Request: custom DB+API integration", "description": "User requests Postgres + internal REST API + OAuth. Please contact to schedule dev work.", "priority": "high"}}, "requires_human": true, "confidence": 0.90}}

Возвращай ТОЛЬКО JSON, без пояснений.
"""


def create_router_node(llm: Optional[ChatGroq] = None):
    """
    Factory function that creates a router node with a configured LLM.

    Args:
        llm: Optional ChatGroq instance. If not provided, creates a default one
             using settings.GROQ_MODEL and settings.GROQ_API_KEY.

    Returns:
        An async function that takes an AgentState dict and returns a dict
        with the router's decision and related fields.
    """
    if llm is None:
        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            temperature=0.0,  # low temperature for consistent JSON
            api_key=settings.GROQ_API_KEY,
        )

    async def router_node(state: AgentState) -> Dict[str, Any]:
        """
        Analyze the state and decide the next action using an LLM.

        Expected state fields:
          - user_input: str
          - conversation_summary: str (optional)
          - client_profile: dict (optional)
          - knowledge_chunks: list of dicts with 'answer' and 'score' (optional)
          - history: list of recent messages (optional)

        Returns a dict with updates to the state:
          - decision: str
          - response_text: str (optional)
          - tool_name: str (optional)
          - tool_args: dict (optional)
          - requires_human: bool
          - confidence: float
        """
        user_input = state.get("user_input", "")
        if not user_input:
            logger.warning("router_node called with empty user_input")
            return {
                "decision": "ESCALATE",
                "requires_human": True,
                "response_text": "Не удалось обработать запрос (пустой ввод). Передано менеджеру.",
                "confidence": 0.0
            }

        # Prepare context for prompt
        conv_summary = state.get("conversation_summary") or "Нет краткого содержания."
        client_profile = state.get("client_profile") or {}
        kb_results = state.get("knowledge_chunks") or []
        # Format kb_results as a string for prompt
        kb_str = json.dumps(kb_results, ensure_ascii=False, indent=2) if kb_results else "[]"
        # Format recent history (just as simple list)
        history = state.get("history") or []
        # We'll pass a trimmed version, maybe last 3 messages
        recent_history = history[-3:] if len(history) > 3 else history
        history_str = json.dumps(recent_history, ensure_ascii=False, indent=2) if recent_history else "[]"

        # Fill prompt template
        prompt = ROUTER_PROMPT_TEMPLATE.format(
            user_input=user_input,
            client_profile=json.dumps(client_profile, ensure_ascii=False, indent=2),
            kb_results=kb_str,
            recent_history=history_str
        )

        logger.debug("Calling router LLM", extra={
            "user_input_preview": user_input[:50],
            "kb_count": len(kb_results)
        })

        try:
            response = await llm.ainvoke(prompt)
            content = response.content.strip()
            # Extract JSON from response (it might be wrapped in markdown)
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            data = json.loads(content)
            logger.debug("Router LLM response parsed", extra={"decision": data.get("decision")})
        except Exception as e:
            logger.error("Failed to parse router LLM response", extra={"error": str(e), "raw": content if 'content' in locals() else 'N/A'})
            # Fallback: escalate to human
            return {
                "decision": "ESCALATE",
                "requires_human": True,
                "response_text": "Произошла ошибка при обработке запроса. Передано менеджеру.",
                "confidence": 0.0
            }

        # Validate required fields
        required_keys = {"decision", "response", "tool", "tool_args", "requires_human", "confidence"}
        if not all(k in data for k in required_keys):
            logger.warning("Router LLM response missing required keys", extra={"keys": data.keys()})
            return {
                "decision": "ESCALATE",
                "requires_human": True,
                "response_text": "Ошибка в формате ответа. Передано менеджеру.",
                "confidence": 0.0
            }

        # Map decision to expected values in state (RESPOND_KB, RESPOND_TEMPLATE, LLM_GENERATE, CALL_TOOL, ESCALATE_TO_HUMAN)
        # We'll keep as is, but convert ESCALATE_TO_HUMAN to ESCALATE for consistency with graph.
        decision = data["decision"]
        if decision == "ESCALATE_TO_HUMAN":
            decision = "ESCALATE"
        elif decision == "CALL_TOOL":
            decision = "TOOL"  # graph expects TOOL, but we can map later
        # For now we return original decision, and the graph will map using conditional edges.

        result = {
            "decision": data["decision"],
            "response_text": data.get("response", ""),
            "tool_name": data.get("tool"),
            "tool_args": data.get("tool_args", {}),
            "requires_human": data.get("requires_human", False),
            "confidence": data.get("confidence", 0.0)
        }

        logger.info("Router decision", extra={
            "decision": result["decision"],
            "confidence": result["confidence"],
            "requires_human": result["requires_human"]
        })
        return result

    return router_node
