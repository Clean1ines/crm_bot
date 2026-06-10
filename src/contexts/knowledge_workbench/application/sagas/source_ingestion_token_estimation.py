from typing import Protocol
from dataclasses import dataclass, replace

from src.contexts.knowledge_workbench.application.sagas.source_ingestion_segmentation_profiles import (
    SourceIngestionSegmentationProfile,
)
from src.contexts.knowledge_workbench.document_segmentation.domain.segmentation_budget import (
    estimate_tokens_roughly,
)


class WorkbenchTokenEstimatorPort(Protocol):
    def estimate_tokens(self, text: str) -> int: ...


@dataclass(frozen=True, slots=True)
class RoughWorkbenchTokenEstimator:
    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens_roughly(text)


@dataclass(frozen=True, slots=True)
class WorkbenchPromptText:
    prompt_name: str
    node_id: str
    prompt_path: str
    text: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.prompt_name, field_name="prompt_name")
        _require_non_empty_text(self.node_id, field_name="node_id")
        _require_non_empty_text(self.prompt_path, field_name="prompt_path")
        _require_non_empty_text(self.text, field_name="text")


@dataclass(frozen=True, slots=True)
class VerifiedPromptTokenEstimate:
    prompt_name: str
    node_id: str
    prompt_path: str
    prompt_token_count: int

    def __post_init__(self) -> None:
        _require_non_empty_text(self.prompt_name, field_name="prompt_name")
        _require_non_empty_text(self.node_id, field_name="node_id")
        _require_non_empty_text(self.prompt_path, field_name="prompt_path")
        if not isinstance(self.prompt_token_count, int):
            raise TypeError("prompt_token_count must be int")
        if self.prompt_token_count <= 0:
            raise ValueError("prompt_token_count must be > 0")


@dataclass(frozen=True, slots=True)
class SourceIngestionPromptTokenEstimationService:
    token_estimator: WorkbenchTokenEstimatorPort

    def __post_init__(self) -> None:
        estimator = getattr(self.token_estimator, "estimate_tokens", None)
        if not callable(estimator):
            raise TypeError("token_estimator must expose estimate_tokens")

    def estimate_prompt_tokens(
        self,
        prompt_text: WorkbenchPromptText,
    ) -> VerifiedPromptTokenEstimate:
        count = self.token_estimator.estimate_tokens(prompt_text.text)
        if count <= 0:
            raise ValueError("estimated prompt token count must be > 0")

        return VerifiedPromptTokenEstimate(
            prompt_name=prompt_text.prompt_name,
            node_id=prompt_text.node_id,
            prompt_path=prompt_text.prompt_path,
            prompt_token_count=count,
        )

    def with_estimated_prompt_tokens(
        self,
        *,
        profile: SourceIngestionSegmentationProfile,
        prompt_text: WorkbenchPromptText,
    ) -> SourceIngestionSegmentationProfile:
        _require_prompt_metadata_match(profile=profile, prompt_text=prompt_text)
        verified = self.estimate_prompt_tokens(prompt_text)
        updated_prompt = replace(
            profile.prompt,
            prompt_token_count=verified.prompt_token_count,
        )
        return replace(profile, prompt=updated_prompt)


def _require_prompt_metadata_match(
    *,
    profile: SourceIngestionSegmentationProfile,
    prompt_text: WorkbenchPromptText,
) -> None:
    if prompt_text.prompt_name != profile.prompt.prompt_name:
        raise ValueError("prompt_name mismatch")
    if prompt_text.node_id != profile.prompt.node_id:
        raise ValueError("node_id mismatch")
    if prompt_text.prompt_path != profile.prompt.prompt_path:
        raise ValueError("prompt_path mismatch")


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
