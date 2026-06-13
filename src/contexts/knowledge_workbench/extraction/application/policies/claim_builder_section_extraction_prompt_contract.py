from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CLAIM_BUILDER_SECTION_EXTRACTION_PROMPT_ID = "faq_claim_observations"
CLAIM_BUILDER_SECTION_EXTRACTION_PROMPT_VERSION = "v1"
_CLAIM_BUILDER_SECTION_EXTRACTION_PROMPT_FILE_NAME = (
    "faq_surface_claim_observations.ru.txt"
)


@dataclass(frozen=True, slots=True)
class ClaimBuilderSectionExtractionPromptInput:
    source_unit_ref: str
    heading_path: tuple[str, ...]
    source_unit_text: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.source_unit_ref, field_name="source_unit_ref")
        if not isinstance(self.heading_path, tuple):
            raise TypeError("heading_path must be tuple")
        for heading_part in self.heading_path:
            _require_non_empty_text(heading_part, field_name="heading_path")
        _require_non_empty_text(self.source_unit_text, field_name="source_unit_text")


@dataclass(frozen=True, slots=True)
class ClaimBuilderSectionExtractionPromptContract:
    prompt_id: str
    prompt_version: str
    provider_messages: tuple[dict[str, str], ...]

    def __post_init__(self) -> None:
        _require_non_empty_text(self.prompt_id, field_name="prompt_id")
        _require_non_empty_text(self.prompt_version, field_name="prompt_version")
        if not isinstance(self.provider_messages, tuple):
            raise TypeError("provider_messages must be tuple")
        for message in self.provider_messages:
            if not isinstance(message, dict):
                raise TypeError("provider_messages must contain dict messages")
            if set(message) != {"role", "content"}:
                raise ValueError("provider message must contain role and content")
            _require_non_empty_text(message["role"], field_name="role")
            _require_non_empty_text(message["content"], field_name="content")


class BuildClaimBuilderSectionExtractionPrompt:
    def execute(
        self,
        command: ClaimBuilderSectionExtractionPromptInput,
    ) -> ClaimBuilderSectionExtractionPromptContract:
        prompt_text = _read_prompt_text()
        return ClaimBuilderSectionExtractionPromptContract(
            prompt_id=CLAIM_BUILDER_SECTION_EXTRACTION_PROMPT_ID,
            prompt_version=CLAIM_BUILDER_SECTION_EXTRACTION_PROMPT_VERSION,
            provider_messages=(
                {
                    "role": "system",
                    "content": _system_message(prompt_text),
                },
                {
                    "role": "user",
                    "content": _user_message(command),
                },
            ),
        )


def claim_builder_section_extraction_prompt_file() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "prompts"
        / _CLAIM_BUILDER_SECTION_EXTRACTION_PROMPT_FILE_NAME
    )


def claim_builder_section_extraction_prompt_repository_path() -> str:
    return (
        "src/contexts/knowledge_workbench/extraction/application/prompts/"
        f"{_CLAIM_BUILDER_SECTION_EXTRACTION_PROMPT_FILE_NAME}"
    )


def _read_prompt_text() -> str:
    prompt_path = claim_builder_section_extraction_prompt_file()
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt contract file is missing: {prompt_path}")

    prompt_text = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt_text:
        raise ValueError("Prompt contract file must be non-empty")
    if f"NODE: {CLAIM_BUILDER_SECTION_EXTRACTION_PROMPT_ID}" not in prompt_text:
        raise ValueError("Prompt contract file has unexpected node id")
    if "Return exactly one valid JSON object." not in prompt_text:
        raise ValueError("Prompt contract file must require strict JSON output")
    return prompt_text


def _system_message(prompt_text: str) -> str:
    return (
        f"prompt_id: {CLAIM_BUILDER_SECTION_EXTRACTION_PROMPT_ID}\n"
        f"prompt_version: {CLAIM_BUILDER_SECTION_EXTRACTION_PROMPT_VERSION}\n\n"
        f"{prompt_text}"
    )


def _user_message(command: ClaimBuilderSectionExtractionPromptInput) -> str:
    return (
        f"source_unit_ref: {command.source_unit_ref}\n"
        f"heading_path: {_format_heading_path(command.heading_path)}\n\n"
        f"{command.source_unit_text}"
    )


def _format_heading_path(heading_path: tuple[str, ...]) -> str:
    if not heading_path:
        return "/"
    return " / ".join(heading_path)


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
