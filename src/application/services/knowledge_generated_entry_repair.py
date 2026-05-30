from __future__ import annotations

import re
from dataclasses import replace

from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    build_embedding_text,
)


KCD_STAGE_K_ANSWER_DIGEST_MAX_CHARS = 220
KCD_STAGE_K8_ANSWER_RESOLUTION_MIN_TOKEN_CHARS = 3


def _clean_optional_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def answer_digest(
    value: str,
    *,
    max_chars: int = KCD_STAGE_K_ANSWER_DIGEST_MAX_CHARS,
) -> str:
    text = _clean_optional_text(value)
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars].rsplit(" ", 1)[0].strip()
    return trimmed or text[:max_chars].strip()


def tokenize_answer_resolution_text(value: str) -> tuple[str, ...]:
    text = value.lower().replace("ё", "е")
    tokens = (
        token
        for token in re.findall(r"[0-9a-zа-я]+", text)
        if len(token) >= KCD_STAGE_K8_ANSWER_RESOLUTION_MIN_TOKEN_CHARS
    )
    return tuple(dict.fromkeys(tokens))


def _source_answer_coverage_ratio(answer: str, source_excerpt: str) -> float:
    answer_tokens = set(tokenize_answer_resolution_text(answer))
    source_tokens = set(tokenize_answer_resolution_text(source_excerpt))
    if not source_tokens:
        return 1.0
    if not answer_tokens:
        return 0.0
    overlap = len(answer_tokens & source_tokens)
    return overlap / max(1, min(len(source_tokens), 36))


def _entry_has_markdown_heading(answer: str) -> bool:
    return any(line.lstrip().startswith("#") for line in answer.splitlines())


def _strip_markdown_heading_markers(answer: str) -> str:
    lines: list[str] = []
    for line in answer.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            repaired = re.sub(r"^\s*#{1,6}\s*", "", line).strip()
            if repaired:
                lines.append(repaired)
            continue
        lines.append(line)
    return _clean_optional_text("\n".join(lines))


def _remove_forbidden_cjk_korean_chars(value: str) -> str:
    return re.sub(r"[一-鿿가-힯]", "", value)


def _strip_service_labels(value: str) -> str:
    repaired = re.sub(
        r"\b(?:expected[\s_-]*topic|test[\s_-]*label)\s*[:：-]*\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return _clean_optional_text(repaired)


def _strip_conversational_prefix(answer: str) -> str:
    repaired = re.sub(
        r"^\s*(?:привет(?:ствую)?|здравствуйте|hello|hi)\s*[,!.\-:;–—]*\s*",
        "",
        answer,
        flags=re.IGNORECASE,
    )
    return _clean_optional_text(repaired)


def repair_generated_entry(
    entry: KnowledgePreprocessingEntry,
    *,
    source_excerpt: str,
) -> tuple[KnowledgePreprocessingEntry, tuple[str, ...]]:
    warnings: list[str] = []
    source_has_cjk = re.search(r"[一-鿿가-힯]", source_excerpt) is not None

    repaired = entry
    repaired_answer = repaired.answer
    if _entry_has_markdown_heading(repaired_answer):
        repaired_answer = _strip_markdown_heading_markers(repaired_answer)
        warnings.append("generated_answer_markdown_heading_repaired")

    answer_without_labels = _strip_service_labels(repaired_answer)
    if answer_without_labels != repaired_answer:
        repaired_answer = answer_without_labels
        warnings.append("generated_answer_service_label_repaired")

    answer_without_prefix = _strip_conversational_prefix(repaired_answer)
    if answer_without_prefix != repaired_answer:
        repaired_answer = answer_without_prefix
        warnings.append("generated_answer_conversational_prefix_repaired")

    if not source_has_cjk:
        answer_without_cjk = _remove_forbidden_cjk_korean_chars(repaired_answer)
        if answer_without_cjk != repaired_answer:
            repaired_answer = _clean_optional_text(answer_without_cjk)
            warnings.append("generated_answer_forbidden_script_repaired")

    repaired = replace(repaired, answer=repaired_answer)

    source_ru = len(re.findall(r"[Ѐ-ӿ]", source_excerpt))
    source_latin = len(re.findall(r"[A-Za-z]", source_excerpt))
    answer_ru = len(re.findall(r"[Ѐ-ӿ]", repaired.answer))
    answer_latin = len(re.findall(r"[A-Za-z]", repaired.answer))
    if source_ru > source_latin and answer_ru < answer_latin:
        warnings.append("answer_language_mismatch_warning")

    coverage = _source_answer_coverage_ratio(repaired.answer, source_excerpt)
    if coverage < 0.45:
        warnings.append("generated_answer_low_coverage_warning")

    if not source_has_cjk:
        sanitized_title = _clean_optional_text(
            _remove_forbidden_cjk_korean_chars(repaired.title)
        )
        sanitized_canonical_question = _clean_optional_text(
            _remove_forbidden_cjk_korean_chars(repaired.canonical_question)
        )
        sanitized_source_excerpt = _clean_optional_text(
            _remove_forbidden_cjk_korean_chars(repaired.source_excerpt)
        )
        sanitized_questions = tuple(
            cleaned
            for item in repaired.questions
            if (
                cleaned := _clean_optional_text(
                    _remove_forbidden_cjk_korean_chars(item)
                )
            )
        )
        sanitized_synonyms = tuple(
            cleaned
            for item in repaired.synonyms
            if (
                cleaned := _clean_optional_text(
                    _remove_forbidden_cjk_korean_chars(item)
                )
            )
        )
        sanitized_tags = tuple(
            cleaned
            for item in repaired.tags
            if (
                cleaned := _clean_optional_text(
                    _remove_forbidden_cjk_korean_chars(item)
                )
            )
        )

        if (
            sanitized_title != repaired.title
            or sanitized_canonical_question != repaired.canonical_question
            or sanitized_source_excerpt != repaired.source_excerpt
            or sanitized_questions != repaired.questions
            or sanitized_synonyms != repaired.synonyms
            or sanitized_tags != repaired.tags
        ):
            warnings.append("generated_enrichment_forbidden_script_repaired")
            repaired = replace(
                repaired,
                title=sanitized_title,
                canonical_question=sanitized_canonical_question,
                source_excerpt=sanitized_source_excerpt,
                questions=sanitized_questions,
                synonyms=sanitized_synonyms,
                tags=sanitized_tags,
            )

    repaired_source_excerpt = _clean_optional_text(repaired.source_excerpt)
    repaired_answer = _clean_optional_text(repaired.answer)
    if not repaired_source_excerpt:
        repaired_source_excerpt = _clean_optional_text(source_excerpt)
        warnings.append("generated_source_excerpt_empty_after_repair_warning")
    if not repaired_answer:
        fallback_answer = answer_digest(repaired_source_excerpt or source_excerpt)
        repaired_answer = fallback_answer
        warnings.append("generated_answer_empty_after_repair_warning")

    repaired = replace(
        repaired,
        answer=repaired_answer,
        source_excerpt=repaired_source_excerpt,
    )
    repaired = replace(repaired, embedding_text=build_embedding_text(repaired))
    return repaired, tuple(warnings)
