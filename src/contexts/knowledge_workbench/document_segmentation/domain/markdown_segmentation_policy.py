from dataclasses import dataclass
from hashlib import sha256
from math import ceil

from src.contexts.knowledge_workbench.document_segmentation.domain.document_segment import (
    DocumentSegment,
    DocumentSegmentKind,
)
from src.contexts.knowledge_workbench.document_segmentation.domain.segmentation_budget import (
    DocumentSegmentationBudget,
    TokenEstimator,
    estimate_tokens_roughly,
    required_segment_count,
    text_fits_segmentation_budget,
)


@dataclass(frozen=True, slots=True)
class MarkdownSegmentationCommand:
    document_key: str
    markdown_text: str
    budget: DocumentSegmentationBudget

    def __post_init__(self) -> None:
        if not isinstance(self.document_key, str) or not self.document_key.strip():
            raise ValueError("document_key must be non-empty")
        if not isinstance(self.markdown_text, str) or not self.markdown_text.strip():
            raise ValueError("markdown_text must be non-empty")
        if not isinstance(self.budget, DocumentSegmentationBudget):
            raise TypeError("budget must be DocumentSegmentationBudget")


@dataclass(frozen=True, slots=True)
class _Candidate:
    text: str
    kind: DocumentSegmentKind
    heading_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SegmentDraft:
    text: str
    kind: DocumentSegmentKind
    heading_path: tuple[str, ...]


class MarkdownSegmentationPolicy:
    def segment(
        self,
        command: MarkdownSegmentationCommand,
        *,
        token_estimator: TokenEstimator = estimate_tokens_roughly,
    ) -> tuple[DocumentSegment, ...]:
        candidates = _split_top_level_h1_candidates(command.markdown_text)
        drafts: list[_SegmentDraft] = []

        for candidate in candidates:
            estimated_tokens = token_estimator(candidate.text)
            if estimated_tokens <= command.budget.max_source_segment_tokens:
                drafts.append(
                    _SegmentDraft(
                        text=candidate.text,
                        kind=candidate.kind,
                        heading_path=candidate.heading_path,
                    )
                )
                continue

            drafts.extend(
                _split_oversized_candidate(
                    candidate=candidate,
                    budget=command.budget,
                    token_estimator=token_estimator,
                )
            )

        return tuple(
            _build_segment(
                document_key=command.document_key,
                draft=draft,
                ordinal=ordinal,
                token_estimator=token_estimator,
            )
            for ordinal, draft in enumerate(drafts)
        )


def split_marker_blocks_balanced(
    *,
    blocks: tuple[str, ...],
    target_part_count: int,
    token_estimator: TokenEstimator,
) -> tuple[str, ...]:
    if target_part_count < 2:
        raise ValueError("target_part_count must be >= 2")

    clean_blocks = tuple(block.strip() for block in blocks if block.strip())
    if not clean_blocks:
        return ()
    if len(clean_blocks) <= target_part_count:
        return clean_blocks

    block_tokens = tuple(max(1, token_estimator(block)) for block in clean_blocks)
    total_tokens = sum(block_tokens)

    parts: list[str] = []
    current_blocks: list[str] = []
    accumulated_tokens = 0

    for index, block in enumerate(clean_blocks):
        current_blocks.append(block)
        accumulated_tokens += block_tokens[index]

        if len(parts) >= target_part_count - 1:
            continue

        next_boundary = total_tokens * (len(parts) + 1) / target_part_count
        remaining_blocks = len(clean_blocks) - index - 1
        remaining_parts_after_boundary = target_part_count - len(parts) - 1

        if (
            accumulated_tokens >= next_boundary
            and remaining_blocks >= remaining_parts_after_boundary
        ):
            parts.append("\n\n".join(current_blocks).strip())
            current_blocks = []

    if current_blocks:
        parts.append("\n\n".join(current_blocks).strip())

    return tuple(part for part in parts if part.strip())


