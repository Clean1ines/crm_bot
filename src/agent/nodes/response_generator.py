"""
Response generator node for LangGraph pipeline.

Uses a stronger LLM to craft the final answer based on decision, context,
knowledge, memory, and dialog_state.
"""

from typing import Any, Dict, List, Optional

from langchain_groq import ChatGroq

from src.core.config import settings
from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState
from src.agent.router.prompt_builder import build_response_prompt

logger = get_logger(__name__)


def _merge_dialog_state_into_user_memory(
    user_memory: Optional[Dict[str, List[Dict[str, Any]]]],
    dialog_state: Optional[Dict[str, Any]],
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """
    Merge dialog_state into the memory block passed to the prompt builder.

    Args:
        user_memory: Existing grouped memory dictionary.
        dialog_state: Current dialog state snapshot.

    Returns:
        A merged memory dictionary, or the original memory if dialog_state is empty.
    """
    if not dialog_state:
        return user_memory

    merged: Dict[str, List[Dict[str, Any]]] = {}

    if user_memory:
        for memory_type, items in user_memory.items():
            if isinstance(items, list):
                normalized_items: List[Dict[str, Any]] = []
                for item in items:
                    if isinstance(item, dict):
                        normalized_items.append(dict(item))
                    else:
                        normalized_items.append({"key": "value", "value": item})
                merged[memory_type] = normalized_items
            else:
                merged[memory_type] = []

    merged["dialog_state"] = [
        {
            "key": "dialog_state",
            "value": dialog_state,
        }
    ]

    return merged


def _build_explanation(decision: str, intent: str, lifecycle: str, cta: str) -> str:
    """
    Build a human-readable explanation for the bot's response in demo mode.

    Args:
        decision: The decision made by policy engine.
        intent: The detected intent.
        lifecycle: Current lifecycle stage.
        cta: Call-to-action.

    Returns:
        A string explaining why the bot responded that way.
    """
    parts = []
    if intent:
        parts.append(f"Я распознал намерение: {intent}")
    if decision == "LLM_GENERATE":
        parts.append("Я сгенерировал ответ на основе вашего вопроса и базы знаний.")
    elif decision == "ESCALATE_TO_HUMAN":
        parts.append("Я бы передал вопрос менеджеру, так как он требует человеческого вмешательства.")
    if lifecycle:
        parts.append(f"На основе нашего разговора я определил стадию: {lifecycle}.")
    if cta and cta != "none":
        parts.append(f"Следующим шагом я предлагаю: {cta}.")

    if not parts:
        return "Ответ сгенерирован на основе вашего сообщения."
    return " ".join(parts)


def create_response_generator_node(
    llm: Optional[ChatGroq] = None,
    model_name: Optional[str] = None,
):
    """
    Factory function that creates a response generator node.

    Args:
        llm: Optional pre-configured ChatGroq instance. If None, creates one using settings.
        model_name: Optional model name (defaults to settings.GROQ_MODEL).

    Returns:
        An async function that takes an AgentState dict and returns a dict
        with updates to the state (response_text).
    """
    if llm is None:
        model = model_name or settings.GROQ_MODEL
        llm = ChatGroq(
            model=model,
            temperature=0.3,
            max_tokens=500,
            api_key=settings.GROQ_API_KEY,
        )

    async def _response_generator_node_impl(state: AgentState) -> Dict[str, Any]:
        """
        Generate the final response using LLM.

        Expected state fields:
          - decision: str
          - user_input: str
          - conversation_summary: Optional[str]
          - history: Optional[List[Dict]]
          - knowledge_chunks: Optional[List[Dict]]
          - user_memory: Optional[Dict]
          - dialog_state: Optional[Dict]
          - features: Optional[Dict]
          - demo_mode: Optional[bool]

        Returns:
            Dict with response_text and optionally metadata (explanation).
        """
        decision = state.get("decision", "LLM_GENERATE")
        if decision not in ["LLM_GENERATE", "RESPOND_KB", "RESPOND_TEMPLATE"]:
            logger.debug(
                "Skipping response generation, decision not generative",
                extra={"decision": decision},
            )
            return {}

        merged_memory = _merge_dialog_state_into_user_memory(
            state.get("user_memory"),
            state.get("dialog_state"),
        )

        # ===== DEBUG OUTPUT =====
        print("\n==== KB CHUNKS ====")
        for c in state.get("knowledge_chunks", []):
            print(c.get("content"))
        print("==== END ====\n")

        print("==== HISTORY ====")
        for msg in state.get("history", []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            print(f"- {role}: {content}")
        print("==== END ====\n")
        # =======================

        prompt = build_response_prompt(
            decision=decision,
            user_input=state.get("user_input", ""),
            conversation_summary=state.get("conversation_summary"),
            history=state.get("history"),
            knowledge_chunks=state.get("knowledge_chunks"),
            user_memory=merged_memory,
            features=state.get("features"),
        )

        try:
            response = await llm.ainvoke([("human", prompt)])
            response_text = (response.content or "").strip()

            logger.debug(
                "Response generated",
                extra={
                    "response_length": len(response_text),
                    "decision": decision,
                },
            )

            # Prepare metadata
            metadata: Dict[str, Any] = {}
            # In demo mode, add explanation
            if state.get("demo_mode"):
                explanation = _build_explanation(
                    decision=decision,
                    intent=state.get("intent", ""),
                    lifecycle=state.get("lifecycle", ""),
                    cta=state.get("cta", ""),
                )
                metadata["explanation"] = explanation
                logger.debug("Added explanation to metadata", extra={"explanation": explanation})

            return {"response_text": response_text, "metadata": metadata}

        except Exception:
            logger.exception("Response generation failed", extra={"decision": decision})
            return {
                "response_text": "Извините, произошла ошибка при формировании ответа. Попробуйте позже."
            }

    def _get_response_input_size(state: AgentState) -> int:
        """
        Estimate response generator input size.

        Args:
            state: Current agent state.

        Returns:
            Approximate input size.
        """
        return (
            len(state.get("user_input") or "") +
            len(state.get("conversation_summary") or "") +
            len(str(state.get("history") or [])) +
            len(str(state.get("knowledge_chunks") or [])) +
            len(str(state.get("user_memory") or {})) +
            len(str(state.get("dialog_state") or {}))
        )

    def _get_response_output_size(result: Dict[str, Any]) -> int:
        """
        Estimate response generator output size.

        Args:
            result: Node result.

        Returns:
            Response text length.
        """
        return len(result.get("response_text", ""))

    async def response_generator_node(state: AgentState) -> Dict[str, Any]:
        """
        Execute response generation with tracing.

        Args:
            state: Current agent state.

        Returns:
            Dictionary of state updates.
        """
        return await log_node_execution(
            "response_generator",
            _response_generator_node_impl,
            state,
            get_input_size=_get_response_input_size,
            get_output_size=_get_response_output_size,
        )

    return response_generator_node
