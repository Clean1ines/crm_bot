from __future__ import annotations

from dataclasses import replace
import re
from typing import Literal, Sequence

from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingEntry, build_embedding_text
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilationExecutionResult,
    RetrievalSurfaceCompilationResult,
    RetrievalSurfaceDraft,
    RetrievalSurfaceGraph,
    RetrievalSurfaceRelation,
    RetrievalSurfaceSourceUnit,
    SurfaceQuestionOwnership,
    SurfaceQuestionReassignment,
)

SurfaceKind = Literal[
    "umbrella",
    "child",
    "specific",
    "standalone",
    "definition",
    "procedural",
    "safety",
    "handoff",
    "pricing",
    "integration",
    "channel",
    "document_upload",
    "curation",
    "retrieval_quality",
    "other",
]

RelationType = Literal[
    "umbrella_contains",
    "specializes",
    "sibling",
    "duplicates",
    "overlaps",
    "contradicts",
    "unrelated",
]


_SERVICE_LABELS = {
    "короткий ответ клиенту",
    "короткий ответ",
    "ожидаемая тема",
    "о продукте",
    "о знаниях",
    "о поиске",
    "о telegram",
    "о web-widget",
    "о crm",
    "негативные тесты",
}

_SHORT_ANSWER_RE = re.compile(r"^\s*короткий ответ(?:\s+клиенту)?\s*:\s*(.+)$", re.IGNORECASE)
_EXPECTED_TOPIC_RE = re.compile(r"^\s*ожидаемая тема\s*:\s*(.+)$", re.IGNORECASE)
_QUESTION_BULLET_RE = re.compile(r"^\s*[-•*]\s*(.+)$")


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_service_label(title: str) -> bool:
    return _normalize(title).lower() in _SERVICE_LABELS


def _surface_key(title: str) -> str:
    return f"surface:{_normalize(title).lower()}"


def _canonical_question(title: str) -> str:
    return f"Что такое {title}?"


def _extract_short_answer(lines: Sequence[str]) -> str:
    for line in lines:
        match = _SHORT_ANSWER_RE.match(line)
        if match:
            return _normalize(match.group(1))
    return ""


def _extract_expected_topic_hint(lines: Sequence[str]) -> str:
    for line in lines:
        match = _EXPECTED_TOPIC_RE.match(line)
        if match:
            return _normalize(match.group(1))
    return ""


