from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class PromotedQuestionRuntimeEmbeddingText:
    text: str
    text_hash: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("text must be non-empty")
        if not self.text_hash.strip():
            raise ValueError("text_hash must be non-empty")


@dataclass(frozen=True, slots=True)
class PromotedQuestionRuntimeEmbeddingTextBuilder:
    def build(
        self,
        *,
        claim: str,
        possible_questions: tuple[str, ...],
        exclusion_scope: str | None,
        existing_embedding_text: str,
    ) -> PromotedQuestionRuntimeEmbeddingText:
        claim = _require_text(claim, "claim")
        existing_embedding_text = _require_text(
            existing_embedding_text,
            "existing_embedding_text",
        )
        questions = _dedupe_texts(possible_questions)
        evidence = _extract_evidence(existing_embedding_text)
        triples = _extract_triples(existing_embedding_text)

        lines = [
            "Claim:",
            claim,
            "",
            "Possible questions:",
        ]
        if questions:
            lines.extend(f"- {question}" for question in questions)
        else:
            lines.append("-")

        if exclusion_scope is not None and exclusion_scope.strip():
            lines.extend(["", "Exclusion scope:", exclusion_scope.strip()])

        lines.extend(["", "Evidence:", evidence or "-"])
        if triples:
            lines.extend(["", "Triples:"])
            lines.extend(triples)

        text = "\n".join(lines).strip()
        return PromotedQuestionRuntimeEmbeddingText(
            text=text,
            text_hash=sha256(text.encode("utf-8")).hexdigest(),
        )


def append_question_once(
    *,
    possible_questions: tuple[str, ...],
    question: str,
) -> tuple[str, ...]:
    return _dedupe_texts((*possible_questions, question))


def _dedupe_texts(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if not stripped:
            continue
        normalized = " ".join(stripped.casefold().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(stripped)
    return tuple(result)


def _extract_evidence(existing_embedding_text: str) -> str:
    marker = "\nEvidence:\n"
    if marker not in existing_embedding_text:
        return "-"
    after = existing_embedding_text.split(marker, 1)[1]
    if "\nTriples:\n" in after:
        after = after.split("\nTriples:\n", 1)[0]
    stripped = after.strip()
    return stripped or "-"


def _extract_triples(existing_embedding_text: str) -> tuple[str, ...]:
    marker = "\nTriples:\n"
    if marker not in existing_embedding_text:
        return ()
    after = existing_embedding_text.split(marker, 1)[1]
    return tuple(line.strip() for line in after.splitlines() if line.strip())


def _require_text(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be non-empty")
    return stripped
