from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from groq import APIError, RateLimitError

from src.application.services.knowledge_surface_graph_quality import (
    validate_faq_surface_graph_quality,
)
from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingMode,
    KnowledgePreprocessingValidationError,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    LocalSurfaceRelation,
    RetrievalSurfaceCandidate,
    RetrievalSurfaceCompilationResult,
    RetrievalSurfaceDraft,
    RetrievalSurfaceGraph,
    RetrievalSurfaceSourceUnit,
    SurfaceAnswerDraft,
    SurfaceQuestionOwnershipDecision,
    SurfaceQuestionReassignment,
)
from src.infrastructure.llm.knowledge_surface_compiler import (
    GROQ_LARGE_REQUEST_FALLBACK_MODEL_ID,
    STRICT_JSON_SYSTEM_MESSAGE,
)
from src.infrastructure.llm.knowledge_surface_full_graph_compiler import (
    GroqFullKnowledgeSurfaceGraphCompiler,
    _dedupe_reassignments,
    _final_ownership,
    _final_surfaces,
    _merge_relations,
    _related_candidates,
    _related_relations,
    _reassign_rejected,
)
from src.infrastructure.llm.knowledge_surface_graph_compiler_v2 import (
    GRAPH_PROMPT_VERSION,
    _is_large_request_error,
)


DEFAULT_FAQ_SURFACE_GRAPH_CONCURRENCY = 3


@dataclass(frozen=True, slots=True)
class _UnitCompilationResult:
    unit_index: int
    candidates: tuple[RetrievalSurfaceCandidate, ...]
    local_relations: tuple[LocalSurfaceRelation, ...]
    drafts: tuple[SurfaceAnswerDraft, ...]
    ownership_decisions: tuple[SurfaceQuestionOwnershipDecision, ...]
    reassignments: tuple[SurfaceQuestionReassignment, ...]
    warnings: tuple[str, ...]


