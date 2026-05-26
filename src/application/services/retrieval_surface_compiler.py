from __future__ import annotations

from dataclasses import replace
import re
from typing import Sequence

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

_SERVICE_LABELS = {"короткий ответ клиенту", "короткий ответ", "ожидаемая тема", "о продукте", "о знаниях", "о поиске", "о telegram", "о web-widget", "о crm", "негативные тесты"}
_SHORT_ANSWER_RE = re.compile(r"^\s*короткий ответ(?:\s+клиенту)?\s*:\s*(.+)$", re.IGNORECASE)
_EXPECTED_TOPIC_RE = re.compile(r"^\s*ожидаемая тема\s*:\s*(.+)$", re.IGNORECASE)
_QUESTION_BULLET_RE = re.compile(r"^\s*[-•*]\s*(.+)$")


def _normalize(v: str) -> str:
    return re.sub(r"\s+", " ", v).strip()


def _surface_key(title: str) -> str:
    return f"surface:{_normalize(title).lower()}"


def _canonical_question(title: str) -> str:
    return f"Что такое {title}?"


def _kind(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ("цена", "стоим", "тариф")):
        return "pricing"
    if "возврат" in t:
        return "refund"
    if any(k in t for k in ("оплат", "payment")):
        return "payment"
    if any(k in t for k in ("widget", "web-widget", "интеграц", "crm")):
        return "integration"
    if any(k in t for k in ("telegram", "канал")):
        return "channel"
    if any(k in t for k in ("загруз", "pdf")):
        return "document_upload"
    if any(k in t for k in ("курац", "слияни", "архив", "hide", "merge")):
        return "curation"
    if "поиск" in t:
        return "retrieval_quality"
    if any(k in t for k in ("огранич", "риск", "гарант")):
        return "service_limits"
    return "specific"


def discover_retrieval_surfaces_from_source_unit(unit: RetrievalSurfaceSourceUnit) -> tuple[RetrievalSurfaceDraft, ...]:
    if not isinstance(unit, RetrievalSurfaceSourceUnit):
        raise TypeError("surface discovery requires RetrievalSurfaceSourceUnit")
    text = unit.raw_text or f"{unit.title}\n{unit.body}"
    umbrella = RetrievalSurfaceDraft(
        local_surface_key=_surface_key(unit.title),
        title=_normalize(unit.title),
        canonical_question=_canonical_question(unit.title),
        surface_kind="umbrella",
        answer_scope=unit.title,
        question_scope=unit.title,
        exclusion_scope="service_labels",
        source_excerpt=text,
        source_chunk_indexes=unit.source_chunk_indexes,
        metadata={"source_unit_key": unit.source_unit_key},
    )
    drafts = [umbrella]

    # priority: structured children
    for child in unit.children:
        title = _normalize(child.title)
        if not title or title.lower() in _SERVICE_LABELS or child.label_kind in {"service_label", "short_answer", "expected_topic"}:
            continue
        drafts.append(
            RetrievalSurfaceDraft(
                local_surface_key=_surface_key(title),
                title=title,
                canonical_question=_canonical_question(title),
                surface_kind=_kind(title),
                answer_scope=title,
                question_scope=title,
                exclusion_scope=unit.title,
                source_excerpt=child.raw_text or child.body,
                parent_candidate_keys=(umbrella.local_surface_key,),
                source_chunk_indexes=unit.source_chunk_indexes,
                metadata={"source_unit_key": unit.source_unit_key, "from_children": True},
            )
        )

    if unit.title.lower() == "негативные тесты":
        for t in ("Ограничения автономности ассистента", "Когда ассистент передаёт вопрос менеджеру", "Рискованные вопросы"):
            drafts.append(
                RetrievalSurfaceDraft(_surface_key(t), t, _canonical_question(t), "safety", t, t, unit.title, source_excerpt=text, parent_candidate_keys=(umbrella.local_surface_key,), source_chunk_indexes=unit.source_chunk_indexes, metadata={"synthetic_from_negative_tests": True})
            )
    return tuple(drafts)


