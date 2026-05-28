from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace

from src.domain.project_plane.json_types import json_value_from_unknown
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingMode
from src.domain.project_plane.retrieval_surface_compilation import (
    LocalSurfaceRelation,
    RetrievalSurfaceCandidate,
    RetrievalSurfaceCompilationResult,
    RetrievalSurfaceMergeDecision,
    RetrievalSurfaceRelation,
    RetrievalSurfaceSourceChild,
    RetrievalSurfaceSourceUnit,
    SurfaceAnswerDraft,
    SurfaceQuestionOwnershipDecision,
    SurfaceQuestionReassignment,
)
from src.infrastructure.llm.groq_router import (
    GroqFallbackExhaustedError,
    GroqRouteFailureType,
)
from src.infrastructure.llm.knowledge_surface_compiler import GROQ_INSTANT_MODEL_ID
from src.infrastructure.llm.knowledge_surface_full_graph_compiler import (
    _dedupe_reassignments,
    _final_surfaces,
)
from src.infrastructure.llm.knowledge_surface_parallel_graph_compiler import (
    GroqParallelKnowledgeSurfaceGraphCompiler,
    _UnitCompilationResult,
    _unit_result_to_checkpoint,
)

INSTANT_SUBUNIT_DEFAULT_MAX_CHARS = 4500
ECONOMY_INSTANT_QUALITY_WARNING = (
    "Большие модели Groq были недоступны; документ обработан в экономичном "
    "режиме llama-3.1-8b-instant. Проверьте качество перед публикацией."
)
CancelCheck = Callable[[], Awaitable[None]]
_HEADING_RE = re.compile(r"(?m)^(#{1,6}\s+.+)$")
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ0-9])")


class KnowledgeSurfaceCompilationCancelled(RuntimeError):
    pass


def _parts_by_headings(text: str) -> tuple[str, ...]:
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return (text,)
    parts: list[str] = []
    if matches[0].start() > 0 and text[: matches[0].start()].strip():
        parts.append(text[: matches[0].start()].strip())
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        part = text[match.start() : end].strip()
        if part:
            parts.append(part)
    return tuple(parts) or (text,)


def _pack(parts: Sequence[str], *, max_chars: int) -> tuple[str, ...]:
    packed: list[str] = []
    current: list[str] = []
    current_len = 0
    for raw in parts:
        part = raw.strip()
        if not part:
            continue
        if len(part) > max_chars:
            if current:
                packed.append("\n\n".join(current).strip())
                current = []
                current_len = 0
            packed.extend(
                part[index : index + max_chars].strip()
                for index in range(0, len(part), max_chars)
            )
            continue
        projected = current_len + len(part) + (2 if current else 0)
        if current and projected > max_chars:
            packed.append("\n\n".join(current).strip())
            current = []
            current_len = 0
        current.append(part)
        current_len += len(part) + (2 if current_len else 0)
    if current:
        packed.append("\n\n".join(current).strip())
    return tuple(item for item in packed if item)


def _split_text_for_instant(text: str, *, max_chars: int) -> tuple[str, ...]:
    if len(text) <= max_chars:
        return (text,)
    candidates: list[str] = []
    for section in _parts_by_headings(text):
        if len(section) <= max_chars:
            candidates.append(section)
            continue
        paragraphs = tuple(
            item.strip() for item in re.split(r"\n\s*\n", section) if item.strip()
        )
        for paragraph in paragraphs or (section,):
            if len(paragraph) <= max_chars:
                candidates.append(paragraph)
            else:
                candidates.extend(
                    item.strip()
                    for item in _SENTENCE_RE.split(paragraph)
                    if item.strip()
                )
    return _pack(candidates, max_chars=max_chars)


