from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeRetrievalEntry:
    runtime_entry_id: str
    project_id: str
    fact_id: str
    claim: str
    answer_text: str
    embedding_text: str
    possible_questions: tuple[str, ...]
    source_refs: tuple[str, ...]
    visibility: str
    status: str


def runtime_entry_from_canonical_fact(
    *,
    runtime_entry_id: str,
    project_id: str,
    fact_id: str,
    claim: str,
    answer_text: str,
    embedding_text: str,
    possible_questions: tuple[str, ...] = (),
    source_refs: tuple[str, ...] = (),
    visibility: str = "public",
    status: str = "active",
) -> RuntimeRetrievalEntry:
    return RuntimeRetrievalEntry(
        runtime_entry_id=runtime_entry_id,
        project_id=project_id,
        fact_id=fact_id,
        claim=claim,
        answer_text=answer_text,
        embedding_text=embedding_text,
        possible_questions=possible_questions,
        source_refs=source_refs,
        visibility=visibility,
        status=status,
    )


__all__ = ["RuntimeRetrievalEntry", "runtime_entry_from_canonical_fact"]