def _split_top_level_h1_candidates(markdown_text: str) -> tuple[_Candidate, ...]:
    lines = _normalize_lines(markdown_text)
    candidates: list[_Candidate] = []
    preamble_lines: list[str] = []
    current_lines: list[str] = []
    current_heading: str | None = None
    found_h1 = False

    for line in lines:
        parsed = _parse_atx_heading(line)
        is_h1 = parsed is not None and parsed[0] == 1

        if is_h1:
            found_h1 = True
            if current_lines and current_heading is not None:
                candidates.append(
                    _Candidate(
                        text="\n".join(current_lines).strip(),
                        kind=DocumentSegmentKind.SECTION,
                        heading_path=(current_heading,),
                    )
                )
            elif preamble_lines:
                preamble_text = "\n".join(preamble_lines).strip()
                if preamble_text:
                    candidates.append(
                        _Candidate(
                            text=preamble_text,
                            kind=DocumentSegmentKind.DOCUMENT_PREAMBLE,
                            heading_path=(),
                        )
                    )
                preamble_lines = []

            current_heading = parsed[1] if parsed is not None else ""
            current_lines = [line]
            continue

        if found_h1:
            current_lines.append(line)
        else:
            preamble_lines.append(line)

    if current_lines and current_heading is not None:
        candidates.append(
            _Candidate(
                text="\n".join(current_lines).strip(),
                kind=DocumentSegmentKind.SECTION,
                heading_path=(current_heading,),
            )
        )
    elif preamble_lines:
        preamble_text = "\n".join(preamble_lines).strip()
        if preamble_text:
            candidates.append(
                _Candidate(
                    text=preamble_text,
                    kind=DocumentSegmentKind.PARAGRAPH_GROUP,
                    heading_path=(),
                )
            )

    return tuple(candidates)


def _split_oversized_candidate(
    *,
    candidate: _Candidate,
    budget: DocumentSegmentationBudget,
    token_estimator: TokenEstimator,
) -> tuple[_SegmentDraft, ...]:
    estimated_tokens = token_estimator(candidate.text)
    target_count = required_segment_count(
        estimated_tokens=estimated_tokens,
        budget=budget,
    )

    lower_heading_blocks = _split_lower_heading_blocks(candidate.text)
    if candidate.heading_path and len(lower_heading_blocks) >= 2:
        lower_chunks = split_marker_blocks_balanced(
            blocks=lower_heading_blocks,
            target_part_count=target_count,
            token_estimator=token_estimator,
        )
        if lower_chunks and all(
            text_fits_segmentation_budget(
                text=chunk,
                budget=budget,
                token_estimator=token_estimator,
            )
            for chunk in lower_chunks
        ):
            return tuple(
                _SegmentDraft(
                    text=chunk,
                    kind=DocumentSegmentKind.SUBSECTION,
                    heading_path=_lower_heading_path(
                        parent_path=candidate.heading_path,
                        chunk=chunk,
                    ),
                )
                for chunk in lower_chunks
            )

    return _split_by_paragraph_or_text(
        candidate=candidate,
        budget=budget,
        target_count=target_count,
        token_estimator=token_estimator,
    )


def _split_by_paragraph_or_text(
    *,
    candidate: _Candidate,
    budget: DocumentSegmentationBudget,
    target_count: int,
    token_estimator: TokenEstimator,
) -> tuple[_SegmentDraft, ...]:
    paragraph_source = (
        _strip_leading_h1(candidate.text) if candidate.heading_path else candidate.text
    )
    paragraph_blocks = _split_paragraph_blocks(paragraph_source)

    if len(paragraph_blocks) >= 2:
        chunks = split_marker_blocks_balanced(
            blocks=paragraph_blocks,
            target_part_count=max(2, target_count),
            token_estimator=token_estimator,
        )
        return tuple(
            _SegmentDraft(
                text=chunk,
                kind=DocumentSegmentKind.SPLIT_FRAGMENT,
                heading_path=candidate.heading_path,
            )
            for chunk in chunks
        )

    fallback_source = paragraph_source if paragraph_source.strip() else candidate.text
    return tuple(
        _fallback_text_drafts(
            text=fallback_source,
            heading_path=candidate.heading_path,
            budget=budget,
            token_estimator=token_estimator,
        )
    )


