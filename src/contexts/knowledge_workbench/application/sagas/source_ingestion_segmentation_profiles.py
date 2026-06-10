from dataclasses import dataclass


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
    reserved_output_tokens: int

    def __post_init__(self) -> None:
        if not isinstance(self.profile_name, str) or not self.profile_name.strip():
            raise ValueError("profile_name must be non-empty")
        if not isinstance(self.max_request_input_tokens, int):
            raise TypeError("max_request_input_tokens must be int")
        if self.max_request_input_tokens <= 0:
            raise ValueError("max_request_input_tokens must be > 0")
        if not isinstance(self.reserved_output_tokens, int):
            raise TypeError("reserved_output_tokens must be int")
        if self.reserved_output_tokens < 0:
            raise ValueError("reserved_output_tokens must be >= 0")
        if self.reserved_output_tokens >= self.max_request_input_tokens:
            raise ValueError(
                "reserved_output_tokens must be < max_request_input_tokens"
            )


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
            self.prompt.prompt_token_count + self.primary_model.reserved_output_tokens
            >= self.primary_model.max_request_input_tokens
        ):
            raise ValueError(
                "prompt_token_count + reserved_output_tokens must be "
                "< max_request_input_tokens"
            )

    @property
    def max_source_segment_tokens(self) -> int:
        return (
            self.primary_model.max_request_input_tokens
            - self.prompt.prompt_token_count
            - self.primary_model.reserved_output_tokens
        )


def default_source_ingestion_segmentation_profile() -> (
    SourceIngestionSegmentationProfile
):
    # prompt_token_count is currently a conservative static estimate.
    # A later tokenizer/profile patch will compute or verify it outside
    # document_segmentation.
    return SourceIngestionSegmentationProfile(
        prompt=WorkbenchPromptProfile(
            prompt_name="draft_observation_extraction",
            node_id="faq_claim_observations",
            prompt_path="src/agent/prompts/faq_surface_claim_observations.ru.txt",
            prompt_token_count=2_000,
        ),
        primary_model=WorkbenchModelRequestBudgetProfile(
            profile_name="primary_model",
            max_request_input_tokens=6_000,
            reserved_output_tokens=1_000,
        ),
    )
