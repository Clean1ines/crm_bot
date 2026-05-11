from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from src.domain.project_plane.knowledge_chunks import (
    KnowledgeChunkDraft,
    KnowledgeChunkRole,
    KnowledgeSectionPath,
)
from src.domain.project_plane.knowledge_document_structure import KnowledgeDocumentBlock
from src.domain.project_plane.knowledge_semantic_markers import (
    MARKDOWN_HEADER_PATTERN,
    MARKDOWN_HEADER_STRIP_PATTERN,
    SEMANTIC_BUILDER_VERSION,
    SEMANTIC_TAG_STOP_WORDS,
    SEMANTIC_TAG_TERM_PATTERN,
)

_MIN_DUPLICATE_TERMS = 4
_MIN_DUPLICATE_OVERLAP_RATIO = 0.70
_MIN_DUPLICATE_JACCARD = 0.45
_MIN_CONTAINED_CONTENT_CHARS = 96


@dataclass(frozen=True, slots=True)
class _SemanticCandidate:
    draft: KnowledgeChunkDraft
    title: str
    content: str
    terms: frozenset[str]


def build_knowledge_chunk_drafts(
    *,
    document_title: str,
    blocks: tuple[KnowledgeDocumentBlock, ...],
) -> tuple[KnowledgeChunkDraft, ...]:
    """Convert parser-level document blocks into canonical semantic chunk drafts."""

    drafts: list[KnowledgeChunkDraft] = []

    for block in blocks:
        title = block.title or _first_markdown_title(block.content)
        headings = block.headings
        if not headings and title:
            headings = (title,)

        metadata: dict[str, object] = dict(block.metadata)
        metadata.setdefault("semantic_builder", SEMANTIC_BUILDER_VERSION)
        metadata.setdefault("semantic_source", "source_block")

        drafts.append(
            KnowledgeChunkDraft(
                content=block.content,
                questions=_question_headings_from_content(block.content),
                title=title,
                source_excerpt=_source_excerpt_from_content(block.content),
                section_path=KnowledgeSectionPath(
                    document_title=document_title,
                    headings=headings,
                ),
                tags=_tags_from_text(title),
                metadata=metadata,
            )
        )

    return canonicalize_knowledge_chunk_drafts(
        document_title=document_title,
        drafts=tuple(drafts),
    )


def canonicalize_knowledge_chunk_drafts(
    *,
    document_title: str,
    drafts: tuple[KnowledgeChunkDraft, ...],
) -> tuple[KnowledgeChunkDraft, ...]:
    """Merge strong semantic duplicates without document-specific assumptions."""

    candidates = [
        _candidate_from_draft(draft) for draft in drafts if draft.content.strip()
    ]
    groups: list[list[_SemanticCandidate]] = []

    for candidate in candidates:
        group_index = _duplicate_group_index(groups, candidate)
        if group_index is None:
            groups.append([candidate])
        else:
            groups[group_index].append(candidate)

    return tuple(
        _draft_from_group(document_title=document_title, group=group)
        for group in groups
    )


def _candidate_from_draft(draft: KnowledgeChunkDraft) -> _SemanticCandidate:
    title = _clean_title(draft.title)
    content = draft.content.strip()
    term_surface = " ".join(
        (
            title,
            content,
            " ".join(draft.questions),
            " ".join(draft.synonyms),
            " ".join(draft.tags),
        )
    )
    return _SemanticCandidate(
        draft=draft,
        title=title,
        content=content,
        terms=_semantic_terms(term_surface),
    )


def _duplicate_group_index(
    groups: list[list[_SemanticCandidate]],
    candidate: _SemanticCandidate,
) -> int | None:
    for index, group in enumerate(groups):
        if any(_are_duplicate_candidates(existing, candidate) for existing in group):
            return index
    return None