def _fallback_text_drafts(
    *,
    text: str,
    heading_path: tuple[str, ...],
    budget: DocumentSegmentationBudget,
    token_estimator: TokenEstimator,
) -> tuple[_SegmentDraft, ...]:
    estimated_tokens = max(1, token_estimator(text))
    target_count = required_segment_count(
        estimated_tokens=estimated_tokens,
        budget=budget,
    )
    chunks = _split_text_balanced(text=text, target_part_count=target_count)
    return tuple(
        _SegmentDraft(
            text=chunk,
            kind=DocumentSegmentKind.SPLIT_FRAGMENT,
            heading_path=heading_path,
        )
        for chunk in chunks
        if chunk.strip()
    )


def _split_text_balanced(*, text: str, target_part_count: int) -> tuple[str, ...]:
    clean_text = text.strip()
    if target_part_count <= 1:
        return (clean_text,)

    words = clean_text.split()
    if len(words) >= target_part_count:
        words_per_chunk = ceil(len(words) / target_part_count)
        return tuple(
            " ".join(words[index : index + words_per_chunk]).strip()
            for index in range(0, len(words), words_per_chunk)
            if " ".join(words[index : index + words_per_chunk]).strip()
        )

    chunk_size = ceil(len(clean_text) / target_part_count)
    return tuple(
        clean_text[index : index + chunk_size].strip()
        for index in range(0, len(clean_text), chunk_size)
        if clean_text[index : index + chunk_size].strip()
    )


def _split_lower_heading_blocks(text: str) -> tuple[str, ...]:
    lines = _normalize_lines(text)
    if lines:
        parsed_first = _parse_atx_heading(lines[0])
        if parsed_first is not None and parsed_first[0] == 1:
            lines = lines[1:]

    blocks: list[str] = []
    current_lines: list[str] = []

    for line in lines:
        parsed = _parse_atx_heading(line)
        is_lower_heading = parsed is not None and parsed[0] > 1
        if is_lower_heading and current_lines:
            block = "\n".join(current_lines).strip()
            if block:
                blocks.append(block)
            current_lines = [line]
            continue
        current_lines.append(line)

    if current_lines:
        block = "\n".join(current_lines).strip()
        if block:
            blocks.append(block)

    return tuple(blocks)


def _strip_leading_h1(text: str) -> str:
    lines = _normalize_lines(text)
    if (
        lines
        and (parsed := _parse_atx_heading(lines[0])) is not None
        and parsed[0] == 1
    ):
        return "\n".join(lines[1:]).strip()
    return text.strip()


def _split_paragraph_blocks(text: str) -> tuple[str, ...]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []
    current_lines: list[str] = []

    for line in normalized.split("\n"):
        if line.strip():
            current_lines.append(line.rstrip())
            continue
        if current_lines:
            paragraphs.append("\n".join(current_lines).strip())
            current_lines = []

    if current_lines:
        paragraphs.append("\n".join(current_lines).strip())

    return tuple(paragraph for paragraph in paragraphs if paragraph.strip())


def _lower_heading_path(
    *,
    parent_path: tuple[str, ...],
    chunk: str,
) -> tuple[str, ...]:
    lower_titles = tuple(
        parsed[1]
        for line in _normalize_lines(chunk)
        if (parsed := _parse_atx_heading(line)) is not None and parsed[0] > 1
    )
    if len(lower_titles) == 1:
        return (*parent_path, lower_titles[0])
    if len(lower_titles) > 1:
        return (*parent_path, "mixed")
    return parent_path


def _build_segment(
    *,
    document_key: str,
    draft: _SegmentDraft,
    ordinal: int,
    token_estimator: TokenEstimator,
) -> DocumentSegment:
    text_hash = sha256(draft.text.encode("utf-8")).hexdigest()
    return DocumentSegment(
        segment_key=f"segment:{document_key}:{ordinal}:{draft.kind.value}:{text_hash}",
        kind=draft.kind,
        text=draft.text,
        heading_path=draft.heading_path,
        ordinal=ordinal,
        estimated_tokens=max(1, token_estimator(draft.text)),
    )


def _normalize_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _parse_atx_heading(line: str) -> tuple[int, str] | None:
    if not line.startswith("#"):
        return None

    marker_count = 0
    for char in line:
        if char == "#":
            marker_count += 1
            continue
        break

    if marker_count < 1 or marker_count > 6:
        return None
    if len(line) <= marker_count or line[marker_count] != " ":
        return None

    title = line[marker_count + 1 :].strip()
    if not title:
        return None
    return marker_count, title