class GroqParallelKnowledgeSurfaceGraphCompiler(GroqFullKnowledgeSurfaceGraphCompiler):
    """Production FAQ graph compiler.

    Restores the operational guarantees the old answer compiler had:
    bounded parallel source-unit processing, live stage metrics, elapsed time,
    token/call accounting, fallback-call tracking, and intermediate card persistence.
    """

    def _reset_runtime_metrics(self) -> None:
        self._llm_call_count = 0
        self._llm_error_count = 0
        self._fallback_call_count = 0
        self._tokens_input = 0
        self._tokens_output = 0
        self._tokens_total = 0
        self._model_call_counts: dict[str, int] = {}

    def _runtime_metrics_snapshot(self, *, started_monotonic: float) -> JsonObject:
        return {
            "elapsed_seconds": json_value_from_unknown(
                round(time.monotonic() - started_monotonic, 1)
            ),
            "llm_call_count": json_value_from_unknown(
                int(getattr(self, "_llm_call_count", 0))
            ),
            "llm_error_count": json_value_from_unknown(
                int(getattr(self, "_llm_error_count", 0))
            ),
            "fallback_call_count": json_value_from_unknown(
                int(getattr(self, "_fallback_call_count", 0))
            ),
            "tokens_input": json_value_from_unknown(
                int(getattr(self, "_tokens_input", 0))
            ),
            "tokens_output": json_value_from_unknown(
                int(getattr(self, "_tokens_output", 0))
            ),
            "tokens_total": json_value_from_unknown(
                int(getattr(self, "_tokens_total", 0))
            ),
            "model_call_counts": json_value_from_unknown(
                dict(getattr(self, "_model_call_counts", {}))
            ),
        }

    def _record_usage(
        self,
        *,
        model: str,
        tokens_input: int,
        tokens_output: int,
        tokens_total: int,
        fallback: bool,
    ) -> None:
        self._llm_call_count = int(getattr(self, "_llm_call_count", 0)) + 1
        if fallback:
            self._fallback_call_count = (
                int(getattr(self, "_fallback_call_count", 0)) + 1
            )
        self._tokens_input = int(getattr(self, "_tokens_input", 0)) + tokens_input
        self._tokens_output = int(getattr(self, "_tokens_output", 0)) + tokens_output
        self._tokens_total = int(getattr(self, "_tokens_total", 0)) + tokens_total
        model_counts = dict(getattr(self, "_model_call_counts", {}))
        model_counts[model] = int(model_counts.get(model, 0)) + 1
        self._model_call_counts = model_counts

    async def _request_json_with_large_request_fallback(
        self,
        *,
        prompt: str,
        max_tokens: int,
    ) -> tuple[str, str]:
        request_model = self._model_for_request(prompt=prompt, max_tokens=max_tokens)
        try:
            return await self._request_json_for_model(
                model=request_model,
                prompt=prompt,
                max_tokens=max_tokens,
                fallback=request_model == GROQ_LARGE_REQUEST_FALLBACK_MODEL_ID,
            )
        except (APIError, RateLimitError) as exc:
            self._llm_error_count = int(getattr(self, "_llm_error_count", 0)) + 1
            if not _is_large_request_error(exc):
                raise
            return await self._request_json_for_model(
                model=GROQ_LARGE_REQUEST_FALLBACK_MODEL_ID,
                prompt=prompt,
                max_tokens=max_tokens,
                fallback=True,
            )

    async def _request_json_for_model(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int,
        fallback: bool,
    ) -> tuple[str, str]:
        response = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": STRICT_JSON_SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        tokens_input = _int_attr(usage, "prompt_tokens")
        tokens_output = _int_attr(usage, "completion_tokens")
        tokens_total = _int_attr(usage, "total_tokens")
        self._record_usage(
            model=model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_total=tokens_total,
            fallback=fallback,
        )
        return model, content

    def _concurrency(self) -> int:
        raw_value = os.getenv("FAQ_SURFACE_GRAPH_CONCURRENCY", "").strip()
        if not raw_value:
            return DEFAULT_FAQ_SURFACE_GRAPH_CONCURRENCY
        try:
            parsed = int(raw_value)
        except ValueError:
            return DEFAULT_FAQ_SURFACE_GRAPH_CONCURRENCY
        return max(1, min(parsed, 8))

    async def compile_surfaces(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        source_units: Sequence[RetrievalSurfaceSourceUnit],
        file_name: str,
        run_id: str,
    ) -> RetrievalSurfaceCompilationResult:
        units = tuple(source_units)
        if not units:
            raise KnowledgePreprocessingValidationError(
                "FAQ graph compiler requires source units"
            )

        self._reset_runtime_metrics()
        started_monotonic = time.monotonic()
        concurrency = self._concurrency()
        semaphore = asyncio.Semaphore(concurrency)

        await self._emit_progress(
            stage_kind="faq_surface_graph_parallel_bootstrap",
            status="running",
            input_summary=f"source_units={len(units)} concurrency={concurrency}",
            metrics={
                "source_unit_count": len(units),
                "concurrency": concurrency,
                **self._runtime_metrics_snapshot(started_monotonic=started_monotonic),
            },
        )

        async def run_unit(
            unit_index: int,
            unit: RetrievalSurfaceSourceUnit,
        ) -> _UnitCompilationResult:
            async with semaphore:
                return await self._compile_source_unit(
                    unit_index=unit_index,
                    source_unit_count=len(units),
                    unit=unit,
                    file_name=file_name,
                    run_id=run_id,
                    started_monotonic=started_monotonic,
                    concurrency=concurrency,
                )

        tasks = [
            asyncio.create_task(run_unit(unit_index, unit))
            for unit_index, unit in enumerate(units, start=1)
        ]
        unit_results = tuple(
            sorted(
                await asyncio.gather(*tasks),
                key=lambda item: item.unit_index,
            )
        )

        candidates = tuple(
            candidate for result in unit_results for candidate in result.candidates
        )
        local_relations = tuple(
            relation for result in unit_results for relation in result.local_relations
        )
        drafts = tuple(draft for result in unit_results for draft in result.drafts)
        ownership_decisions = tuple(
            decision
            for result in unit_results
            for decision in result.ownership_decisions
        )
        reassignments = tuple(
            reassignment
            for result in unit_results
            for reassignment in result.reassignments
        )
        warnings = tuple(
            warning for result in unit_results for warning in result.warnings
        )

        await self._emit_progress(
            stage_kind="global_reconciliation",
            status="running",
            input_summary=f"surfaces={len(drafts)} local_relations={len(local_relations)}",
            metrics={
                "source_unit_count": len(units),
                "surface_count": len(drafts),
                "candidate_count": len(candidates),
                "local_relation_count": len(local_relations),
                "concurrency": concurrency,
                **self._runtime_metrics_snapshot(started_monotonic=started_monotonic),
            },
        )

        (
            judge_relations,
            merge_decisions,
            judge_warnings,
        ) = await self._judge_global_relations(
            run_id=run_id,
            document_id=units[0].document_id,
            drafts=drafts,
            local_relations=local_relations,
        )
        warnings = warnings + judge_warnings

        await self._emit_progress(
            stage_kind="global_relation_judge",
            status="completed",
            output_summary=(
                f"judge_relations={len(judge_relations)} merges={len(merge_decisions)}"
            ),
            metrics={
                "judge_relation_count": len(judge_relations),
                "merge_decision_count": len(merge_decisions),
                "concurrency": concurrency,
                **self._runtime_metrics_snapshot(started_monotonic=started_monotonic),
            },
        )

        final_relations = _merge_relations(
            run_id=run_id,
            document_id=units[0].document_id,
            local_relations=local_relations,
            judge_relations=judge_relations,
            drafts=drafts,
        )
        final_reassignments, reassignment_warnings = await self._reassign_questions(
            run_id=run_id,
            document_id=units[0].document_id,
            drafts=drafts,
            relations=final_relations,
            ownership_decisions=ownership_decisions,
            existing_reassignments=reassignments,
        )
        warnings = warnings + reassignment_warnings
        reassignments = _dedupe_reassignments(reassignments + final_reassignments)

        await self._emit_progress(
            stage_kind="question_reassignment",
            status="completed",
            output_summary=f"reassignments={len(final_reassignments)}",
            metrics={
                "reassignment_count": len(final_reassignments),
                "concurrency": concurrency,
                **self._runtime_metrics_snapshot(started_monotonic=started_monotonic),
            },
        )

        final_ownership = _final_ownership(
            run_id=run_id,
            document_id=units[0].document_id,
            decisions=ownership_decisions,
            reassignments=reassignments,
        )
        surfaces = _final_surfaces(
            run_id=run_id,
            document_id=units[0].document_id,
            candidates=candidates,
            drafts=drafts,
            warnings=warnings,
        )

        graph = RetrievalSurfaceGraph(
            run_id=run_id,
            document_id=units[0].document_id,
            source_units=units,
            surfaces=surfaces,
            relations=final_relations,
            ownership=final_ownership,
            reassignments=reassignments,
            merge_decisions=merge_decisions,
            metrics={
                "compiler_kind": "parallel_surface_graph_v2",
                "source_unit_count": len(units),
                "candidate_count": len(candidates),
                "surface_count": len(surfaces),
                "relation_count": len(final_relations),
                "ownership_count": len(final_ownership),
                "reassignment_count": len(reassignments),
                "merge_decision_count": len(merge_decisions),
                "warning_count": len(warnings),
                "concurrency": concurrency,
                **self._runtime_metrics_snapshot(started_monotonic=started_monotonic),
            },
        )
        quality = validate_faq_surface_graph_quality(graph)
        if not quality.passed:
            raise KnowledgePreprocessingValidationError(
                "FAQ surface graph quality failed: " + ", ".join(quality.issues)
            )

        metrics: JsonObject = {
            **graph.metrics,
            **quality.metrics,
            "quality_status": "passed",
            "prompt_version": GRAPH_PROMPT_VERSION,
        }
        if quality.warnings:
            metrics["quality_warnings"] = json_value_from_unknown(
                list(quality.warnings)
            )

        return RetrievalSurfaceCompilationResult(
            mode=mode,
            prompt_version=GRAPH_PROMPT_VERSION,
            model=self.model_name,
            graph=replace(graph, metrics=metrics),
            metrics=metrics,
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
        warnings: list[str] = []

        discovered = await self.discover_surfaces_for_source_unit(
            source_unit=unit,
            file_name=file_name,
            run_id=run_id,
        )
        unit_candidates = discovered.surface_candidates
        warnings.extend(discovered.warnings)
        await self._emit_progress(
            stage_kind="surface_discovery",
            status="completed",
            input_summary=f"source_unit={unit_index}/{source_unit_count} {unit.title}",
            output_summary=f"candidates={len(unit_candidates)}",
            metrics={
                "source_unit_index": unit_index,
                "source_unit_count": source_unit_count,
                "candidate_count": len(unit_candidates),
                "source_unit_key": unit.source_unit_key,
                "concurrency": concurrency,
                **self._runtime_metrics_snapshot(started_monotonic=started_monotonic),
            },
        )

        if len(unit_candidates) <= 1:
            unit_relations: tuple[LocalSurfaceRelation, ...] = ()
            await self._emit_progress(
                stage_kind="relation_planning",
                status="completed",
                input_summary=f"source_unit={unit_index}/{source_unit_count} {unit.title}",
                output_summary="relations=0 skipped=single_candidate",
                metrics={
                    "source_unit_index": unit_index,
                    "source_unit_count": source_unit_count,
                    "candidate_count": len(unit_candidates),
                    "relation_count": 0,
                    "relation_planning_skipped": True,
                    "source_unit_key": unit.source_unit_key,
                    "concurrency": concurrency,
                    **self._runtime_metrics_snapshot(
                        started_monotonic=started_monotonic
                    ),
                },
            )
        else:
            planned = await self.plan_local_relations(
                source_unit=unit,
                candidates=unit_candidates,
                file_name=file_name,
                run_id=run_id,
            )
            unit_relations = planned.relations
            warnings.extend(planned.warnings)
            await self._emit_progress(
                stage_kind="relation_planning",
                status="completed",
                input_summary=f"source_unit={unit_index}/{source_unit_count} {unit.title}",
                output_summary=f"relations={len(unit_relations)}",
                metrics={
                    "source_unit_index": unit_index,
                    "source_unit_count": source_unit_count,
                    "relation_count": len(unit_relations),
                    "candidate_count": len(unit_candidates),
                    "source_unit_key": unit.source_unit_key,
                    "concurrency": concurrency,
                    **self._runtime_metrics_snapshot(
                        started_monotonic=started_monotonic
                    ),
                },
            )

        unit_drafts: list[SurfaceAnswerDraft] = []
        unit_ownership: list[SurfaceQuestionOwnershipDecision] = []
        unit_reassignments: list[SurfaceQuestionReassignment] = []

        for candidate_index, candidate in enumerate(unit_candidates, start=1):
            related_candidates = _related_candidates(
                candidate, unit_candidates, unit_relations
            )
            related_relations = _related_relations(
                candidate.local_surface_key, unit_relations
            )

            draft = await self.synthesize_surface_answer(
                source_unit=unit,
                candidate=candidate,
                local_relations=related_relations,
                related_candidates=related_candidates,
                file_name=file_name,
                run_id=run_id,
            )
            unit_drafts.append(draft)
            warnings.extend(draft.warnings)
            await self._emit_progress(
                stage_kind="answer_synthesis",
                status="completed",
                input_summary=(
                    f"source_unit={unit_index}/{source_unit_count} "
                    f"candidate={candidate_index}/{len(unit_candidates)}"
                ),
                output_summary=f"surface={candidate.local_surface_key}",
                metrics={
                    "source_unit_index": unit_index,
                    "source_unit_count": source_unit_count,
                    "candidate_index": candidate_index,
                    "candidate_count": len(unit_candidates),
                    "surface_key": candidate.local_surface_key,
                    "concurrency": concurrency,
                    **self._runtime_metrics_snapshot(
                        started_monotonic=started_monotonic
                    ),
                },
            )

            ownership_result = await self.assign_surface_questions(
                source_unit=unit,
                answer_draft=draft,
                candidate=candidate,
                local_relations=related_relations,
                related_candidates=related_candidates,
                file_name=file_name,
                run_id=run_id,
            )
            unit_ownership.extend(ownership_result.owned_questions)
            warnings.extend(ownership_result.warnings)
            unit_reassignments.extend(
                _reassign_rejected(
                    run_id=run_id,
                    document_id=unit.document_id,
                    from_surface_key=candidate.local_surface_key,
                    rejected_questions=ownership_result.rejected_questions,
                )
            )
            await self._emit_progress(
                stage_kind="question_ownership",
                status="completed",
                input_summary=(
                    f"source_unit={unit_index}/{source_unit_count} "
                    f"candidate={candidate_index}/{len(unit_candidates)}"
                ),
                output_summary=(
                    f"owned={len(ownership_result.owned_questions)} "
                    f"rejected={len(ownership_result.rejected_questions)}"
                ),
                metrics={
                    "source_unit_index": unit_index,
                    "source_unit_count": source_unit_count,
                    "candidate_index": candidate_index,
                    "candidate_count": len(unit_candidates),
                    "surface_key": candidate.local_surface_key,
                    "owned_question_count": len(ownership_result.owned_questions),
                    "rejected_question_count": len(ownership_result.rejected_questions),
                    "concurrency": concurrency,
                    **self._runtime_metrics_snapshot(
                        started_monotonic=started_monotonic
                    ),
                },
            )

        partial_surfaces = _final_surfaces(
            run_id=run_id,
            document_id=unit.document_id,
            candidates=unit_candidates,
            drafts=tuple(unit_drafts),
            warnings=tuple(warnings),
        )
        await self._emit_partial_surfaces(
            unit_index=unit_index,
            source_unit_count=source_unit_count,
            surfaces=partial_surfaces,
            started_monotonic=started_monotonic,
            concurrency=concurrency,
        )

        return _UnitCompilationResult(
            unit_index=unit_index,
            candidates=unit_candidates,
            local_relations=unit_relations,
            drafts=tuple(unit_drafts),
            ownership_decisions=tuple(unit_ownership),
            reassignments=tuple(unit_reassignments),
            warnings=tuple(warnings),
        )

    async def _emit_partial_surfaces(
        self,
        *,
        unit_index: int,
        source_unit_count: int,
        surfaces: tuple[RetrievalSurfaceDraft, ...],
        started_monotonic: float,
        concurrency: int,
    ) -> None:
        callback = getattr(self, "_progress_callback", None)
        if callback is None:
            return
        await callback(
            {
                "stage_kind": "partial_surface_cards",
                "status": "completed",
                "input_summary": f"source_unit={unit_index}/{source_unit_count}",
                "output_summary": f"partial_surfaces={len(surfaces)}",
                "partial_surfaces": surfaces,
                "metrics": {
                    "source_unit_index": unit_index,
                    "source_unit_count": source_unit_count,
                    "partial_surface_count": len(surfaces),
                    "concurrency": concurrency,
                    **self._runtime_metrics_snapshot(
                        started_monotonic=started_monotonic
                    ),
                },
            }
        )


def _int_attr(value: object, name: str) -> int:
    raw_value = getattr(value, name, 0)
    if isinstance(raw_value, int) and not isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str) and raw_value.strip().isdigit():
        return int(raw_value)
    return 0