def split_source_unit_for_instant(
    unit: RetrievalSurfaceSourceUnit,
    *,
    max_chars: int,
) -> tuple[RetrievalSurfaceSourceUnit, ...]:
    parts = _split_text_for_instant(
        unit.raw_text or unit.body,
        max_chars=max(800, max_chars),
    )
    if len(parts) == 1:
        return (unit,)
    result: list[RetrievalSurfaceSourceUnit] = []
    for index, body in enumerate(parts, start=1):
        key = f"{unit.source_unit_key}::instant_subunit:{index}"
        result.append(
            RetrievalSurfaceSourceUnit(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{unit.id}:{key}")),
                run_id=unit.run_id,
                document_id=unit.document_id,
                source_unit_key=key,
                source_chunk_indexes=unit.source_chunk_indexes,
                title=f"{unit.title} · instant subunit {index}/{len(parts)}",
                body=body,
                children=(
                    RetrievalSurfaceSourceChild(
                        title="instant_subunit",
                        body=body,
                        raw_text=body,
                        label_kind="content_section",
                        metadata={
                            "original_source_unit_key": unit.source_unit_key,
                            "subunit_index": index,
                            "subunit_count": len(parts),
                        },
                    ),
                ),
                raw_text=body,
                section_path=(*unit.section_path, f"instant_subunit:{index}"),
                source_refs=unit.source_refs,
                preprocessing_mode=unit.preprocessing_mode,
                metadata={
                    **unit.metadata,
                    "economy_instant_subunit": True,
                    "original_source_unit_key": unit.source_unit_key,
                    "subunit_index": index,
                    "subunit_count": len(parts),
                },
            )
        )
    return tuple(result)


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = " ".join(value.strip().split())
        if text and text not in result:
            result.append(text)
    return tuple(result)