def _extract_question_candidates(lines: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    for line in lines:
        candidate = line
        bullet = _QUESTION_BULLET_RE.match(line)
        if bullet:
            candidate = bullet.group(1)
        if "?" not in candidate:
            continue
        cleaned = _normalize(candidate)
        if cleaned:
            out.append(cleaned)
    return tuple(dict.fromkeys(out))


def _child_kind_for_title(title: str) -> SurfaceKind:
    lowered = title.lower()
    if "widget" in lowered or "web-widget" in lowered or "интеграц" in lowered:
        return "integration"
    if "telegram" in lowered or "канал" in lowered:
        return "channel"
    if "загруз" in lowered or "pdf" in lowered:
        return "document_upload"
    if "курац" in lowered or "merge" in lowered or "слияни" in lowered:
        return "curation"
    if "поиск" in lowered or "retrieval" in lowered:
        return "retrieval_quality"
    return "specific"


def discover_retrieval_surfaces_from_source_unit(
    unit: RetrievalSurfaceSourceUnit,
) -> tuple[RetrievalSurfaceDraft, ...]:
    if not isinstance(unit, RetrievalSurfaceSourceUnit):
        raise TypeError("surface discovery requires RetrievalSurfaceSourceUnit")

    text = unit.raw_text or f"{unit.title}\n{unit.body}"
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    title = _normalize(unit.title or (lines[0].lstrip("# ") if lines else "Тема"))
    umbrella_key = _surface_key(title)

    expected_topic_hint = _extract_expected_topic_hint(lines)
    metadata: dict[str, object] = {
        "source_unit_key": unit.source_unit_key,
        "expected_topic_hint": expected_topic_hint,
    }

    drafts: list[RetrievalSurfaceDraft] = [
        RetrievalSurfaceDraft(
            local_surface_key=umbrella_key,
            title=title,
            canonical_question=_canonical_question(title),
            surface_kind="umbrella",
            answer_scope=title,
            question_scope=title,
            exclusion_scope="service_labels",
            source_excerpt=text,
            source_chunk_indexes=unit.source_chunk_indexes,
            metadata=metadata,
        )
    ]

    for line in lines:
        if _SHORT_ANSWER_RE.match(line) or _EXPECTED_TOPIC_RE.match(line):
            continue
        if not (line.startswith("###") or line.startswith("##")):
            continue
        child_title = _normalize(line.lstrip("# "))
        if not child_title or child_title == title or _is_service_label(child_title):
            continue
        child_key = _surface_key(child_title)
        drafts.append(
            RetrievalSurfaceDraft(
                local_surface_key=child_key,
                title=child_title,
                canonical_question=_canonical_question(child_title),
                surface_kind=_child_kind_for_title(child_title),
                answer_scope=child_title,
                question_scope=child_title,
                exclusion_scope=title,
                parent_candidate_keys=(umbrella_key,),
                source_excerpt=text,
                source_chunk_indexes=unit.source_chunk_indexes,
                metadata=metadata,
            )
        )

    return tuple(drafts)


def plan_retrieval_surface_relations(
    surfaces: Sequence[RetrievalSurfaceDraft],
) -> tuple[RetrievalSurfaceRelation, ...]:
    relations: list[RetrievalSurfaceRelation] = []
    surface_keys = {surface.local_surface_key for surface in surfaces}

    for surface in surfaces:
        for parent_key in surface.parent_candidate_keys:
            if parent_key in surface_keys:
                relations.append(
                    RetrievalSurfaceRelation(
                        parent_key=parent_key,
                        child_key=surface.local_surface_key,
                        relation_type="umbrella_contains",
                        reason="explicit parent candidate",
                        confidence=0.9,
                    )
                )

    return tuple(relations)


def synthesize_retrieval_surface_answers(
    unit: RetrievalSurfaceSourceUnit,
    surface: RetrievalSurfaceDraft,
    relations: Sequence[RetrievalSurfaceRelation],
) -> RetrievalSurfaceDraft:
    del relations  # локальная детерминированная версия пока не использует контекст напрямую

    text = unit.raw_text or unit.body
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    short_answer = _extract_short_answer(lines)

    answer_lines = [
        line
        for line in lines
        if not _SHORT_ANSWER_RE.match(line) and not _EXPECTED_TOPIC_RE.match(line)
    ]
    answer = _normalize(" ".join(answer_lines))
    if short_answer and short_answer not in answer:
        answer = _normalize(f"{answer} {short_answer}")

    return replace(
        surface,
        answer=answer,
        short_answer=short_answer,
        source_refs=unit.source_refs or (unit.source_unit_key,),
    )


def assign_retrieval_surface_questions(
    surfaces: Sequence[RetrievalSurfaceDraft],
    questions: Sequence[str],
) -> tuple[RetrievalSurfaceDraft, ...]:
    normalized_questions = tuple(_normalize(q) for q in questions if _normalize(q))
    result: list[RetrievalSurfaceDraft] = []

    for surface in surfaces:
        title_tokens = tuple(token for token in surface.title.lower().split() if len(token) > 2)
        owned: list[str] = []
        rejected: list[str] = []

        for question in normalized_questions:
            lowered = question.lower()
            if surface.surface_kind == "umbrella":
                if any(term in lowered for term in ("что это", "зачем", "для чего", "чем вы")):
                    owned.append(question)
                else:
                    rejected.append(question)
                continue

            if surface.title.lower() in lowered or any(token in lowered for token in title_tokens[:3]):
                owned.append(question)
            else:
                rejected.append(question)

        result.append(
            replace(
                surface,
                owned_questions=tuple(dict.fromkeys(owned)),
                rejected_or_reassigned_questions=tuple(SurfaceQuestionReassignment(question=q, target_surface_key="", reason="reassigned") for q in dict.fromkeys(rejected)),
            )
        )

    return tuple(result)


def merge_same_surface_drafts(
    surfaces: Sequence[RetrievalSurfaceDraft],
    relations: Sequence[RetrievalSurfaceRelation],
) -> tuple[RetrievalSurfaceDraft, ...]:
    del relations

    by_title: dict[str, RetrievalSurfaceDraft] = {}
    for surface in surfaces:
        title_key = surface.title.lower()
        existing = by_title.get(title_key)
        if existing is None:
            by_title[title_key] = surface
            continue

        merged_questions = tuple(
            dict.fromkeys(existing.owned_questions + surface.owned_questions)
        )
        merged_rejected = tuple(
            dict.fromkeys(
                existing.rejected_or_reassigned_questions
                + surface.rejected_or_reassigned_questions
            )
        )
        merged_answer = (
            existing.answer
            if len(existing.answer) >= len(surface.answer)
            else surface.answer
        )

        by_title[title_key] = replace(
            existing,
            answer=merged_answer,
            owned_questions=merged_questions,
            rejected_or_reassigned_questions=merged_rejected,
        )

    return tuple(by_title.values())


def project_surfaces_to_preprocessing_entries(
    surfaces: Sequence[RetrievalSurfaceDraft],
    source_chunk_indexes: tuple[int, ...] = (),
) -> tuple[KnowledgePreprocessingEntry, ...]:
    entries: list[KnowledgePreprocessingEntry] = []

    for surface in surfaces:
        indexes = surface.source_chunk_indexes or source_chunk_indexes
        entry = KnowledgePreprocessingEntry(
            title=surface.title,
            canonical_question=surface.canonical_question,
            answer=surface.answer or surface.short_answer,
            source_excerpt=surface.source_excerpt,
            questions=surface.owned_questions,
            embedding_text="",
            source_chunk_indexes=indexes,
            tags=(f"surface_kind:{surface.surface_kind}",),
            synonyms=surface.relation_hints,
        )
        entries.append(replace(entry, embedding_text=build_embedding_text(entry)))

    return tuple(entries)


def extract_questions_from_source_unit(unit: RetrievalSurfaceSourceUnit) -> tuple[str, ...]:
    lines = tuple(line.strip() for line in (unit.raw_text or unit.body).splitlines() if line.strip())
    return _extract_question_candidates(lines)


class DeterministicKnowledgeSurfaceCompiler:
    model_name = "deterministic-surface-compiler"

    async def compile_surfaces(self, *, mode, source_units, file_name):
        del file_name
        all_surfaces=[]
        all_relations=[]
        ownership=[]
        for unit in source_units:
            discovered=discover_retrieval_surfaces_from_source_unit(unit)
            relations=plan_retrieval_surface_relations(discovered)
            synthesized=tuple(synthesize_retrieval_surface_answers(unit,s,relations) for s in discovered)
            questions=extract_questions_from_source_unit(unit)
            assigned=assign_retrieval_surface_questions(synthesized,questions)
            for surf in assigned:
                for q in surf.owned_questions:
                    ownership.append(SurfaceQuestionOwnership(question=q,owner_surface_key=surf.local_surface_key,question_kind="user_like_question",confidence=0.6,reason="deterministic_score",rejected_from_surface_keys=tuple(r.target_surface_key for r in surf.rejected_or_reassigned_questions)))
            merged=merge_same_surface_drafts(assigned,relations)
            all_surfaces.extend(merged)
            all_relations.extend(relations)
        projected=project_surfaces_to_preprocessing_entries(tuple(all_surfaces))
        graph=RetrievalSurfaceGraph(source_unit_keys=tuple(u.source_unit_key for u in source_units),surfaces=tuple(all_surfaces),relations=tuple(all_relations),question_ownership=tuple(ownership),metrics={"compiler":"deterministic"})
        result=RetrievalSurfaceCompilationResult(mode=mode,prompt_version="retrieval_surface_compiler_v1",model=self.model_name,graph=graph,projected_entries=projected,metrics={"surface_count":len(all_surfaces)})
        return RetrievalSurfaceCompilationExecutionResult(result=result,usage=None)