def _are_duplicate_candidates(
    left: _SemanticCandidate,
    right: _SemanticCandidate,
) -> bool:
    if not _can_merge_candidate_roles(left, right):
        return False

    left_content = _normalized_content(left.content)
    right_content = _normalized_content(right.content)

    if left_content and left_content == right_content:
        return True

    if _is_contained_duplicate(left_content, right_content):
        return True

    left_title = _normalized_title(left.title)
    right_title = _normalized_title(right.title)
    if not left_title and not right_title:
        return False

    # Important: equal titles are not enough to merge.
    # Generic repeated headings like FAQ, Pricing, Manager, or a file name can
    # group unrelated facts into one noisy chunk. Semantic overlap must carry
    # the decision.
    return _term_sets_duplicate(left.terms, right.terms)


def _can_merge_candidate_roles(
    left: _SemanticCandidate,
    right: _SemanticCandidate,
) -> bool:
    left_role = left.draft.role
    right_role = right.draft.role

    if left_role == right_role:
        return True

    return left_role.is_answerable and right_role.is_answerable


def _is_contained_duplicate(left: str, right: str) -> bool:
    if not left or not right or left == right:
        return False

    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    return len(shorter) >= _MIN_CONTAINED_CONTENT_CHARS and shorter in longer


def _term_sets_duplicate(left: frozenset[str], right: frozenset[str]) -> bool:
    if not left or not right:
        return False

    overlap = left & right
    if len(overlap) < _MIN_DUPLICATE_TERMS:
        return False

    min_size = min(len(left), len(right))
    union_size = len(left | right)
    overlap_ratio = len(overlap) / min_size
    jaccard = len(overlap) / union_size
    return (
        overlap_ratio >= _MIN_DUPLICATE_OVERLAP_RATIO
        or jaccard >= _MIN_DUPLICATE_JACCARD
    )


def _draft_from_group(
    *,
    document_title: str,
    group: list[_SemanticCandidate],
) -> KnowledgeChunkDraft:
    title = _choose_title(group)
    content = _merge_content(group)
    metadata = _merged_metadata(group)
    metadata.setdefault("semantic_builder", SEMANTIC_BUILDER_VERSION)
    metadata["canonical_unit"] = True
    metadata["merged_source_count"] = len(group)

    tag_parts: list[Iterable[str] | str] = [candidate.draft.tags for candidate in group]
    tag_parts.append(_tags_from_text(title))

    return KnowledgeChunkDraft(
        content=content,
        role=_choose_role(group),
        title=title,
        source_excerpt=_choose_source_excerpt(group, content=content),
        section_path=KnowledgeSectionPath(
            document_title=document_title,
            headings=_choose_headings(group, title=title),
        ),
        questions=_merge_question_values(
            _merge_text_tuple(candidate.draft.questions for candidate in group),
            _questions_from_group(group=group, fallback_content=content),
        ),
        synonyms=_merge_text_tuple(candidate.draft.synonyms for candidate in group),
        tags=_merge_text_tuple(tag_parts),
        embedding_text=_choose_embedding_text(group),
        metadata=metadata,
    )


def _choose_role(group: list[_SemanticCandidate]) -> KnowledgeChunkRole:
    role_priority = (
        KnowledgeChunkRole.PRICE_LIST,
        KnowledgeChunkRole.FAQ,
        KnowledgeChunkRole.INSTRUCTION,
        KnowledgeChunkRole.RETRIEVAL_GUIDELINE,
        KnowledgeChunkRole.NEGATIVE_TEST,
        KnowledgeChunkRole.INTERNAL_EVAL_TEST,
        KnowledgeChunkRole.ANSWER_KNOWLEDGE,
    )
    roles = {candidate.draft.role for candidate in group}
    for role in role_priority:
        if role in roles:
            return role
    return group[0].draft.role


def _choose_title(group: list[_SemanticCandidate]) -> str:
    titles = [candidate.title for candidate in group if candidate.title]
    if not titles:
        return ""

    return max(titles, key=_title_score)


def _title_score(title: str) -> tuple[int, int, int]:
    words = title.split()
    question_penalty = 1 if title.strip().endswith("?") else 0
    concise_score = max(0, 16 - len(words))
    alpha_score = sum(1 for char in title if char.isalpha())
    return (-question_penalty, concise_score, alpha_score)


