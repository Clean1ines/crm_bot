from __future__ import annotations

from src.agent.router import prompt_builder


def test_format_commercial_context_formats_answerable_price_fact() -> None:
    text = prompt_builder.format_commercial_context(
        {
            "decision": "answerable",
            "facts": [
                {
                    "item_name": "Pro",
                    "value_kind": "exact",
                    "amount": {"amount": "2490", "currency": "RUB"},
                    "unit": "month",
                    "variant": {"period": "monthly"},
                    "source_refs": [{"quote": "Pro — 2490 ₽/мес."}],
                }
            ],
        }
    )

    assert "STRUCTURED COMMERCIAL CONTEXT" in text
    assert "decision=answerable" in text
    assert "item=Pro" in text
    assert "price=2490 RUB" in text
    assert "source=Pro — 2490 ₽/мес." in text


def test_format_commercial_context_ignores_not_found_or_empty_context() -> None:
    assert prompt_builder.format_commercial_context(None) == ""
    assert prompt_builder.format_commercial_context({"decision": "not_found"}) == ""


def test_build_response_prompt_includes_commercial_context_before_generic_kb() -> None:
    original_template = prompt_builder._response_prompt_template
    original_interpretation = prompt_builder._interpretation_block
    try:
        prompt_builder._response_prompt_template = (
            "knowledge={knowledge_block}\nuser={user_input}"
        )
        prompt_builder._interpretation_block = ""

        prompt = prompt_builder.build_response_prompt(
            decision="LLM_GENERATE",
            user_input="Сколько стоит Pro?",
            knowledge_chunks=[{"content": "generic kb", "score": 0.8}],
            commercial_context={
                "decision": "answerable",
                "facts": [
                    {
                        "item_name": "Pro",
                        "value_kind": "exact",
                        "amount": {"amount": "2490", "currency": "RUB"},
                        "unit": "month",
                        "source_refs": [{"quote": "Pro — 2490 ₽/мес."}],
                    }
                ],
            },
        )
    finally:
        prompt_builder._response_prompt_template = original_template
        prompt_builder._interpretation_block = original_interpretation

    assert "STRUCTURED COMMERCIAL CONTEXT" in prompt
    assert "GENERIC KNOWLEDGE BASE" in prompt
    assert prompt.index("STRUCTURED COMMERCIAL CONTEXT") < prompt.index(
        "GENERIC KNOWLEDGE BASE"
    )
