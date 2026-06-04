from __future__ import annotations

import inspect
from dataclasses import fields, is_dataclass
from pathlib import Path

from src.application.ports.faq_workbench_registry_merge_generator import (
    FaqWorkbenchRegistryMergeGenerationCommand,
    FaqWorkbenchRegistryMergeGenerationError,
    FaqWorkbenchRegistryMergeGenerationResult,
    FaqWorkbenchRegistryMergeGeneratorPort,
)


PORT_SOURCE = Path("src/application/ports/faq_workbench_registry_merge_generator.py")


def _field_names(cls: type) -> tuple[str, ...]:
    assert is_dataclass(cls)
    return tuple(field.name for field in fields(cls))


def test_registry_merge_command_is_actual_document_level_prompt_c_contract() -> None:
    assert _field_names(FaqWorkbenchRegistryMergeGenerationCommand) == (
        "node_run_id",
        "canonicalization_unit",
        "registry",
        "canonical_facts",
        "registry_snapshot_payload",
        "relevant_registry_state",
        "prompt_version",
    )

    source = PORT_SOURCE.read_text(encoding="utf-8")
    command_source = source.split(
        "class FaqWorkbenchRegistryMergeGenerationCommand",
        1,
    )[1].split(
        "class FaqWorkbenchRegistryMergeGenerationResult",
        1,
    )[0]

    assert "Prompt C no longer receives one section" in command_source
    assert "Prompt C command requires canonicalization unit members" in command_source
    assert "Prompt C registry_snapshot_payload must be object" in command_source
    assert "Prompt C relevant_registry_state must be object" in command_source

    stale_names = {
        "project_id",
        "document_id",
        "processing_run_id",
        "section",
        "claim_inputs",
        "candidate_fact_sets",
        "match_context",
    }
    assert set(_field_names(FaqWorkbenchRegistryMergeGenerationCommand)).isdisjoint(
        stale_names
    )


def test_registry_merge_result_is_actual_fact_registry_artifact_contract() -> None:
    assert _field_names(FaqWorkbenchRegistryMergeGenerationResult) == (
        "fact_registry",
        "registry_update_summary",
        "invocation",
        "raw_output_artifact_payload",
        "parsed_output_artifact_payload",
        "warnings",
        "metrics",
    )

    result_attrs = set(dir(FaqWorkbenchRegistryMergeGenerationResult))
    assert "canonical_fact_count" in result_attrs
    assert "fact_relation_count" in result_attrs

    stale_names = {
        "node_run_id",
        "raw_text",
        "parsed_output",
        "token_usage",
        "model_name",
        "proposal_count",
        "proposals",
    }
    assert set(_field_names(FaqWorkbenchRegistryMergeGenerationResult)).isdisjoint(
        stale_names
    )


def test_registry_merge_error_wraps_llm_invocation_result_not_freeform_message_context() -> (
    None
):
    signature = inspect.signature(FaqWorkbenchRegistryMergeGenerationError)

    assert tuple(signature.parameters) == ("result",)

    source = PORT_SOURCE.read_text(encoding="utf-8")
    error_source = source.split(
        "class FaqWorkbenchRegistryMergeGenerationError",
        1,
    )[1].split(
        "class FaqWorkbenchRegistryMergeGeneratorPort",
        1,
    )[0]

    assert (
        "def __init__(self, result: LlmJsonInvocationResult) -> None:" in error_source
    )
    assert "self.result = result" in error_source
    assert "self.status = result.status" in error_source
    assert "self.error_kind = error_kind" in error_source
    assert "self.user_message = user_message" in error_source
    assert "self.internal_message = internal_message" in error_source
    assert "self.cooldown_seconds =" in error_source
    assert "Prompt C invocation failed" in error_source

    stale_markers = (
        "message: str",
        "raw_text: str",
        "context: dict",
        "self.message",
        "self.raw_text",
        "self.context",
    )
    for marker in stale_markers:
        assert marker not in error_source


def test_registry_merge_port_declares_async_generation_method() -> None:
    signature = inspect.signature(
        FaqWorkbenchRegistryMergeGeneratorPort.generate_registry_updates
    )

    assert tuple(signature.parameters) == ("self", "command")
    assert hasattr(FaqWorkbenchRegistryMergeGeneratorPort, "generate_registry_updates")
