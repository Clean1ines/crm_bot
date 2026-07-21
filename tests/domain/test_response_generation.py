import inspect

from src.domain.runtime.response_generation import (
    ResponseGenerationContext,
    ResponseGenerationResult,
)


def test_response_generation_context_from_state_normalizes_values():
    context = ResponseGenerationContext.from_state(
        {
            "user_input": "hello",
            "intent": "pricing",
            "lifecycle": "warm",
            "cta": "book_consultation",
            "topic": "product",
            "turn_relation": "new_topic",
            "decision": "LLM_GENERATE",
            "knowledge_chunks": [{"text": "chunk"}],
            "user_memory": {"stage": {"stage": "warm"}},
        }
    )

    assert context.user_input == "hello"
    assert context.intent == "pricing"
    assert context.lifecycle == "warm"
    assert context.cta == "book_consultation"
    assert context.topic == "product"
    assert context.turn_relation == "new_topic"
    assert context.decision == "LLM_GENERATE"


def test_response_generation_result_to_state_patch_matches_contract():
    signature = inspect.signature(ResponseGenerationResult)
    kwargs = {}

    if "response_text" in signature.parameters:
        kwargs["response_text"] = "hello"
    if "confidence" in signature.parameters:
        kwargs["confidence"] = 0.9
    if "metadata" in signature.parameters:
        kwargs["metadata"] = {"source": "test"}
    if "cta" in signature.parameters:
        kwargs["cta"] = "continue_explanation"
    if "topic" in signature.parameters:
        kwargs["topic"] = "product"

    result = ResponseGenerationResult(**kwargs)
    patch = result.to_state_patch()

    assert isinstance(patch, dict)
    if "response_text" in kwargs:
        assert patch["response_text"] == "hello"
    if "cta" in kwargs:
        assert patch["cta"] == "continue_explanation"
    if "topic" in kwargs:
        assert patch["topic"] == "product"
