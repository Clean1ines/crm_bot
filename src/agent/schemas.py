"""
Pydantic schemas for LangGraph agent nodes.

Defines validation models for structured outputs from LLM nodes,
ensuring type safety and error handling.
"""

from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field


class RouterOutput(BaseModel):
    """
    Structured output from the router LLM node.

    The router analyzes the user input, conversation context, and knowledge base results,
    and decides the next action: respond from KB, respond with template, generate LLM response,
    call a tool, or escalate to human.

    Attributes:
        decision: The action to take.
        response: Short text response to send to the user (may be empty).
        tool: Name of the tool to call (if decision is CALL_TOOL).
        tool_args: Arguments for the tool.
        requires_human: Whether human intervention is required.
        confidence: Confidence score of the decision (0.0-1.0).
    """
    decision: Literal[
        "RESPOND_KB",
        "RESPOND_TEMPLATE",
        "LLM_GENERATE",
        "CALL_TOOL",
        "ESCALATE_TO_HUMAN"
    ] = Field(..., description="Decision made by the router")
    response: str = Field(default="", description="Response text to send to user")
    tool: Optional[str] = Field(None, description="Tool name if decision is CALL_TOOL")
    tool_args: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")
    requires_human: bool = Field(False, description="Whether human intervention is needed")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the decision")


class IntentOutput(BaseModel):
    """
    Structured output from the intent extraction LLM node.

    Extracts intent, call-to-action, topic, emotion, and repeat flag.

    Attributes:
        intent: Primary user intent (pricing, support, sales, feedback, other).
        cta: Suggested call-to-action (request_demo, call_manager, book_consultation, none).
        features: Dictionary of mentioned features with interest level (0-1).
        topic: Refined business topic (pricing, product, integration, support, feedback, other, handoff, angry).
        cta_hint: Free-text hint about what CTA to use (optional).
        emotion: Detected user emotion (neutral, positive, negative, angry).
        is_repeat_like: Whether the user is repeating themselves.
    """
    intent: Literal[
        "pricing", "support", "sales", "feedback", "other"
    ] = Field(..., description="Primary intent of the user message")
    cta: Literal[
        "request_demo", "call_manager", "book_consultation", "none"
    ] = Field(..., description="Suggested call-to-action")
    features: Dict[str, float] = Field(
        default_factory=dict,
        description="Features mentioned with interest score (0-1)"
    )
    topic: Literal[
        "pricing", "product", "integration", "support", "feedback", "other", "handoff", "angry"
    ] = Field(default="other", description="Refined business topic")
    cta_hint: Optional[str] = Field(None, description="Free-text hint about CTA")
    emotion: Literal["neutral", "positive", "negative", "angry"] = Field(
        default="neutral", description="Detected user emotion"
    )
    is_repeat_like: bool = Field(
        default=False, description="Whether the user is repeating themselves"
    )