class GroqEconomyInstantKnowledgeSurfaceGraphCompiler(
    GroqParallelKnowledgeSurfaceGraphCompiler
):
    def set_cancel_check(self, callback: CancelCheck | None) -> None:
        self._cancel_check = callback

    async def _ensure_not_cancelled(self) -> None:
        callback = getattr(self, "_cancel_check", None)
        if callback is not None:
            await callback()

    async def _stage(
        self,
        stage: str,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        await self._ensure_not_cancelled()
        return await super()._stage(stage, payload)

    async def _prompt_json(
        self,
        prompt_file: str,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        await self._ensure_not_cancelled()
        return await super()._prompt_json(prompt_file, payload)

    async def compile_surfaces(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        source_units: Sequence[RetrievalSurfaceSourceUnit],
        file_name: str,
        run_id: str,
    ) -> RetrievalSurfaceCompilationResult:
        self._economy_enabled = False
        self._economy_reason = ""
        self._economy_subunits = 0
        self._economy_completed_subunits = 0
        await self._ensure_not_cancelled()
        result = await super().compile_surfaces(
            mode=mode,
            source_units=source_units,
            file_name=file_name,
            run_id=run_id,
        )
        if not bool(getattr(self, "_economy_enabled", False)):
            return result
        metrics = {
            **result.metrics,
            "economy_mode": True,
            "economy_reason": str(getattr(self, "_economy_reason", "")),
            "economy_subunit_count": int(getattr(self, "_economy_subunits", 0)),
            "economy_completed_subunit_count": int(
                getattr(self, "_economy_completed_subunits", 0)
            ),
            "economy_quality_warning": ECONOMY_INSTANT_QUALITY_WARNING,
            "quality_mode": "economy_instant",
            "quality_warning": ECONOMY_INSTANT_QUALITY_WARNING,
        }
        graph = replace(
            result.graph,
            metrics={
                **result.graph.metrics,
                **{
                    key: json_value_from_unknown(value)
                    for key, value in metrics.items()
                },
            },
            surfaces=tuple(
                replace(
                    surface,
                    warnings=_dedupe(
                        (*surface.warnings, ECONOMY_INSTANT_QUALITY_WARNING)
                    ),
                    metadata={
                        **surface.metadata,
                        "economy_mode": True,
                        "quality_mode": "economy_instant",
                    },
                )
                for surface in result.graph.surfaces
            ),
        )
        return replace(
            result,
            graph=graph,
            metrics={
                str(key): json_value_from_unknown(value)
                for key, value in metrics.items()
            },
            model=GROQ_INSTANT_MODEL_ID,
        )

    async def _compile_source_unit(
        self,
        *,
        unit_index: int,
        source_unit_count: int,
        unit: RetrievalSurfaceSourceUnit,
        file_name: str,
        run_id: str,
        started_monotonic: float,
        concurrency: int,
    ) -> _UnitCompilationResult:
        await self._ensure_not_cancelled()
        try:
            return await super()._compile_source_unit(
                unit_index=unit_index,
                source_unit_count=source_unit_count,
                unit=unit,
                file_name=file_name,
                run_id=run_id,
                started_monotonic=started_monotonic,
                concurrency=concurrency,
            )
        except GroqFallbackExhaustedError as exc:
            if exc.failure_type not in {
                GroqRouteFailureType.INPUT_TOO_LARGE,
                GroqRouteFailureType.QUOTA_EXHAUSTED,
                GroqRouteFailureType.ALL_FALLBACKS_EXHAUSTED,
            }:
                raise
            return await self._compile_source_unit_in_economy_mode(
                unit_index=unit_index,
                source_unit_count=source_unit_count,
                unit=unit,
                file_name=file_name,
                run_id=run_id,
                started_monotonic=started_monotonic,
                concurrency=concurrency,
                reason=exc.failure_type.value,
            )

    async def _compile_source_unit_in_economy_mode(
        self,
        *,
        unit_index: int,
        source_unit_count: int,
        unit: RetrievalSurfaceSourceUnit,
        file_name: str,
        run_id: str,
        started_monotonic: float,
        concurrency: int,
        reason: str,
    ) -> _UnitCompilationResult:
        self._economy_enabled = True
        self._economy_reason = reason
        subunits = split_source_unit_for_instant(
            unit,
            max_chars=INSTANT_SUBUNIT_DEFAULT_MAX_CHARS,
        )
        self._economy_subunits = int(getattr(self, "_economy_subunits", 0)) + len(
            subunits
        )
        await self._emit_progress(
            stage_kind="economy_instant_mode",
            status="running",
            input_summary=f"source_unit={unit_index}/{source_unit_count} {unit.title}",
            output_summary=f"reason={reason} subunits={len(subunits)}",
            metrics={
                "source_unit_index": unit_index,
                "source_unit_count": source_unit_count,
                "source_unit_key": unit.source_unit_key,
                "economy_mode": True,
                "economy_reason": reason,
                "economy_source_unit_split_count": len(subunits),
                "actual_model": GROQ_INSTANT_MODEL_ID,
                **self._runtime_metrics_snapshot(started_monotonic=started_monotonic),
            },
        )
        previous_model = self._model
        candidates: list[RetrievalSurfaceCandidate] = []
        drafts: list[SurfaceAnswerDraft] = []
        ownership: list[SurfaceQuestionOwnershipDecision] = []
        try:
            self._model = GROQ_INSTANT_MODEL_ID
            for subunit_index, subunit in enumerate(subunits, start=1):
                await self._ensure_not_cancelled()
                discovered = await self.discover_surfaces_for_source_unit(
                    source_unit=subunit,
                    file_name=file_name,
                    run_id=run_id,
                )
                for candidate in discovered.surface_candidates:
                    candidate_key = (
                        f"{candidate.local_surface_key}:economy:{subunit_index}"
                    )
                    economy_candidate = replace(
                        candidate,
                        source_unit_id=unit.id,
                        local_surface_key=candidate_key,
                        source_refs=_dedupe(
                            (*unit.source_refs, *candidate.source_refs)
                        ),
                        metadata={
                            **candidate.metadata,
                            "economy_mode": True,
                            "original_source_unit_key": unit.source_unit_key,
                            "economy_instant_subunit_index": subunit_index,
                        },
                    )
                    draft = await self.synthesize_surface_answer(
                        source_unit=subunit,
                        candidate=economy_candidate,
                        local_relations=(),
                        related_candidates=(economy_candidate,),
                        file_name=file_name,
                        run_id=run_id,
                    )
                    economy_draft = replace(
                        draft,
                        candidate_key=candidate_key,
                        source_refs=_dedupe((*unit.source_refs, *draft.source_refs)),
                        warnings=_dedupe(
                            (*draft.warnings, ECONOMY_INSTANT_QUALITY_WARNING)
                        ),
                        metadata={
                            **draft.metadata,
                            "economy_mode": True,
                            "quality_mode": "economy_instant",
                            "original_source_unit_key": unit.source_unit_key,
                        },
                    )
                    candidates.append(economy_candidate)
                    drafts.append(economy_draft)
                    ownership.append(
                        SurfaceQuestionOwnershipDecision(
                            id=str(uuid.uuid5(uuid.NAMESPACE_URL, candidate_key)),
                            run_id=run_id,
                            document_id=unit.document_id,
                            surface_key=candidate_key,
                            question=economy_draft.canonical_question
                            or economy_draft.title,
                            question_kind="faq_question",
                            ownership_confidence=max(economy_candidate.confidence, 0.7),
                            source="economy_instant_deterministic",
                            status="owned",
                        )
                    )
                self._economy_completed_subunits = (
                    int(getattr(self, "_economy_completed_subunits", 0)) + 1
                )
                await self._emit_progress(
                    stage_kind="economy_instant_subunit",
                    status="completed",
                    input_summary=f"subunit={subunit_index}/{len(subunits)}",
                    output_summary=f"candidates={len(discovered.surface_candidates)}",
                    metrics={
                        "source_unit_index": unit_index,
                        "source_unit_count": source_unit_count,
                        "source_unit_key": unit.source_unit_key,
                        "economy_mode": True,
                        "economy_reason": reason,
                        "economy_subunit_index": subunit_index,
                        "economy_completed_subunit_count": int(
                            getattr(self, "_economy_completed_subunits", 0)
                        ),
                        "actual_model": GROQ_INSTANT_MODEL_ID,
                        **self._runtime_metrics_snapshot(
                            started_monotonic=started_monotonic
                        ),
                    },
                )
        finally:
            self._model = previous_model
        if not candidates or not drafts:
            raise GroqFallbackExhaustedError(
                failure_type=GroqRouteFailureType.ALL_FALLBACKS_EXHAUSTED,
                message="economy instant compiler produced no publishable surfaces",
            )
        result = _UnitCompilationResult(
            unit_index=unit_index,
            candidates=tuple(candidates),
            local_relations=(),
            drafts=tuple(drafts),
            ownership_decisions=tuple(ownership),
            reassignments=(),
            warnings=(ECONOMY_INSTANT_QUALITY_WARNING,),
        )
        partial_surfaces = _final_surfaces(
            run_id=run_id,
            document_id=unit.document_id,
            candidates=result.candidates,
            drafts=result.drafts,
            warnings=result.warnings,
        )
        await self._emit_partial_surfaces(
            unit_index=unit_index,
            source_unit_count=source_unit_count,
            source_unit_key=unit.source_unit_key,
            surfaces=partial_surfaces,
            unit_checkpoint=_unit_result_to_checkpoint(
                source_unit_key=unit.source_unit_key,
                result=result,
            ),
            started_monotonic=started_monotonic,
            concurrency=concurrency,
        )
        return result

    async def _judge_global_relations(
        self,
        *,
        run_id: str,
        document_id: str,
        drafts: tuple[SurfaceAnswerDraft, ...],
        local_relations: tuple[LocalSurfaceRelation, ...],
    ) -> tuple[
        tuple[RetrievalSurfaceRelation, ...],
        tuple[RetrievalSurfaceMergeDecision, ...],
        tuple[str, ...],
    ]:
        await self._ensure_not_cancelled()
        if bool(getattr(self, "_economy_enabled", False)):
            return (), (), ()
        return await super()._judge_global_relations(
            run_id=run_id,
            document_id=document_id,
            drafts=drafts,
            local_relations=local_relations,
        )

    async def _reassign_questions(
        self,
        *,
        run_id: str,
        document_id: str,
        drafts: tuple[SurfaceAnswerDraft, ...],
        relations: tuple[RetrievalSurfaceRelation, ...],
        ownership_decisions: tuple[SurfaceQuestionOwnershipDecision, ...],
        existing_reassignments: tuple[SurfaceQuestionReassignment, ...],
    ) -> tuple[tuple[SurfaceQuestionReassignment, ...], tuple[str, ...]]:
        await self._ensure_not_cancelled()
        if bool(getattr(self, "_economy_enabled", False)):
            return _dedupe_reassignments(tuple(existing_reassignments)), ()
        return await super()._reassign_questions(
            run_id=run_id,
            document_id=document_id,
            drafts=drafts,
            relations=relations,
            ownership_decisions=ownership_decisions,
            existing_reassignments=existing_reassignments,
        )
