"""
Functions for parsing and validating the model's JSON response,
and building fallback answers from KB results.
"""

import json
import re
from typing import Any, Dict, List, Optional, Sequence

from pydantic import ValidationError

from src.agent.schemas import RouterOutput
from src.core.logging import get_logger
from src.agent.router.utils import truncate_text, extract_kb_text, count_question_signals

logger = get_logger(__name__)


def clean_response_content(content: str) -> str:
    """
    Clean model response from markdown code fences or wrapper text.

    Args:
        content: Raw model output.

    Returns:
        Clean JSON string candidate.
    """
    cleaned = (content or "").strip()

    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    else:
        object_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if object_match:
            cleaned = object_match.group(0).strip()

    return cleaned


def validate_router_output(data: Dict[str, Any]) -> RouterOutput:
    """
    Validate parsed router JSON with the project's RouterOutput schema.

    Args:
        data: Parsed JSON dictionary.

    Returns:
        Validated RouterOutput object.
    """
    if hasattr(RouterOutput, "model_validate"):
        return RouterOutput.model_validate(data)  # type: ignore[attr-defined]
    return RouterOutput.parse_obj(data)  # type: ignore[attr-defined]


def parse_router_output(content: str) -> RouterOutput:
    """
    Parse and validate router output from the model.

    Args:
        content: Raw model text output.

    Returns:
        Validated RouterOutput object.

    Raises:
        JSONDecodeError: If the content is not valid JSON.
        ValidationError: If the JSON does not match RouterOutput schema.
    """
    cleaned = clean_response_content(content)
    data = json.loads(cleaned)
    return validate_router_output(data)


def build_fallback_response_from_kb(
    *,
    kb_results: Sequence[Any],
    user_input: str,
) -> str:
    """
    Build a deterministic fallback answer from KB evidence.

    Used only when the model output cannot be parsed or the generation fails.

    Args:
        kb_results: KB evidence.
        user_input: Original user message.

    Returns:
        Human-readable fallback answer.
    """
    items: List[str] = []

    for item in kb_results[:3]:
        text = extract_kb_text(item)
        if text:
            items.append(f"- {truncate_text(text, 320)}")

    if not items:
        return (
            "Сейчас я не смог сформировать корректный ответ. "
            "Я передал запрос менеджеру."
        )

    intro = "Нашёл релевантные сведения:\n"
    outro = (
        "\n\nЕсли хочешь, я могу уточнить вопрос и сузить ответ под твой кейс."
    )

    # If the user asked multiple questions, keep the fallback point-by-point.
    if count_question_signals(user_input) >= 2:
        intro = "Нашёл несколько релевантных фрагментов и собрал краткий ответ:\n"

    return intro + "\n".join(items) + outro