def _choose_headings(
    group: list[_SemanticCandidate],
    *,
    title: str,
) -> tuple[str, ...]:
    for candidate in group:
        headings = candidate.draft.section_path.headings
        if headings and (not title or title in headings):
            return headings

    if title:
        return (title,)

    for candidate in group:
        headings = candidate.draft.section_path.headings
        if headings:
            return headings

    return ()


def _merge_content(group: list[_SemanticCandidate]) -> str:
    result: list[str] = []

    for candidate in group:
        for unit in _content_units(candidate):
            _append_content_unit(result, unit)

    return "\n\n".join(result).strip()


def _content_units(candidate: _SemanticCandidate) -> list[str]:
    units: list[str] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        paragraph = " ".join(paragraph_lines).strip()
        paragraph_lines.clear()

        for unit in _split_text_units(paragraph):
            if unit:
                units.append(unit)

    for raw_line in candidate.content.split("\n"):
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue

        if re.fullmatch(r"[-*_]{3,}", line):
            flush_paragraph()
            continue

        header_unit, body_tail = _split_leading_markdown_title(
            line,
            title=candidate.title,
        )
        if header_unit:
            flush_paragraph()
            units.append(header_unit)
            for unit in _split_text_units(body_tail):
                if unit:
                    units.append(unit)
            continue

        paragraph_lines.append(line)

    flush_paragraph()
    return units


def _split_leading_markdown_title(
    line: str,
    *,
    title: str,
) -> tuple[str, str]:
    stripped = line.strip()
    if not title or not _is_markdown_header(stripped):
        return ("", "")

    clean_title = _clean_title(title)
    if not clean_title:
        return ("", "")

    match = re.match(r"^(#{1,6}\s+)(.+)$", stripped)
    if match is None:
        return ("", "")

    marker = match.group(1)
    tail = match.group(2).strip()
    if not tail:
        return ("", "")

    normalized_title = _normalized_content(clean_title)
    normalized_tail_prefix = _normalized_content(tail[: len(clean_title) + 8])
    if not normalized_title or not normalized_tail_prefix.startswith(normalized_title):
        return ("", "")

    # Use the exact title selected for the candidate, not the whole collapsed line.
    body_tail = tail[len(clean_title) :].strip()
    header_unit = f"{marker}{clean_title}".strip()
    return (header_unit, body_tail)


def _split_text_units(value: str) -> list[str]:
    text = _clean_content_part(value)
    if not text:
        return []

    parts = re.split(r"(?<=[.!?…])\s+", text)
    units = [part.strip() for part in parts if part.strip()]
    return units or [text]


def _append_content_unit(result: list[str], unit: str) -> None:
    candidate = _clean_content_part(unit)
    if not candidate:
        return

    candidate_normalized = _normalized_content(candidate)
    if not candidate_normalized:
        return

    for index, existing in enumerate(result):
        existing_normalized = _normalized_content(existing)
        if not existing_normalized:
            continue

        if candidate_normalized == existing_normalized:
            return

        if _is_substantive_containment(
            contained=candidate_normalized,
            container=existing_normalized,
        ):
            return

        if _is_substantive_containment(
            contained=existing_normalized,
            container=candidate_normalized,
        ):
            result[index] = candidate
            return

    result.append(candidate)


def _is_substantive_containment(*, contained: str, container: str) -> bool:
    return len(contained) >= 32 and contained in container


def _choose_source_excerpt(
    group: list[_SemanticCandidate],
    *,
    content: str,
) -> str:
    """Choose an excerpt without losing explicit single-source metadata.

    A single structured candidate may carry an LLM-produced source excerpt that
    is intentionally shorter than content. Merged canonical units derive their
    excerpt from merged content so the excerpt covers all merged sources.
    """

    if len(group) == 1:
        excerpt = group[0].draft.source_excerpt.strip()
        if excerpt:
            return excerpt

    if content.strip():
        return _source_excerpt_from_content(content)

    for candidate in group:
        excerpt = candidate.draft.source_excerpt.strip()
        if excerpt:
            return excerpt

    return ""


def _choose_embedding_text(group: list[_SemanticCandidate]) -> str:
    values: list[str] = []
    for candidate in group:
        embedding_text = candidate.draft.embedding_text.strip()
        if embedding_text and embedding_text not in values:
            values.append(embedding_text)

    return "\n\n".join(values)


