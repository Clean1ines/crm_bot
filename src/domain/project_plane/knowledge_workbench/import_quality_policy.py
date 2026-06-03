from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkbenchImportQualitySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class WorkbenchImportQualityAction(StrEnum):
    PROCESS = "process"
    PROCESS_WITH_WARNINGS = "process_with_warnings"
    REQUIRE_REVIEW = "require_review"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class WorkbenchImportQualityIssue:
    code: str
    severity: WorkbenchImportQualitySeverity
    message: str


@dataclass(frozen=True, slots=True)
class WorkbenchImportQualityDecision:
    action: WorkbenchImportQualityAction
    issues: tuple[WorkbenchImportQualityIssue, ...]

    @property
    def can_process(self) -> bool:
        return self.action in {
            WorkbenchImportQualityAction.PROCESS,
            WorkbenchImportQualityAction.PROCESS_WITH_WARNINGS,
        }


def decide_import_quality_action(
    issues: tuple[WorkbenchImportQualityIssue, ...],
) -> WorkbenchImportQualityDecision:
    severities = {issue.severity for issue in issues}

    if WorkbenchImportQualitySeverity.ERROR in severities:
        action = WorkbenchImportQualityAction.REJECT
    elif WorkbenchImportQualitySeverity.WARNING in severities:
        action = WorkbenchImportQualityAction.PROCESS_WITH_WARNINGS
    else:
        action = WorkbenchImportQualityAction.PROCESS

    return WorkbenchImportQualityDecision(action=action, issues=issues)


def require_import_quality_review(
    *,
    issues: tuple[WorkbenchImportQualityIssue, ...],
    reason: str,
) -> WorkbenchImportQualityDecision:
    review_issue = WorkbenchImportQualityIssue(
        code="manual_review_required",
        severity=WorkbenchImportQualitySeverity.WARNING,
        message=reason,
    )
    return WorkbenchImportQualityDecision(
        action=WorkbenchImportQualityAction.REQUIRE_REVIEW,
        issues=(*issues, review_issue),
    )
