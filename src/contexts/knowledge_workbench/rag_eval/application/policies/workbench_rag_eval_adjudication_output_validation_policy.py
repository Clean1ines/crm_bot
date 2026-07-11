from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalAdjudicationVerdict,
)


WORKBENCH_RAG_EVAL_ADJUDICATION_CONTRACT_VERSION = "workbench_rag_eval_adjudication.v1"


class WorkbenchRagEvalAdjudicationOutputValidationOutcome(StrEnum):
    VALID_ADJUDICATION = "VALID_ADJUDICATION"
    INVALID_JSON = "INVALID_JSON"
    INVALID_ROOT = "INVALID_ROOT"
    INVALID_CONTRACT_VERSION = "INVALID_CONTRACT_VERSION"
    INVALID_VERDICT = "INVALID_VERDICT"
    INVALID_PROMOTION_RECOMMENDATION = "INVALID_PROMOTION_RECOMMENDATION"
    INVALID_REASON = "INVALID_REASON"


@dataclass(frozen=True, slots=True)
class ValidatedWorkbenchRagEvalAdjudicationOutput:
    contract_version: str
    verdict: WorkbenchRagEvalAdjudicationVerdict
    promotion_recommended: bool
    reason: str


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalAdjudicationOutputValidationResult:
    outcome: WorkbenchRagEvalAdjudicationOutputValidationOutcome
    adjudication: ValidatedWorkbenchRagEvalAdjudicationOutput | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if (
            self.outcome
            is WorkbenchRagEvalAdjudicationOutputValidationOutcome.VALID_ADJUDICATION
        ):
            if self.adjudication is None:
                raise ValueError("valid adjudication requires parsed adjudication")
            if self.error is not None:
                raise ValueError("valid adjudication cannot include error")
            return
        if self.adjudication is not None:
            raise ValueError("invalid adjudication cannot include parsed adjudication")
        if self.error is None or not self.error.strip():
            raise ValueError("invalid adjudication requires error")


class WorkbenchRagEvalAdjudicationOutputValidationPolicy:
    def validate(
        self,
        *,
        raw_text: str,
    ) -> WorkbenchRagEvalAdjudicationOutputValidationResult:
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return _invalid(
                WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_JSON,
                str(exc),
            )
        if not isinstance(payload, dict):
            return _invalid(
                WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_ROOT,
                "root must be object",
            )
        allowed = {
            "contract_version",
            "verdict",
            "promotion_recommended",
            "reason",
        }
        if set(payload) != allowed:
            return _invalid(
                WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_ROOT,
                "root must contain exactly required fields",
            )
        contract_version = payload.get("contract_version")
        if contract_version != WORKBENCH_RAG_EVAL_ADJUDICATION_CONTRACT_VERSION:
            return _invalid(
                WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_CONTRACT_VERSION,
                "invalid contract_version",
            )
        verdict_value = payload.get("verdict")
        if not isinstance(verdict_value, str):
            return _invalid(
                WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_VERDICT,
                "verdict must be string",
            )
        try:
            verdict = WorkbenchRagEvalAdjudicationVerdict(verdict_value)
        except ValueError:
            return _invalid(
                WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_VERDICT,
                "unknown verdict",
            )
        promotion_recommended = payload.get("promotion_recommended")
        if not isinstance(promotion_recommended, bool):
            return _invalid(
                WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_PROMOTION_RECOMMENDATION,
                "promotion_recommended must be bool",
            )
        if (
            promotion_recommended
            and verdict is not WorkbenchRagEvalAdjudicationVerdict.VALID_TARGET_QUERY
        ):
            return _invalid(
                WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_PROMOTION_RECOMMENDATION,
                "promotion_recommended=true requires valid_target_query verdict",
            )
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            return _invalid(
                WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_REASON,
                "reason must be non-empty string",
            )
        return WorkbenchRagEvalAdjudicationOutputValidationResult(
            outcome=(
                WorkbenchRagEvalAdjudicationOutputValidationOutcome.VALID_ADJUDICATION
            ),
            adjudication=ValidatedWorkbenchRagEvalAdjudicationOutput(
                contract_version=contract_version,
                verdict=verdict,
                promotion_recommended=promotion_recommended,
                reason=reason.strip(),
            ),
        )


def _invalid(
    outcome: WorkbenchRagEvalAdjudicationOutputValidationOutcome,
    error: str,
) -> WorkbenchRagEvalAdjudicationOutputValidationResult:
    return WorkbenchRagEvalAdjudicationOutputValidationResult(
        outcome=outcome,
        error=error,
    )
