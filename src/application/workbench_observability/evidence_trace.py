from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from src.application.workbench_observability.tombstone import (
    is_deleted_workbench_document,
)


class WorkbenchEvidenceTraceNotFoundError(LookupError):
    pass


class WorkbenchEvidenceTraceQueryPort(Protocol):
    async def get_evidence_trace_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None: ...

    async def list_evidence_trace_sections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]: ...

    async def list_evidence_trace_findings(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]: ...

    async def list_evidence_trace_canonical_facts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]: ...

    async def list_evidence_trace_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class WorkbenchEvidenceTraceReadService:
    query: WorkbenchEvidenceTraceQueryPort

    async def fetch_document_evidence_trace(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> dict[str, object]:
        document = await self.query.get_evidence_trace_document(
            project_id=project_id,
            document_id=document_id,
        )
        if document is None or is_deleted_workbench_document(document):
            raise WorkbenchEvidenceTraceNotFoundError("Knowledge document not found")

        sections = [
            _section_payload(row)
            for row in await self.query.list_evidence_trace_sections(
                project_id=project_id,
                document_id=document_id,
            )
        ]
        findings = [
            _finding_payload(row)
            for row in await self.query.list_evidence_trace_findings(
                project_id=project_id,
                document_id=document_id,
            )
        ]
        canonical_facts = [
            _canonical_fact_payload(row)
            for row in await self.query.list_evidence_trace_canonical_facts(
                project_id=project_id,
                document_id=document_id,
            )
        ]
        surfaces = [
            _surface_payload(row)
            for row in await self.query.list_evidence_trace_surfaces(
                project_id=project_id,
                document_id=document_id,
            )
        ]

        by_section = {str(section["section_id"]): section for section in sections}
        section_key_to_id = {
            str(section["section_key"]): str(section["section_id"])
            for section in sections
        }

        for section in sections:
            section["findings"] = []
            section["canonical_facts"] = []
            section["surfaces"] = []

        unassigned_findings: list[dict[str, object]] = []
        for finding in findings:
            finding_section = by_section.get(str(finding.get("section_id") or ""))
            if finding_section is None:
                unassigned_findings.append(finding)
            else:
                _append_child(finding_section, "findings", finding)

        unassigned_canonical_facts: list[dict[str, object]] = []
        for entry in canonical_facts:
            assigned = _assign_by_source_section_ids(
                by_section=by_section,
                section_key_to_id=section_key_to_id,
                item=entry,
                target_key="canonical_facts",
            )
            if not assigned:
                unassigned_canonical_facts.append(entry)

        unassigned_surfaces: list[dict[str, object]] = []
        for surface in surfaces:
            assigned = _assign_by_source_section_ids(
                by_section=by_section,
                section_key_to_id=section_key_to_id,
                item=surface,
                target_key="surfaces",
            )
            if not assigned:
                unassigned_surfaces.append(surface)

        source_units = sections
        coverage = _coverage(
            source_units=source_units,
            findings=findings,
            canonical_facts=canonical_facts,
            surfaces=surfaces,
        )
        gaps = {
            "unassigned_findings": unassigned_findings,
            "unassigned_canonical_facts": unassigned_canonical_facts,
            "unassigned_surfaces": unassigned_surfaces,
            "ungrounded_surfaces": [
                surface
                for surface in surfaces
                if not surface["source_refs"]
                and not surface["source_section_ids"]
                and not surface["evidence_quotes"]
            ],
        }

        return {
            "document": _document_payload(document),
            "source_units": source_units,
            "items": source_units,
            "findings": findings,
            "canonical_facts": canonical_facts,
            "surfaces": surfaces,
            "coverage": coverage,
            "gaps": gaps,
        }


def _append_child(
    section: dict[str, object],
    key: str,
    child: dict[str, object],
) -> None:
    children = section.get(key)
    if not isinstance(children, list):
        children = []
        section[key] = children
    children.append(child)


def _assign_by_source_section_ids(
    *,
    by_section: Mapping[str, dict[str, object]],
    section_key_to_id: Mapping[str, str],
    item: dict[str, object],
    target_key: str,
) -> bool:
    raw_ids = _json_list(item.get("source_section_ids"))
    assigned_ids: set[str] = set()

    for raw_id in raw_ids:
        section_ref = str(raw_id)
        section_id = section_ref
        if section_id not in by_section:
            section_id = section_key_to_id.get(section_ref, "")

        section = by_section.get(section_id)
        if section is None:
            continue

        _append_child(section, target_key, item)
        assigned_ids.add(section_id)

    return bool(assigned_ids)


def _coverage(
    *,
    source_units: Sequence[Mapping[str, object]],
    findings: Sequence[Mapping[str, object]],
    canonical_facts: Sequence[Mapping[str, object]],
    surfaces: Sequence[Mapping[str, object]],
) -> dict[str, int]:
    return {
        "source_units_total": len(source_units),
        "source_units_with_source_refs": sum(
            1 for item in source_units if item.get("source_refs")
        ),
        "findings_total": len(findings),
        "findings_with_evidence": sum(
            1
            for item in findings
            if item.get("source_refs")
            or item.get("source_chunk_indexes")
            or item.get("evidence_quotes")
        ),
        "canonical_facts_total": len(canonical_facts),
        "canonical_facts_with_evidence": sum(
            1
            for item in canonical_facts
            if item.get("source_refs")
            or item.get("source_section_ids")
            or item.get("evidence_quotes")
        ),
        "surfaces_total": len(surfaces),
        "surfaces_with_evidence": sum(
            1
            for item in surfaces
            if item.get("source_refs")
            or item.get("source_section_ids")
            or item.get("evidence_quotes")
        ),
    }


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
    raw_text = _text(row.get("raw_text"))
    return {
        "unit_id": _text(row.get("section_id")),
        "source_unit_id": _text(row.get("section_id")),
        "section_id": _text(row.get("section_id")),
        "section_key": _text(row.get("section_key")),
        "section_index": _int(row.get("section_index")),
        "title": _text(row.get("title")),
        "status": _text(row.get("status")),
        "source_refs": _json_list(row.get("source_refs")),
        "source_chunk_indexes": _json_list(row.get("source_chunk_indexes")),
        "metadata": _json_dict(row.get("metadata")),
        "text_excerpt": _excerpt(raw_text),
        "raw_text_excerpt": _excerpt(raw_text),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def _finding_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "claim_observation_id": _text(row.get("claim_observation_id")),
        "section_id": _text(row.get("section_id")),
        "action": _text(row.get("action")),
        "status": _text(row.get("status")),
        "target_fact_id": _nullable_text(row.get("target_fact_id")),
        "claim_local_ref": _nullable_text(row.get("claim_local_ref")),
        "title": _nullable_text(row.get("title")),
        "claim": _nullable_text(row.get("claim")),
        "claim_kind": _text(row.get("claim_kind")),
        "answer": _nullable_text(row.get("answer")),
        "short_answer": _nullable_text(row.get("short_answer")),
        "claim_delta": _nullable_text(row.get("claim_delta")),
        "variants": _json_list(row.get("variants")),
        "evidence_quotes": _json_list(row.get("evidence_quotes")),
        "source_refs": _json_list(row.get("source_refs")),
        "source_chunk_indexes": _json_list(row.get("source_chunk_indexes")),
        "confidence": _nullable_float(row.get("confidence")),
        "reason": _nullable_text(row.get("reason")),
        "created_at": _iso(row.get("created_at")),
    }


def _canonical_fact_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "fact_id": _text(row.get("fact_id")),
        "fact_key": _text(row.get("fact_key")),
        "claim": _text(row.get("claim")),
        "question_variants": _json_list(row.get("question_variants")),
        "claim_kind": _text(row.get("claim_kind")),
        "answer": _text(row.get("answer")),
        "short_answer": _text(row.get("short_answer")),
        "evidence_quotes": _json_list(row.get("evidence_quotes")),
        "source_refs": _json_list(row.get("source_refs")),
        "source_section_ids": _json_list(row.get("source_section_ids")),
        "source_chunk_indexes": _json_list(row.get("source_chunk_indexes")),
        "status": _text(row.get("status")),
        "updated_at": _iso(row.get("updated_at")),
    }


def _surface_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "surface_id": _text(row.get("surface_id")),
        "fact_id": _nullable_text(row.get("fact_id")),
        "title": _text(row.get("title")),
        "claim": _text(row.get("claim")),
        "question_variants": _json_list(row.get("question_variants")),
        "answer": _text(row.get("answer")),
        "short_answer": _text(row.get("short_answer")),
        "evidence_quotes": _json_list(row.get("evidence_quotes")),
        "source_refs": _json_list(row.get("source_refs")),
        "source_section_ids": _json_list(row.get("source_section_ids")),
        "claim_kind": _text(row.get("claim_kind")),
        "status": _text(row.get("status")),
        "curation_state": _text(row.get("curation_state")),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def _json_list(value: object) -> list[object]:
    parsed = _parse_json(value)
    if isinstance(parsed, list):
        return parsed
    if parsed is None:
        return []
    return [parsed]


def _json_dict(value: object) -> dict[str, object]:
    parsed = _parse_json(value)
    if isinstance(parsed, dict):
        return {str(key): item for key, item in parsed.items()}
    return {}


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


def _excerpt(value: str, *, limit: int = 800) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"
