from __future__ import annotations

import json
from typing import Protocol


class StageHRowLookup(Protocol):
    def __getitem__(self, key: str) -> object: ...


def _stage_h_int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def stage_h_json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return {str(key): item for key, item in parsed.items()}
    return {}


def stage_h_text_list(value: object) -> list[str]:
    if isinstance(value, str):
        text = " ".join(value.strip().split())
        return [text] if text else []
    if not isinstance(value, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item or "").strip().split())
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def stage_h_entry_snapshot(row: StageHRowLookup) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "document_id": str(row["document_id"]) if row["document_id"] else None,
        "compiler_run_id": str(row["compiler_run_id"] or ""),
        "stable_key": str(row["stable_key"]),
        "entry_kind": str(row["entry_kind"]),
        "title": str(row["title"]),
        "answer": str(row["answer"]),
        "status": str(row["status"]),
        "visibility": str(row["visibility"]),
        "version": _stage_h_int(row["version"]),
        "compiler_version": str(row["compiler_version"] or ""),
        "embedding_text": str(row["embedding_text"] or ""),
        "embedding_text_version": str(row["embedding_text_version"] or ""),
        "enrichment": stage_h_json_object(row["enrichment"]),
        "metadata": stage_h_json_object(row["metadata"]),
    }


def stage_h_attached_questions(
    *,
    enrichment: dict[str, object],
    metadata: dict[str, object],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for key in ("questions", "positive_questions", "synonyms", "tags"):
        for value in stage_h_text_list(enrichment.get(key)):
            if value not in seen:
                seen.add(value)
                result.append(value)

    stage_h = stage_h_json_object(metadata.get("stage_h"))
    raw_attached = stage_h.get("attached_questions")
    if isinstance(raw_attached, list):
        for item in raw_attached:
            if not isinstance(item, dict):
                continue
            question = " ".join(str(item.get("question") or "").strip().split())
            if question and question not in seen:
                seen.add(question)
                result.append(question)

    return result


def stage_h_embedding_text(row: StageHRowLookup) -> str:
    enrichment = stage_h_json_object(row["enrichment"])
    metadata = stage_h_json_object(row["metadata"])
    parts = [
        str(row["title"] or "").strip(),
        str(row["answer"] or "").strip(),
        str(row["embedding_text"] or "").strip(),
        *stage_h_attached_questions(enrichment=enrichment, metadata=metadata),
    ]

    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = " ".join(part.split())
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)

    return "\n".join(result)


def stage_h_search_text(
    *,
    title: str,
    answer: str,
    embedding_text: str,
) -> str:
    parts = (title, answer, embedding_text)
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = " ".join(part.strip().split())
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return "\n".join(result)
