from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from fractions import Fraction

TokenEstimator = Callable[[str], int]


@dataclass(frozen=True, slots=True)
class RoughTokenEstimator:
    multiplier: Fraction

    def __post_init__(self) -> None:
        if not isinstance(self.multiplier, Fraction):
            raise TypeError("multiplier must be Fraction")
        if self.multiplier <= 0:
            raise ValueError("multiplier must be > 0")

    def estimate_tokens(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError("text must be str")
        if not text.strip():
            return 0

        numerator = self.multiplier.numerator
        denominator = self.multiplier.denominator
        return max(1, (len(text) * denominator + numerator - 1) // numerator)


COMPACTION_ROUGH_TOKEN_ESTIMATOR = RoughTokenEstimator(
    multiplier=Fraction(37, 10),
)


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
        available_tokens = (
            self.model.max_request_input_tokens
            - self.prompt.prompt_token_count
            - self.model.segmentation_input_safety_gap_tokens
        )
        return available_tokens // 2

    def estimate_tokens(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError("text must be str")
        if not text.strip():
            return 0
        return max(
            1,
            int(
                (
                    Decimal(len(text)) / self.model.char_to_token_multiplier
                ).to_integral_value(rounding=ROUND_CEILING)
            ),
        )


def text_fits_segmentation_budget(
    *,
    text: str,
    budget: DocumentSegmentationBudget,
    token_estimator: TokenEstimator | None = None,
) -> bool:
    effective_token_estimator = (
        budget.estimate_tokens if token_estimator is None else token_estimator
    )
    return effective_token_estimator(text) <= budget.max_source_segment_tokens


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
