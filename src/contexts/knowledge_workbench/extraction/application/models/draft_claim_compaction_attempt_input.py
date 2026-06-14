from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from src.domain.project_plane.json_types import JsonObject


class DraftClaimCompactionPromptKind(StrEnum):
    DRAFT_CLAIM_COMPACTION = "draft_claim_compaction"
    MIXED_CLAIM_COMPACTION = "mixed_claim_compaction"
    REDUCED_CLAIM_REWRITE = "reduced_claim_rewrite"


class DraftClaimCompactionExpectedOutputKind(StrEnum):
    COMPACTED_CLAIMS = "compacted_claims"
    REDUCED_REWRITE = "reduced_rewrite"


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionAttemptInput:
    workflow_run_id: str
    group_ref: str
    batch_ref: str
    work_item_id: str
    prompt_kind: DraftClaimCompactionPromptKind
    prompt_ref: str
    model_id: str
    payload: JsonObject
    expected_output_kind: DraftClaimCompactionExpectedOutputKind

    def __post_init__(self) -> None:
        _text(self.workflow_run_id, "workflow_run_id")
        _text(self.group_ref, "group_ref")
        _text(self.batch_ref, "batch_ref")
        _text(self.work_item_id, "work_item_id")
        object.__setattr__(
            self,
            "prompt_kind",
            DraftClaimCompactionPromptKind(self.prompt_kind),
        )
        _text(self.prompt_ref, "prompt_ref")
        _text(self.model_id, "model_id")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be Mapping")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        object.__setattr__(
            self,
            "expected_output_kind",
            DraftClaimCompactionExpectedOutputKind(self.expected_output_kind),
        )


def _text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