def plan_retrieval_surface_relations(surfaces: Sequence[RetrievalSurfaceDraft]) -> tuple[RetrievalSurfaceRelation, ...]:
    keys = {s.local_surface_key for s in surfaces}
    out: list[RetrievalSurfaceRelation] = []
    for s in surfaces:
        for p in s.parent_candidate_keys:
            if p in keys:
                out.append(RetrievalSurfaceRelation(p, s.local_surface_key, "umbrella_contains", "parent candidate", 0.9, ()))
    return tuple(out)


def synthesize_retrieval_surface_answers(unit: RetrievalSurfaceSourceUnit, surface: RetrievalSurfaceDraft, relations: Sequence[RetrievalSurfaceRelation]) -> RetrievalSurfaceDraft:
    del relations
    short = ""
    for line in (unit.raw_text or "").splitlines():
        m = _SHORT_ANSWER_RE.match(line.strip())
        if m:
            short = _normalize(m.group(1))
            break

    if surface.surface_kind == "umbrella":
        base = _normalize(unit.body or unit.title)
    else:
        base = ""
        for child in unit.children:
            if _normalize(child.title).lower() == surface.title.lower():
                base = _normalize(child.body or child.raw_text)
                break
        if not base:
            base = _normalize(surface.answer_scope)
    answer = base
    if surface.surface_kind == "umbrella" and short:
        answer = _normalize(f"{answer}. {short}")
    return replace(surface, answer=answer, short_answer=short if surface.surface_kind == "umbrella" else "", source_refs=unit.source_refs or (unit.source_unit_key,))


def extract_questions_from_source_unit(unit: RetrievalSurfaceSourceUnit) -> tuple[str, ...]:
    out: list[str] = []
    for line in (unit.raw_text or unit.body).splitlines():
        m = _QUESTION_BULLET_RE.match(line.strip())
        candidate = m.group(1) if m else line.strip()
        if "?" in candidate:
            out.append(_normalize(candidate))
    return tuple(dict.fromkeys(q for q in out if q))


def _score(surface: RetrievalSurfaceDraft, question: str, relations: Sequence[RetrievalSurfaceRelation]) -> float:
    q = question.lower()
    score = 0.0
    if surface.title.lower() in q:
        score += 4
    for t in surface.question_scope.lower().split():
        if len(t) > 3 and t in q:
            score += 1.2
    for t in surface.answer_scope.lower().split():
        if len(t) > 3 and t in q:
            score += 1
    if surface.exclusion_scope and surface.exclusion_scope.lower() in q:
        score -= 1
    if surface.surface_kind == "umbrella" and any(k in q for k in ("что это", "чем вы", "для чего")):
        score += 2
    if surface.surface_kind != "umbrella" and any(k in q for k in ("как", "можно", "где", "есть ли")):
        score += 1
    if any(r.child_key == surface.local_surface_key and r.relation_type in {"umbrella_contains", "specializes"} for r in relations):
        score += 0.3
    return score


def assign_retrieval_surface_questions(surfaces: Sequence[RetrievalSurfaceDraft], questions: Sequence[str], relations: Sequence[RetrievalSurfaceRelation] = ()) -> tuple[RetrievalSurfaceDraft, ...]:
    assigned = {s.local_surface_key: [] for s in surfaces}
    rejected = {s.local_surface_key: [] for s in surfaces}
    for q in (_normalize(i) for i in questions if _normalize(i)):
        ranked = sorted(((s.local_surface_key, _score(s, q, relations)) for s in surfaces), key=lambda x: x[1], reverse=True)
        winner, wscore = ranked[0]
        if wscore <= 0:
            continue
        assigned[winner].append(q)
        for sid, _ in ranked[1:]:
            rejected[sid].append(SurfaceQuestionReassignment(question=q, target_surface_key=winner, reason="lower_score"))

    by_id = {s.local_surface_key: s for s in surfaces}
    out = []
    for sid, surface in by_id.items():
        out.append(replace(surface, owned_questions=tuple(dict.fromkeys(assigned[sid])), rejected_or_reassigned_questions=tuple(rejected[sid])))
    return tuple(out)


