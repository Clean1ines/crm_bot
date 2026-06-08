from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind


class QuotaDecisionKind(StrEnum):
    ALLOW = "allow"
    WAIT_UNTIL = "wait_until"
    TRY_OTHER_ACCOUNT = "try_other_account"
    TRY_OTHER_MODEL = "try_other_model"
    DAILY_EXHAUSTED = "daily_exhausted"
    CAPACITY_UNKNOWN = "capacity_unknown"


@dataclass(frozen=True, slots=True)
class QuotaDecision:
    kind: QuotaDecisionKind
    reason: LlmErrorKind | None = None
    wait_until: datetime | None = None

    def __post_init__(self) -> None:
        if self.kind is QuotaDecisionKind.WAIT_UNTIL:
            if self.wait_until is None:
                raise ValueError("WAIT_UNTIL decision must have wait_until")
            if self.wait_until.tzinfo is None or self.wait_until.utcoffset() is None:
                raise ValueError("wait_until must be timezone-aware")
        if (
            self.kind is not QuotaDecisionKind.WAIT_UNTIL
            and self.wait_until is not None
        ):
            raise ValueError("Only WAIT_UNTIL decision may carry wait_until")

    @classmethod
    def allow(cls) -> "QuotaDecision":
        return cls(QuotaDecisionKind.ALLOW)