def _merged_metadata(group: list[_SemanticCandidate]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for candidate in group:
        metadata: Mapping[str, object] = candidate.draft.metadata
        for key, value in metadata.items():
            merged.setdefault(key, value)
    return merged


def _merge_text_tuple(values: Iterable[Iterable[str] | str]) -> tuple[str, ...]:
    result: list[str] = []

    for item in values:
        candidates = (item,) if isinstance(item, str) else item
        for candidate in candidates:
            text = " ".join(candidate.strip().split())
            if text and text not in result:
                result.append(text)

    return tuple(result)


def _clean_content_part(value: str) -> str:
    lines = [
        line.rstrip()
        for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _first_markdown_title(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if _is_markdown_header(stripped):
            return _header_text(stripped)
    return ""


def _source_excerpt_from_content(content: str, *, max_chars: int = 420) -> str:
    body_lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _is_markdown_header(stripped):
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            continue
        body_lines.append(stripped)

    excerpt = " ".join(body_lines)
    if not excerpt:
        excerpt = _first_markdown_title(content) or " ".join(content.split())

    excerpt = " ".join(excerpt.split())
    if len(excerpt) <= max_chars:
        return excerpt
    return excerpt[:max_chars].rstrip() + "..."


def _tags_from_text(value: str, *, max_tags: int = 8) -> tuple[str, ...]:
    tags: list[str] = []
    for token in re.findall(SEMANTIC_TAG_TERM_PATTERN, value.lower()):
        token = token.strip("_-.")
        if len(token) < 4 or token in SEMANTIC_TAG_STOP_WORDS or token.isdigit():
            continue
        if token not in tags:
            tags.append(token)
        if len(tags) >= max_tags:
            break
    return tuple(tags)


def _semantic_terms(value: str) -> frozenset[str]:
    terms: set[str] = set()
    normalized = value.lower().replace("ё", "е")
    for token in re.findall(SEMANTIC_TAG_TERM_PATTERN, normalized):
        token = token.strip("_-.")
        if len(token) < 4 or token.isdigit() or token in SEMANTIC_TAG_STOP_WORDS:
            continue
        terms.add(token)
    return frozenset(terms)


def _clean_title(value: str) -> str:
    return " ".join(value.strip().split())


def _normalized_title(value: str) -> str:
    text = value.lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return " ".join(text.split())


def _normalized_content(value: str) -> str:
    text = value.lower().replace("ё", "е")
    text = re.sub(MARKDOWN_HEADER_STRIP_PATTERN, "", text, flags=re.MULTILINE)
    text = re.sub(r"[-*_]{3,}", " ", text)
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return " ".join(text.split())


def _questions_from_group(
    *,
    group: list[_SemanticCandidate],
    fallback_content: str,
) -> tuple[str, ...]:
    result: list[str] = []

    for candidate in group:
        for question in candidate.draft.questions:
            _append_question(result, question)

        for question in _question_headings_from_content(candidate.draft.content):
            _append_question(result, question)

    for question in _question_headings_from_content(fallback_content):
        _append_question(result, question)

    return tuple(result)


def _question_headings_from_content(content: str) -> tuple[str, ...]:
    result: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not _is_markdown_header(stripped):
            continue

        heading = _header_text(stripped)
        _append_question(result, heading)

    return tuple(result)


def _merge_question_values(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> tuple[str, ...]:
    result: list[str] = []
    for value in (*left, *right):
        _append_question(result, value)
    return tuple(result)


def _append_question(result: list[str], value: str) -> None:
    question = " ".join(value.strip().split())
    if not question:
        return
    if not _is_question_text(question):
        return
    if question not in result:
        result.append(question)


def _is_question_text(value: str) -> bool:
    return value.endswith(("?", "？"))


def _is_markdown_header(line: str) -> bool:
    return bool(re.match(MARKDOWN_HEADER_PATTERN, line.strip()))


def _header_text(line: str) -> str:
    return re.sub(MARKDOWN_HEADER_STRIP_PATTERN, "", line.strip()).strip()