def merge_same_surface_drafts(surfaces: Sequence[RetrievalSurfaceDraft], relations: Sequence[RetrievalSurfaceRelation]) -> tuple[RetrievalSurfaceDraft, ...]:
    blocked_pairs = {(r.parent_key, r.child_key) for r in relations if r.relation_type in {"umbrella_contains", "specializes"}}
    merged: list[RetrievalSurfaceDraft] = []
    for s in surfaces:
        found = None
        for i, e in enumerate(merged):
            same_scope = e.surface_kind == s.surface_kind and e.answer_scope.lower() == s.answer_scope.lower()
            same_id = e.local_surface_key == s.local_surface_key
            blocked = (e.local_surface_key, s.local_surface_key) in blocked_pairs or (s.local_surface_key, e.local_surface_key) in blocked_pairs
            if (same_id or same_scope) and not blocked:
                found = i
                break
        if found is None:
            merged.append(s)
            continue
        e = merged[found]
        merged[found] = replace(e, answer=e.answer if len(e.answer) >= len(s.answer) else s.answer, owned_questions=tuple(dict.fromkeys(e.owned_questions + s.owned_questions)))
    return tuple(merged)


def project_surfaces_to_preprocessing_entries(surfaces: Sequence[RetrievalSurfaceDraft], source_chunk_indexes: tuple[int, ...] = ()) -> tuple[KnowledgePreprocessingEntry, ...]:
    entries = []
    for s in surfaces:
        indexes = s.source_chunk_indexes or source_chunk_indexes
        entry = KnowledgePreprocessingEntry(
            title=s.title,
            canonical_question=s.canonical_question,
            answer=s.answer or s.short_answer,
            source_excerpt=s.source_excerpt,
            questions=s.owned_questions,
            embedding_text="",
            source_chunk_indexes=indexes,
            tags=(f"surface_key:{s.local_surface_key}", f"surface_kind:{s.surface_kind}", f"answer_scope:{s.answer_scope}"),
            synonyms=s.relation_hints,
        )
        entries.append(replace(entry, embedding_text=build_embedding_text(entry)))
    return tuple(entries)


class DeterministicKnowledgeSurfaceCompiler:
    model_name = "deterministic-surface-compiler"

    async def compile_surfaces(self, *, mode, source_units, file_name):
        del file_name
        all_surfaces: list[RetrievalSurfaceDraft] = []
        all_relations: list[RetrievalSurfaceRelation] = []
        ownership: list[SurfaceQuestionOwnership] = []
        questions_total = 0
        for unit in source_units:
            discovered = discover_retrieval_surfaces_from_source_unit(unit)
            relations = plan_retrieval_surface_relations(discovered)
            synthesized = tuple(synthesize_retrieval_surface_answers(unit, s, relations) for s in discovered)
            questions = extract_questions_from_source_unit(unit)
            questions_total += len(questions)
            assigned = assign_retrieval_surface_questions(synthesized, questions, relations)
            for surf in assigned:
                for q in surf.owned_questions:
                    ownership.append(SurfaceQuestionOwnership(q, surf.local_surface_key, "user_like_question", 0.7, "relation_scope_scoring", tuple(r.target_surface_key for r in surf.rejected_or_reassigned_questions)))
            merged = merge_same_surface_drafts(assigned, relations)
            all_surfaces.extend(merged)
            all_relations.extend(relations)
        projected = project_surfaces_to_preprocessing_entries(tuple(all_surfaces))
        graph = RetrievalSurfaceGraph(
            source_unit_keys=tuple(u.source_unit_key for u in source_units),
            surfaces=tuple(all_surfaces),
            relations=tuple(all_relations),
            question_ownership=tuple(ownership),
            metrics={
                "compiler": "deterministic",
                "source_unit_count": len(source_units),
                "surface_count": len(all_surfaces),
                "relation_count": len(all_relations),
                "question_count": questions_total,
                "owned_question_count": len(ownership),
                "projected_entry_count": len(projected),
            },
        )
        result = RetrievalSurfaceCompilationResult(mode=mode, prompt_version="retrieval_surface_compiler_v2", model=self.model_name, graph=graph, projected_entries=projected, metrics=dict(graph.metrics))
        return RetrievalSurfaceCompilationExecutionResult(result=result, usage=None)
