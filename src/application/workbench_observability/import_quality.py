from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from src.application.workbench_observability.tombstone import (
    is_deleted_workbench_document,
)

from src.domain.project_plane.knowledge_workbench.import_quality_policy import (
    WorkbenchImportQualityIssue,
    WorkbenchImportQualitySeverity,
    decide_import_quality_action,
)


class WorkbenchImportQualityNotFoundError(LookupError):
    pass


class WorkbenchImportQualityQueryPort(Protocol):
    async def get_import_quality_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None: ...

    async def list_import_quality_sections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]: ...

    async def list_import_quality_findings(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]: ...

    async def list_import_quality_canonical_facts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]: ...

    async def list_import_quality_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]: ...

    async def list_import_quality_node_runs(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class WorkbenchImportQualityReadService:
    query: WorkbenchImportQualityQueryPort

    async def fetch_import_quality_report(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> dict[str, object]:
        document = await self.query.get_import_quality_document(
            project_id=project_id,
            document_id=document_id,
        )
        if document is None or is_deleted_workbench_document(document):
            raise WorkbenchImportQualityNotFoundError("Knowledge document not found")

        sections = [
            _section_payload(row)
            for row in await self.query.list_import_quality_sections(
                project_id=project_id,
                document_id=document_id,
            )
        ]
        findings = [
            _finding_payload(row)
            for row in await self.query.list_import_quality_findings(
                project_id=project_id,
                document_id=document_id,
            )
        ]
        canonical_facts = [
            _canonical_fact_payload(row)
            for row in await self.query.list_import_quality_canonical_facts(
                project_id=project_id,
                document_id=document_id,
            )
        ]
        surfaces = [
            _surface_payload(row)
            for row in await self.query.list_import_quality_surfaces(
                project_id=project_id,
                document_id=document_id,
            )
        ]
        node_runs = [
            _node_run_payload(row)
            for row in await self.query.list_import_quality_node_runs(
                project_id=project_id,
                document_id=document_id,
            )
        ]

        section_ids = {str(section["section_id"]) for section in sections}
        findings_by_section: dict[str, int] = defaultdict(int)
        for finding in findings:
            section_id = str(finding.get("section_id") or "")
            if section_id:
                findings_by_section[section_id] += 1

        sections_without_findings = [
            section
            for section in sections
            if str(section["section_id"]) not in findings_by_section
        ]

        findings_without_evidence = [
            finding for finding in findings if not _has_evidence(finding)
        ]
        canonical_facts_without_evidence = [
            entry for entry in canonical_facts if not _has_evidence(entry)
        ]
        surfaces_without_evidence = [
            surface for surface in surfaces if not _has_evidence(surface)
        ]
        surfaces_with_missing_sections = [
            surface
            for surface in surfaces
            if any(
                str(section_id) not in section_ids
                for section_id in _json_list(surface.get("source_section_ids"))
            )
        ]
        failed_node_runs = [
            run
            for run in node_runs
            if str(run["status"]).lower() in {"failed", "error"}
        ]

        section_status_counts = Counter(str(section["status"]) for section in sections)
        surface_status_counts = Counter(str(surface["status"]) for surface in surfaces)
        node_status_counts = Counter(str(run["status"]) for run in node_runs)

        warnings = _build_warnings(
            sections=sections,
            sections_without_findings=sections_without_findings,
            findings_without_evidence=findings_without_evidence,
            canonical_facts_without_evidence=canonical_facts_without_evidence,
            surfaces_without_evidence=surfaces_without_evidence,
            surfaces_with_missing_sections=surfaces_with_missing_sections,
            failed_node_runs=failed_node_runs,
        )

        quality_decision = _quality_decision_payload(warnings)

        return {
            "document": _document_payload(document),
            "status": _overall_status(
                sections=sections,
                sections_without_findings=sections_without_findings,
                findings_without_evidence=findings_without_evidence,
                canonical_facts_without_evidence=canonical_facts_without_evidence,
                surfaces_without_evidence=surfaces_without_evidence,
                failed_node_runs=failed_node_runs,
            ),
            "quality_decision": quality_decision,
            "summary": {
                "sections_total": len(sections),
                "findings_total": len(findings),
                "canonical_facts_total": len(canonical_facts),
                "surfaces_total": len(surfaces),
                "node_runs_total": len(node_runs),
                "warnings_total": len(warnings),
            },
            "section_quality": {
                "by_status": dict(sorted(section_status_counts.items())),
                "sections_without_findings": _section_refs(sections_without_findings),
                "sections_without_findings_count": len(sections_without_findings),
            },
            "evidence_quality": {
                "findings_without_evidence_count": len(findings_without_evidence),
                "canonical_facts_without_evidence_count": len(
                    canonical_facts_without_evidence
                ),
                "surfaces_without_evidence_count": len(surfaces_without_evidence),
                "surfaces_with_missing_sections_count": len(
                    surfaces_with_missing_sections
                ),
            },
            "surface_quality": {
                "by_status": dict(sorted(surface_status_counts.items())),
                "surfaces_without_evidence": _surface_refs(surfaces_without_evidence),
                "surfaces_with_missing_sections": _surface_refs(
                    surfaces_with_missing_sections
                ),
            },
            "node_quality": {
                "by_status": dict(sorted(node_status_counts.items())),
                "failed_node_runs": failed_node_runs,
                "failed_node_runs_count": len(failed_node_runs),
            },
            "warnings": warnings,
            "items": warnings,
        }


def _overall_status(
    *,
    sections: Sequence[Mapping[str, object]],
    sections_without_findings: Sequence[Mapping[str, object]],
    findings_without_evidence: Sequence[Mapping[str, object]],
    canonical_facts_without_evidence: Sequence[Mapping[str, object]],
    surfaces_without_evidence: Sequence[Mapping[str, object]],
    failed_node_runs: Sequence[Mapping[str, object]],
) -> str:
    if not sections:
        return "empty"
    if failed_node_runs:
        return "failed"
    if (
        sections_without_findings
        or findings_without_evidence
        or canonical_facts_without_evidence
        or surfaces_without_evidence
    ):
        return "needs_review"
    return "ok"


def _build_warnings(
    *,
    sections: Sequence[Mapping[str, object]],
    sections_without_findings: Sequence[Mapping[str, object]],
    findings_without_evidence: Sequence[Mapping[str, object]],
    canonical_facts_without_evidence: Sequence[Mapping[str, object]],
    surfaces_without_evidence: Sequence[Mapping[str, object]],
    surfaces_with_missing_sections: Sequence[Mapping[str, object]],
    failed_node_runs: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []

    if not sections:
        warnings.append(
            {
                "code": "no_sections",
                "severity": "error",
                "message": "Document has no Workbench sections.",
            }
        )

    if sections_without_findings:
        warnings.append(
            {
                "code": "sections_without_findings",
                "severity": "warning",
                "message": "Some sections produced no extracted findings.",
                "count": len(sections_without_findings),
            }
        )

    if findings_without_evidence:
        warnings.append(
            {
                "code": "findings_without_evidence",
                "severity": "warning",
                "message": "Some findings have no explicit evidence.",
                "count": len(findings_without_evidence),
            }
        )

    if canonical_facts_without_evidence:
        warnings.append(
            {
                "code": "canonical_facts_without_evidence",
                "severity": "warning",
                "message": "Some canonical facts have no explicit evidence.",
                "count": len(canonical_facts_without_evidence),
            }
        )

    if surfaces_without_evidence:
        warnings.append(
            {
                "code": "surfaces_without_evidence",
                "severity": "warning",
                "message": "Some surface cards have no explicit evidence.",
                "count": len(surfaces_without_evidence),
            }
        )

    if surfaces_with_missing_sections:
        warnings.append(
            {
                "code": "surfaces_with_missing_sections",
                "severity": "error",
                "message": "Some surface cards reference missing source sections.",
                "count": len(surfaces_with_missing_sections),
            }
        )

    if failed_node_runs:
        warnings.append(
            {
                "code": "failed_node_runs",
                "severity": "error",
                "message": "Some Workbench processing nodes failed.",
                "count": len(failed_node_runs),
            }
        )

    return warnings


def _quality_decision_payload(
    warnings: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    issues = tuple(_quality_issue_from_warning(warning) for warning in warnings)
    decision = decide_import_quality_action(issues)

    return {
        "action": decision.action.value,
        "can_process": decision.can_process,
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity.value,
                "message": issue.message,
            }
            for issue in decision.issues
        ],
    }


def _quality_issue_from_warning(
    warning: Mapping[str, object],
) -> WorkbenchImportQualityIssue:
    return WorkbenchImportQualityIssue(
        code=_text(warning.get("code")) or "unknown_import_quality_issue",
        severity=_quality_severity(warning.get("severity")),
        message=_text(warning.get("message")),
    )


def _quality_severity(value: object) -> WorkbenchImportQualitySeverity:
    raw = _text(value).lower()
    if raw == WorkbenchImportQualitySeverity.ERROR.value:
        return WorkbenchImportQualitySeverity.ERROR
    if raw == WorkbenchImportQualitySeverity.INFO.value:
        return WorkbenchImportQualitySeverity.INFO
    return WorkbenchImportQualitySeverity.WARNING


def _document_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "project_id": _text(row.get("project_id")),
        "document_id": _text(row.get("document_id")),
        "file_name": _text(row.get("file_name")),
        "source_type": _text(row.get("source_type")),
        "file_size_bytes": _int(row.get("file_size_bytes")),
        "status": _text(row.get("status")),
        "current_processing_run_id": _nullable_text(
            row.get("current_processing_run_id")
        ),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "deleted_at": _iso(row.get("deleted_at")),
    }


def _section_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "section_id": _text(row.get("section_id")),
        "section_key": _text(row.get("section_key")),
        "section_index": _int(row.get("section_index")),
        "title": _text(row.get("title")),
        "status": _text(row.get("status")),
        "source_refs": _json_list(row.get("source_refs")),
        "source_chunk_indexes": _json_list(row.get("source_chunk_indexes")),
    }


