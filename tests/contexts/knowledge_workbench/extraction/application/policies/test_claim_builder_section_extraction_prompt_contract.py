from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_section_extraction_prompt_contract import (
    BuildClaimBuilderSectionExtractionPrompt,
    ClaimBuilderSectionExtractionPromptInput,
    claim_builder_section_extraction_prompt_file,
    claim_builder_section_extraction_prompt_repository_path,
)


def _contract_input() -> ClaimBuilderSectionExtractionPromptInput:
    return ClaimBuilderSectionExtractionPromptInput(
        source_unit_ref="source-unit:project-1:abc:0",
        heading_path=("Root", "Child"),
        source_unit_text="# Child\n\nSource body",
    )


def test_prompt_contract_returns_claim_observation_identity() -> None:
    contract = BuildClaimBuilderSectionExtractionPrompt().execute(_contract_input())

    assert contract.prompt_id == "faq_claim_observations"
    assert contract.prompt_version == "v1"


def test_prompt_contract_uses_context_local_prompt_file() -> None:
    prompt_file = claim_builder_section_extraction_prompt_file()

    assert prompt_file.is_file()
    assert (
        claim_builder_section_extraction_prompt_repository_path()
        == "src/contexts/knowledge_workbench/extraction/application/prompts/"
        "faq_surface_claim_observations.ru.txt"
    )
    assert (
        "src/agent/prompts"
        not in claim_builder_section_extraction_prompt_repository_path()
    )


def test_prompt_contract_returns_one_system_and_one_user_message() -> None:
    contract = BuildClaimBuilderSectionExtractionPrompt().execute(_contract_input())

    assert tuple(message["role"] for message in contract.provider_messages) == (
        "system",
        "user",
    )
    assert len(contract.provider_messages) == 2


def test_system_message_contains_prompt_identity_and_strict_json_contract() -> None:
    contract = BuildClaimBuilderSectionExtractionPrompt().execute(_contract_input())
    system_message = contract.provider_messages[0]["content"]
    normalized_system_message = " ".join(system_message.lower().split())

    assert "prompt_id: faq_claim_observations" in system_message
    assert "prompt_version: v1" in system_message
    assert "NODE: faq_claim_observations" in system_message
    assert "json" in normalized_system_message
    assert "object" in normalized_system_message
    assert "claims" in normalized_system_message
    assert (
        "any text before json" in normalized_system_message
        or "any text after json" in normalized_system_message
        or "output :=" in normalized_system_message
    )


def test_user_message_contains_source_unit_context() -> None:
    contract = BuildClaimBuilderSectionExtractionPrompt().execute(_contract_input())
    user_message = contract.provider_messages[1]["content"]

    assert "source_unit_ref: source-unit:project-1:abc:0" in user_message
    assert "heading_path: Root / Child" in user_message
    assert "# Child\n\nSource body" in user_message


def test_user_message_formats_empty_heading_path_as_root() -> None:
    contract = BuildClaimBuilderSectionExtractionPrompt().execute(
        ClaimBuilderSectionExtractionPromptInput(
            source_unit_ref="source-unit:project-1:abc:0",
            heading_path=(),
            source_unit_text="Body",
        ),
    )
    user_message = contract.provider_messages[1]["content"]

    assert "heading_path: /" in user_message
