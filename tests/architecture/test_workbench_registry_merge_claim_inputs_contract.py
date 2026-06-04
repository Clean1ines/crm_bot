from pathlib import Path

PORT = Path("src/application/ports/faq_workbench_registry_merge_generator.py")
GENERATOR = Path("src/infrastructure/llm/faq_workbench_registry_merge_generator.py")
PROMPT = Path("src/agent/prompts/faq_surface_registry_merge.ru.txt")


def test_prompt_c_contract_is_fact_registry_canonicalization_prompt_without_old_payload() -> (
    None
):
    prompt = PROMPT.read_text(encoding="utf-8")

    assert "NODE: faq_fact_registry_canonicalization" in prompt
    assert "Prompt C" in prompt
    assert "canonical fact graph canonicalization" in prompt
    assert "fact_registry" in prompt

    stale_markers = (
        "claim_inputs",
        "candidate_fact_sets",
        "match_context",
        "known_facts",
        "relation_to_known_claim",
        "suggested_registry_action",
        "legacy",
        "легаси",
        "surface/question",
    )
    for marker in stale_markers:
        assert marker not in prompt


def test_registry_merge_generator_uses_canonicalization_unit_contract_without_old_payload_keys() -> (
    None
):
    source = GENERATOR.read_text(encoding="utf-8")

    assert "canonicalization_unit" in source
    assert "fact_registry" in source

    stale_markers = (
        '"claim_inputs": self._claim_inputs_payload(command)',
        '"candidate_fact_sets": self._candidate_fact_sets_payload(command)',
        '"match_context": command.match_context',
        "command.claim_inputs",
        "command.candidate_fact_sets",
        "command.match_context",
        "_claim_inputs_payload",
        "_candidate_fact_sets_payload",
    )
    for marker in stale_markers:
        assert marker not in source


def test_registry_merge_port_exposes_canonicalization_unit_command_without_old_section_payload() -> (
    None
):
    source = PORT.read_text(encoding="utf-8")

    assert "canonicalization_unit" in source
    assert "canonical_facts" in source

    stale_markers = (
        "section:",
        "claim_inputs:",
        "candidate_fact_sets:",
        "match_context:",
        "CandidateFactSet",
        "proposal_count",
        "proposals",
    )
    for marker in stale_markers:
        assert marker not in source
