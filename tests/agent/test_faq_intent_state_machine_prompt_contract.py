from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "src/agent/prompts"

PROMPT_FILES = (
    "faq_surface_local_discovery.ru.txt",
    "faq_surface_local_relations.ru.txt",
    "faq_surface_answer_synthesis_v2.ru.txt",
    "faq_surface_question_ownership_v2.ru.txt",
    "faq_surface_global_relation_judge.ru.txt",
    "faq_surface_question_reassignment.ru.txt",
)


def _read(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def test_all_faq_prompts_share_state_machine_taxonomy() -> None:
    for name in PROMPT_FILES:
        source = _read(name)
        assert "FAQ_INTENT_STATE_MACHINE_CONTRACT_V1" in source
        assert "INPUT_JSON.compilation_context" in source
        assert "SAME_INTENT_ALIAS" in source
        assert "DUPLICATE" in source
        assert "SHORT_LONG_VARIANT" in source
        assert "PARENT_CHILD" in source
        assert "SIBLING_SEPARATE" in source


def test_stage_specific_prompt_rules_are_present() -> None:
    assert "DISCOVERY_STAGE_STATE_RULES_V1" in _read(
        "faq_surface_local_discovery.ru.txt"
    )
    assert "RELATION_STAGE_STATE_RULES_V1" in _read(
        "faq_surface_local_relations.ru.txt"
    )
    assert "ANSWER_STAGE_STATE_RULES_V1" in _read(
        "faq_surface_answer_synthesis_v2.ru.txt"
    )
    assert "OWNERSHIP_STAGE_STATE_RULES_V1" in _read(
        "faq_surface_question_ownership_v2.ru.txt"
    )
    assert "GLOBAL_JUDGE_STATE_RULES_V1" in _read(
        "faq_surface_global_relation_judge.ru.txt"
    )
    assert "REASSIGNMENT_STAGE_STATE_RULES_V1" in _read(
        "faq_surface_question_reassignment.ru.txt"
    )


def test_prompt_contract_requires_universal_metadata_without_domain_hardcode() -> None:
    combined = "\n".join(_read(name) for name in PROMPT_FILES)

    assert "customer_intent" in combined
    assert "factual_answer_core" in combined
    assert "alias_questions" in combined
    assert "intent_taxonomy" in combined
    assert "product_formula" not in combined
    assert "product_short_description" not in combined
    assert "Мастерская знаний для AI-ассистентов бизнеса" not in combined
