from dataclasses import dataclass
from decimal import Decimal

from src.contexts.knowledge_workbench.application.sagas.claim_builder_source_ingestion_budget import (
    CLAIM_BUILDER_PROMPT_NAME,
    CLAIM_BUILDER_PROMPT_NODE_ID,
    CLAIM_BUILDER_PROMPT_PATH,
    CLAIM_BUILDER_PROMPT_TOKEN_COUNT,
    CLAIM_BUILDER_SEGMENTATION_PROFILE_NAME,
    claim_builder_char_to_token_multiplier,
    claim_builder_model_tpm,
    claim_builder_request_safety_gap_tokens,
)


@dataclass(frozen=True, slots=True)
class WorkbenchPromptProfile:
    prompt_name: str
    node_id: str
    prompt_path: str
    prompt_token_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.prompt_name, str) or not self.prompt_name.strip():
            raise ValueError("prompt_name must be non-empty")
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ValueError("node_id must be non-empty")
        if not isinstance(self.prompt_path, str) or not self.prompt_path.strip():
            raise ValueError("prompt_path must be non-empty")
        if not isinstance(self.prompt_token_count, int):
            raise TypeError("prompt_token_count must be int")
        if self.prompt_token_count < 0:
            raise ValueError("prompt_token_count must be >= 0")


@dataclass(frozen=True, slots=True)
class WorkbenchModelRequestBudgetProfile:
    profile_name: str
    max_request_input_tokens: int
    segmentation_input_safety_gap_tokens: int
    char_to_token_multiplier: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.profile_name, str) or not self.profile_name.strip():
            raise ValueError("profile_name must be non-empty")
        if not isinstance(self.max_request_input_tokens, int):
            raise TypeError("max_request_input_tokens must be int")
        if self.max_request_input_tokens <= 0:
            raise ValueError("max_request_input_tokens must be > 0")
        if not isinstance(self.segmentation_input_safety_gap_tokens, int):
            raise TypeError("segmentation_input_safety_gap_tokens must be int")
        if self.segmentation_input_safety_gap_tokens < 0:
            raise ValueError("segmentation_input_safety_gap_tokens must be >= 0")
        if self.segmentation_input_safety_gap_tokens >= self.max_request_input_tokens:
            raise ValueError(
                "segmentation_input_safety_gap_tokens must be < max_request_input_tokens"
            )
        if not isinstance(self.char_to_token_multiplier, Decimal):
            raise TypeError("char_to_token_multiplier must be Decimal")
        if self.char_to_token_multiplier <= 0:
            raise ValueError("char_to_token_multiplier must be > 0")


@dataclass(frozen=True, slots=True)
class SourceIngestionSegmentationProfile:
    prompt: WorkbenchPromptProfile
    primary_model: WorkbenchModelRequestBudgetProfile

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, WorkbenchPromptProfile):
            raise TypeError("prompt must be WorkbenchPromptProfile")
        if not isinstance(self.primary_model, WorkbenchModelRequestBudgetProfile):
            raise TypeError("primary_model must be WorkbenchModelRequestBudgetProfile")
        if (
            self.prompt.prompt_token_count
            + self.primary_model.segmentation_input_safety_gap_tokens
            >= self.primary_model.max_request_input_tokens
        ):
            raise ValueError(
                "prompt_token_count + segmentation_input_safety_gap_tokens must be "
                "< max_request_input_tokens"
            )

    @property
    def max_source_segment_tokens(self) -> int:
        return (
            self.primary_model.max_request_input_tokens
            - self.prompt.prompt_token_count
            - self.primary_model.segmentation_input_safety_gap_tokens
        ) // 2


def default_source_ingestion_segmentation_profile() -> (
    SourceIngestionSegmentationProfile
):
    # During source ingestion this field is intentionally only a small
    # input safety gap. Output budget is resolved later per concrete LLM
    # dispatch attempt from the actual source-unit prompt estimate.
    return SourceIngestionSegmentationProfile(
        prompt=WorkbenchPromptProfile(
            prompt_name=CLAIM_BUILDER_PROMPT_NAME,
            node_id=CLAIM_BUILDER_PROMPT_NODE_ID,
            prompt_path=CLAIM_BUILDER_PROMPT_PATH,
            prompt_token_count=CLAIM_BUILDER_PROMPT_TOKEN_COUNT,
        ),
        primary_model=WorkbenchModelRequestBudgetProfile(
            profile_name=CLAIM_BUILDER_SEGMENTATION_PROFILE_NAME,
            max_request_input_tokens=claim_builder_model_tpm(),
            segmentation_input_safety_gap_tokens=claim_builder_request_safety_gap_tokens(),
            char_to_token_multiplier=claim_builder_char_to_token_multiplier(),
        ),
    )