def _finding_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "claim_observation_id": _text(row.get("claim_observation_id")),
        "section_id": _text(row.get("section_id")),
        "status": _text(row.get("status")),
        "action": _text(row.get("action")),
        "evidence_quotes": _json_list(row.get("evidence_quotes")),
        "source_refs": _json_list(row.get("source_refs")),
        "source_chunk_indexes": _json_list(row.get("source_chunk_indexes")),
        "confidence": _nullable_float(row.get("confidence")),
    }


def _canonical_fact_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "fact_id": _text(row.get("fact_id")),
        "fact_key": _text(row.get("fact_key")),
        "status": _text(row.get("status")),
        "evidence_quotes": _json_list(row.get("evidence_quotes")),
        "source_refs": _json_list(row.get("source_refs")),
        "source_section_ids": _json_list(row.get("source_section_ids")),
        "source_chunk_indexes": _json_list(row.get("source_chunk_indexes")),
    }


def _surface_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "surface_id": _text(row.get("surface_id")),
        "fact_id": _nullable_text(row.get("fact_id")),
        "status": _text(row.get("status")),
        "curation_state": _text(row.get("curation_state")),
        "evidence_quotes": _json_list(row.get("evidence_quotes")),
        "source_refs": _json_list(row.get("source_refs")),
        "source_section_ids": _json_list(row.get("source_section_ids")),
    }


