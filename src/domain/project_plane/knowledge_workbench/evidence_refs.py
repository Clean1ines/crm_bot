from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class WorkbenchEvidenceRef:
    source_type: str
    source_id: str
    quote: str
    section_id: str | None = None
    source_row_id: str | None = None

    @property
    def normalized_quote(self) -> str:
        return normalize_evidence_quote(self.quote)


def normalize_evidence_quote(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "").strip())


def evidence_ref_fingerprint(ref: WorkbenchEvidenceRef) -> str:
    payload = "|".join(
        (
            ref.source_type.strip().casefold(),
            ref.source_id.strip(),
            ref.section_id or "",
            ref.source_row_id or "",
            ref.normalized_quote.casefold(),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dedupe_evidence_refs(
    refs: tuple[WorkbenchEvidenceRef, ...],
) -> tuple[WorkbenchEvidenceRef, ...]:
    retained: list[WorkbenchEvidenceRef] = []
    seen: set[str] = set()

    for ref in refs:
        fingerprint = evidence_ref_fingerprint(ref)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        retained.append(ref)

    return tuple(retained)


def evidence_refs_are_grounded(refs: tuple[WorkbenchEvidenceRef, ...]) -> bool:
    return all(
        ref.source_type and ref.source_id and ref.normalized_quote for ref in refs
    )


def require_grounded_evidence(
    refs: tuple[WorkbenchEvidenceRef, ...],
    *,
    context: str,
) -> None:
    if not refs:
        raise ValueError(f"{context} must have at least one evidence ref")
    if not evidence_refs_are_grounded(refs):
        raise ValueError(f"{context} contains ungrounded evidence refs")
