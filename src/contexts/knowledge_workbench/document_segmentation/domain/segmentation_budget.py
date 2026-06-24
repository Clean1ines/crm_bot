from collections.abc import Callable
from dataclasses import dataclass

TokenEstimator = Callable[[str], int]


def estimate_tokens_roughly(text: str) -> int:
    if not text.strip():
        return 0
    return max(1, (len(text) * 10 + 32) // 33)


@dataclass(frozen=True, slots=True)
class SegmentationPromptProfile:
    prompt_name: str
    prompt_token_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.prompt_name, str) or not self.prompt_name.strip():
            raise ValueError("prompt_name must be non-empty")
        if not isinstance(self.prompt_token_count, int):
            raise TypeError("prompt_token_count must be int")
        if self.prompt_token_count < 0:
            raise ValueError("prompt_token_count must be >= 0")


@dataclass(frozen=True, slots=True)
class SegmentationModelBudgetProfile:
    profile_name: str
    max_request_input_tokens: int
    segmentation_input_safety_gap_tokens: int

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


@dataclass(frozen=True, slots=True)
class DocumentSegmentationBudget:
    prompt: SegmentationPromptProfile
    model: SegmentationModelBudgetProfile

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, SegmentationPromptProfile):
            raise TypeError("prompt must be SegmentationPromptProfile")
        if not isinstance(self.model, SegmentationModelBudgetProfile):
            raise TypeError("model must be SegmentationModelBudgetProfile")
        if self.max_source_segment_tokens <= 0:
            raise ValueError("max_source_segment_tokens must be > 0")

    @property
    def max_source_segment_tokens(self) -> int:
        return (
            self.model.max_request_input_tokens
            - self.prompt.prompt_token_count
            - self.model.segmentation_input_safety_gap_tokens
        )


def text_fits_segmentation_budget(
    *,
    text: str,
    budget: DocumentSegmentationBudget,
    token_estimator: TokenEstimator = estimate_tokens_roughly,
) -> bool:
    return token_estimator(text) <= budget.max_source_segment_tokens


def required_segment_count(
    *,
    estimated_tokens: int,
    budget: DocumentSegmentationBudget,
) -> int:
    if not isinstance(estimated_tokens, int):
        raise TypeError("estimated_tokens must be int")
    if estimated_tokens <= 0:
        raise ValueError("estimated_tokens must be > 0")
    return (
        estimated_tokens + budget.max_source_segment_tokens - 1
    ) // budget.max_source_segment_tokens