def _node_run_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "node_run_id": _text(row.get("node_run_id")),
        "processing_run_id": _text(row.get("processing_run_id")),
        "node_name": _text(row.get("node_name")),
        "status": _text(row.get("status")),
        "error_kind": _nullable_text(row.get("error_kind")),
        "error_message": _nullable_text(row.get("error_message")),
        "started_at": _iso(row.get("started_at")),
        "completed_at": _iso(row.get("completed_at")),
    }


def _section_refs(sections: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "section_id": _text(section.get("section_id")),
            "section_key": _text(section.get("section_key")),
            "title": _text(section.get("title")),
        }
        for section in sections
    ]


def _surface_refs(surfaces: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "surface_id": _text(surface.get("surface_id")),
            "status": _text(surface.get("status")),
            "curation_state": _text(surface.get("curation_state")),
        }
        for surface in surfaces
    ]


def _has_evidence(item: Mapping[str, object]) -> bool:
    return bool(
        _json_list(item.get("evidence_quotes"))
        or _json_list(item.get("source_refs"))
        or _json_list(item.get("source_section_ids"))
        or _json_list(item.get("source_chunk_indexes"))
    )


def _json_list(value: object) -> list[object]:
    parsed = _parse_json(value)
    if isinstance(parsed, list):
        return parsed
    if parsed is None:
        return []
    return [parsed]


def _parse_json(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _nullable_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _int(value: object) -> int:
    if value is None:
        return 0
    return int(str(value))


def _nullable_float(value: object) -> float | None:
    if value is None:
        return None
    return float(str(value))


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)
