from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

from src.application.rag_eval.ports import (
    RagEvalEvidenceEntrySourcePort,
    RagEvalDatasetControlCallback,
    RagEvalDatasetGeneratorPort,
    RagEvalDatasetProgressCallback,
    RagEvalDatasetMetricsCallback,
    RagEvalReportSinkPort,
    RagEvalRunMetricsCallback,
    RagEvalRunProgressCallback,
    RagEvalStorePort,
)
from src.application.rag_eval.reporter import RagQualityReporter
from src.application.rag_eval.review_service import build_review_payload
from src.application.rag_eval.runner import RagEvalRunner, RagEvalTechnicalAnswerError
from src.application.rag_eval.schemas import (
    RagEvalDataset,
    RagEvalEvidenceEntry,
    RagEvalQuestion,
    RagEvalResult,
    RagEvalRun,
    RagQualityReport,
    new_eval_id,
)


def _metric_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


class RagEvalService:
    def __init__(
        self,
        *,
        entry_source: RagEvalEvidenceEntrySourcePort,
        dataset_generator: RagEvalDatasetGeneratorPort,
        runner: RagEvalRunner,
        reporter: RagQualityReporter | None = None,
        store: RagEvalStorePort | None = None,
        report_sink: RagEvalReportSinkPort | None = None,
        run_concurrency: int = 4,
        entry_retrieval_concurrency: int = 8,
    ) -> None:
        self._entry_source = entry_source
        self._dataset_generator = dataset_generator
        self._runner = runner
        self._reporter = reporter or RagQualityReporter()
        self._store = store
        self._report_sink = report_sink
        self._run_concurrency = max(1, min(32, run_concurrency))
        self._entry_retrieval_concurrency = max(1, min(32, entry_retrieval_concurrency))

    async def generate_dataset_and_run_streaming_retrieval(
        self,
        *,
        project_id: str,
        document_id: str,
        progress_callback: RagEvalDatasetProgressCallback | None = None,
        control_callback: RagEvalDatasetControlCallback | None = None,
        run_progress_callback: RagEvalRunProgressCallback | None = None,
        dataset_metrics_callback: RagEvalDatasetMetricsCallback | None = None,
        run_metrics_callback: RagEvalRunMetricsCallback | None = None,
    ) -> tuple[RagEvalRun, RagQualityReport]:
        entries = await self._entry_source.load_document_entries(
            project_id=project_id,
            document_id=document_id,
        )
        entries_total = len(entries)
        dataset = RagEvalDataset(
            id=new_eval_id("dataset"),
            project_id=project_id,
            document_id=document_id,
            status="generating",
            model_used=getattr(self._dataset_generator, "_model_name", ""),
            metadata={
                "generation_strategy": "fragment_local_streaming_entry_review",
                "source_entry_count": entries_total,
            },
        )
        run = RagEvalRun(
            id=new_eval_id("run"),
            dataset_id=dataset.id,
            project_id=project_id,
            document_id=document_id,
            status="running",
            generator_model=dataset.model_used,
        )

        if self._store is not None:
            await self._store.save_dataset(dataset=dataset)
            await self._store.create_run(run=run)

        generation_workers_count = max(
            1, getattr(self._dataset_generator, "_max_concurrency", 1)
        )
        global_retrieval_concurrency = self._run_concurrency
        per_entry_retrieval_concurrency = self._entry_retrieval_concurrency
        entry_queue: asyncio.Queue[RagEvalEvidenceEntry | None] = asyncio.Queue()
        global_retrieval_limiter = asyncio.Semaphore(global_retrieval_concurrency)
        state_lock = asyncio.Lock()
        stop_heartbeat = asyncio.Event()
        started_at = datetime.now(UTC)
        state: dict[str, int] = {
            "entries_queued": entries_total,
            "entries_generating": 0,
            "entries_checking": 0,
            "entries_ready_for_review": 0,
            "entries_failed": 0,
            "active_generation_workers": 0,
            "active_retrieval_checks": 0,
            "generated_questions": 0,
            "checked_questions": 0,
            "retrieval_issues_found": 0,
            "review_candidates_ready": 0,
            "json_parse_failures": 0,
            "provider_failures": 0,
            "retry_count": 0,
            "fallback_used_count": 0,
            # Backward-compatible aggregate aliases for existing UI/worker code.
            "entries_processed": 0,
            "active_retrieval_workers": 0,
            "processed_questions": 0,
            "failed_retrieval_count": 0,
            "actionable_improvements_count": 0,
        }

        for entry in entries:
            await entry_queue.put(entry)
            await self._upsert_review_group_projection(
                run=run,
                entry=entry,
                status="queued",
            )
        for _ in range(generation_workers_count):
            await entry_queue.put(None)

        def elapsed_minutes() -> float:
            elapsed_seconds = max(
                (datetime.now(UTC) - started_at).total_seconds(),
                1.0,
            )
            return elapsed_seconds / 60.0

        async def snapshot() -> dict[str, object]:
            async with state_lock:
                current = dict(state)
            minutes = elapsed_minutes()
            total_questions = max(
                current["generated_questions"],
                current["checked_questions"],
            )
            percent = 100.0
            if entries_total:
                ready_weight = current["entries_ready_for_review"] / entries_total
                checking_weight = current["entries_checking"] / entries_total
                generating_weight = current["entries_generating"] / entries_total
                percent = round(
                    min(
                        99.0,
                        (ready_weight * 90.0)
                        + (checking_weight * 65.0)
                        + (generating_weight * 25.0),
                    ),
                    2,
                )
            return {
                "stage": "fragment_review_streaming",
                "status": "running",
                "entries_total": entries_total,
                "entries_queued": current["entries_queued"],
                "entries_generating": current["entries_generating"],
                "entries_checking": current["entries_checking"],
                "entries_ready_for_review": current["entries_ready_for_review"],
                "entries_failed": current["entries_failed"],
                "fragments_ready_for_review": current["entries_ready_for_review"],
                "active_generation_workers": current["active_generation_workers"],
                "active_retrieval_checks": current["active_retrieval_checks"],
                "generated_questions": current["generated_questions"],
                "checked_questions": current["checked_questions"],
                "retrieval_issues_found": current["retrieval_issues_found"],
                "review_candidates_ready": current["review_candidates_ready"],
                "questions_per_minute": round(
                    current["checked_questions"] / minutes, 2
                ),
                "fragments_per_minute": round(
                    current["entries_ready_for_review"] / minutes, 2
                ),
                "last_update_seconds_ago": 0,
                "question_model": dataset.model_used,
                "fallback_used_count": current["fallback_used_count"],
                "json_parse_failures": current["json_parse_failures"],
                "provider_failures": current["provider_failures"],
                "retry_count": current["retry_count"],
                "generation_concurrency": generation_workers_count,
                "entry_retrieval_concurrency": per_entry_retrieval_concurrency,
                "global_retrieval_concurrency": global_retrieval_concurrency,
                "percent": percent,
                # Backward-compatible aliases kept as technical diagnostics.
                "entries_processed": current["entries_processed"],
                "active_retrieval_workers": current["active_retrieval_workers"],
                "processed_questions": current["processed_questions"],
                "queued_questions": 0,
                "total_questions": total_questions,
                "failed_retrieval_count": current["failed_retrieval_count"],
                "actionable_improvements_count": current[
                    "actionable_improvements_count"
                ],
                "dataset_generation_concurrency": generation_workers_count,
                "retrieval_concurrency": global_retrieval_concurrency,
            }

        async def emit_progress() -> None:
            metrics = await snapshot()
            if progress_callback is not None:
                await progress_callback(
                    _metric_int(metrics["generated_questions"]),
                    max(_metric_int(metrics["generated_questions"]), entries_total),
                    _metric_int(metrics["entries_ready_for_review"]),
                )
            if dataset_metrics_callback is not None:
                await dataset_metrics_callback(metrics)
            if run_progress_callback is not None:
                await run_progress_callback(
                    _metric_int(metrics["checked_questions"]),
                    _metric_int(metrics["total_questions"]),
                )
            if run_metrics_callback is not None:
                await run_metrics_callback(metrics)

        async def heartbeat() -> None:
            while not stop_heartbeat.is_set():
                await asyncio.sleep(1.0)
                await emit_progress()

        async def run_entry_question(
            *,
            question: RagEvalQuestion,
            per_entry_limiter: asyncio.Semaphore,
        ) -> RagEvalResult:
            async with per_entry_limiter:
                async with global_retrieval_limiter:
                    if control_callback is not None:
                        await control_callback()
                    async with state_lock:
                        state["active_retrieval_checks"] += 1
                        state["active_retrieval_workers"] += 1
                    await emit_progress()
                    try:
                        return await self._runner.run_question(
                            run_id=run.id,
                            project_id=project_id,
                            question=question,
                        )
                    except RagEvalTechnicalAnswerError:
                        raise
                    except Exception as exc:
                        return self._runner.failed_result(
                            run_id=run.id,
                            question=question,
                            error=exc,
                            stage="fragment_streaming_rag_eval_question",
                        )
                    finally:
                        async with state_lock:
                            state["active_retrieval_checks"] = max(
                                0, state["active_retrieval_checks"] - 1
                            )
                            state["active_retrieval_workers"] = max(
                                0, state["active_retrieval_workers"] - 1
                            )
                        await emit_progress()

        async def process_entry(entry: RagEvalEvidenceEntry) -> None:
            local_results: list[RagEvalResult] = []
            try:
                if control_callback is not None:
                    await control_callback()
                async with state_lock:
                    state["entries_queued"] = max(0, state["entries_queued"] - 1)
                    state["entries_generating"] += 1
                    state["active_generation_workers"] += 1
                await self._upsert_review_group_projection(
                    run=run,
                    entry=entry,
                    status="generating_questions",
                )
                await emit_progress()

                generated = await self._dataset_generator.generate_dataset(
                    project_id=project_id,
                    document_id=document_id,
                    chunks=[entry],
                    control_callback=control_callback,
                )
                questions = [
                    replace(question, dataset_id=dataset.id)
                    for question in generated.questions
                ]
                async with state_lock:
                    state["entries_generating"] = max(
                        0, state["entries_generating"] - 1
                    )
                    state["active_generation_workers"] = max(
                        0, state["active_generation_workers"] - 1
                    )
                    state["entries_checking"] += 1
                    dataset.questions.extend(questions)
                    dataset.total_questions = len(dataset.questions)
                    state["generated_questions"] += len(questions)
                    state["review_candidates_ready"] += len(questions)
                    metadata = dict(generated.metadata)
                    state["json_parse_failures"] += _metric_int(
                        metadata.get("json_parse_failures")
                    )
                    state["provider_failures"] += _metric_int(
                        metadata.get("provider_failures")
                    )
                    state["retry_count"] += _metric_int(metadata.get("retry_count"))
                    state["fallback_used_count"] += _metric_int(
                        metadata.get("fallback_used_count")
                    )
                if self._store is not None:
                    await self._save_questions_incremental(questions=questions)
                await self._upsert_review_group_projection(
                    run=run,
                    entry=entry,
                    status="checking_retrieval",
                    questions_total=len(questions),
                )
                await emit_progress()

                per_entry_limiter = asyncio.Semaphore(per_entry_retrieval_concurrency)
                tasks = [
                    asyncio.create_task(
                        run_entry_question(
                            question=question,
                            per_entry_limiter=per_entry_limiter,
                        )
                    )
                    for question in questions
                ]
                try:
                    for task in asyncio.as_completed(tasks):
                        if control_callback is not None:
                            await control_callback()
                        result = await task
                        local_results.append(result)
                        run.results.append(result)
                        if self._store is not None:
                            await self._store.save_result(result=result)
                        async with state_lock:
                            state["checked_questions"] += 1
                            state["processed_questions"] += 1
                            if not result.is_passed:
                                state["retrieval_issues_found"] += 1
                                state["failed_retrieval_count"] += 1
                            if result.proposed_actions:
                                state["actionable_improvements_count"] += 1
                        await emit_progress()
                except Exception:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    raise

                counts = self._entry_result_counts(local_results)
                group_payload = self._entry_review_group_payload(
                    run=run,
                    entry=entry,
                    results=local_results,
                )
                async with state_lock:
                    state["entries_checking"] = max(0, state["entries_checking"] - 1)
                    state["entries_ready_for_review"] += 1
                    state["entries_processed"] += 1
                await self._upsert_review_group_projection(
                    run=run,
                    entry=entry,
                    status="ready_for_review",
                    questions_total=len(questions),
                    checked_questions=len(local_results),
                    reliable_count=counts["reliable"],
                    weak_count=counts["weak"],
                    confused_count=counts["confused"],
                    missing_count=counts["missing"],
                    improvement_count=counts["improvements"],
                    review_payload=group_payload,
                )
                await emit_progress()
            except Exception as exc:
                async with state_lock:
                    state["entries_generating"] = max(
                        0, state["entries_generating"] - 1
                    )
                    state["entries_checking"] = max(0, state["entries_checking"] - 1)
                    state["active_generation_workers"] = max(
                        0, state["active_generation_workers"] - 1
                    )
                    state["entries_failed"] += 1
                await self._upsert_review_group_projection(
                    run=run,
                    entry=entry,
                    status="failed",
                    error=str(exc)[:500],
                )
                await emit_progress()
                raise

        async def generation_worker() -> None:
            while True:
                entry = await entry_queue.get()
                try:
                    if entry is None:
                        return
                    await process_entry(entry)
                finally:
                    entry_queue.task_done()

        generation_tasks = [
            asyncio.create_task(generation_worker())
            for _ in range(generation_workers_count)
        ]
        heartbeat_task = asyncio.create_task(heartbeat())

        try:
            await emit_progress()
            await asyncio.gather(*generation_tasks)
        except Exception:
            for task in generation_tasks:
                if not task.done():
                    task.cancel()
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            if self._store is not None:
                await self._store.finish_run(run=run)
            raise
        finally:
            stop_heartbeat.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        dataset.status = "ready"
        dataset.total_questions = len(dataset.questions)
        dataset.metadata = {
            **dict(dataset.metadata),
            "total_questions": dataset.total_questions,
            "streaming": True,
            "streaming_model": "fragment_local_entry_review",
        }
        run.status = "completed"
        run.finished_at = datetime.now(UTC)
        report = self._reporter.build_report(run=run)

        if self._store is not None:
            await self._store.save_dataset(dataset=dataset)
            await self._store.finish_run(run=run)
            await self._store.save_report(report=report)

        if self._report_sink is not None:
            await self._report_sink.write_markdown_report(
                run_id=run.id,
                markdown=report.markdown,
            )
            await self._report_sink.write_json_report(
                run_id=run.id,
                payload=report.to_json(),
            )

        await emit_progress()
        return run, report

    async def _save_questions_incremental(
        self, *, questions: list[RagEvalQuestion]
    ) -> None:
        if self._store is None or not questions:
            return
        await self._store.save_questions(questions=questions)

    async def _upsert_review_group_projection(
        self,
        *,
        run: RagEvalRun,
        entry: RagEvalEvidenceEntry,
        status: str,
        questions_total: int = 0,
        checked_questions: int = 0,
        reliable_count: int = 0,
        weak_count: int = 0,
        confused_count: int = 0,
        missing_count: int = 0,
        improvement_count: int = 0,
        review_payload: dict[str, object] | None = None,
        error: str = "",
    ) -> None:
        if self._store is None:
            return
        await self._store.upsert_review_group(
            run_id=run.id,
            dataset_id=run.dataset_id,
            project_id=run.project_id,
            document_id=run.document_id,
            source_chunk_id=entry.id,
            status=status,
            questions_total=questions_total,
            checked_questions=checked_questions,
            reliable_count=reliable_count,
            weak_count=weak_count,
            confused_count=confused_count,
            missing_count=missing_count,
            improvement_count=improvement_count,
            review_payload=review_payload or {},
            error=error,
        )

    def _entry_review_group_payload(
        self,
        *,
        run: RagEvalRun,
        entry: RagEvalEvidenceEntry,
        results: list[RagEvalResult],
    ) -> dict[str, object]:
        payload = build_review_payload(
            run={
                "id": run.id,
                "dataset_id": run.dataset_id,
                "project_id": run.project_id,
                "document_id": run.document_id,
                "status": run.status,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "retriever_version": run.retriever_version,
                "reranker_version": run.reranker_version,
                "generator_model": run.generator_model,
                "result_count": len(results),
            },
            results=results,
            entries=[entry],
            reviews={},
        )
        groups = payload.get("groups")
        if isinstance(groups, list) and groups and isinstance(groups[0], dict):
            return dict(groups[0])
        return {
            "entry_id": entry.id,
            "title": str(entry.metadata.get("title") or entry.id),
            "content": entry.content,
            "questions": [],
        }

    def _entry_result_counts(self, results: list[RagEvalResult]) -> dict[str, int]:
        counts = {
            "reliable": 0,
            "weak": 0,
            "confused": 0,
            "missing": 0,
            "improvements": 0,
        }
        for result in results:
            if result.top1_hit:
                counts["reliable"] += 1
            elif result.expected_entry_found:
                counts["weak"] += 1
            elif result.wrong_entry_top1:
                counts["confused"] += 1
            else:
                counts["missing"] += 1
            if result.proposed_actions:
                counts["improvements"] += 1
        return counts

    async def generate_dataset_and_run(
        self,
        *,
        project_id: str,
        document_id: str,
        progress_callback: RagEvalDatasetProgressCallback | None = None,
        control_callback: RagEvalDatasetControlCallback | None = None,
        run_progress_callback: RagEvalRunProgressCallback | None = None,
        dataset_metrics_callback: RagEvalDatasetMetricsCallback | None = None,
        run_metrics_callback: RagEvalRunMetricsCallback | None = None,
    ) -> tuple[RagEvalRun, RagQualityReport]:
        chunks = await self._entry_source.load_document_entries(
            project_id=project_id,
            document_id=document_id,
        )

        dataset = await self._dataset_generator.generate_dataset(
            project_id=project_id,
            document_id=document_id,
            chunks=chunks,
            progress_callback=progress_callback,
            control_callback=control_callback,
            metrics_callback=dataset_metrics_callback,
        )

        if self._store is not None:
            await self._store.save_dataset(dataset=dataset)

        run = RagEvalRun(
            id=new_eval_id("run"),
            dataset_id=dataset.id,
            project_id=project_id,
            document_id=document_id,
            status="running",
            generator_model=dataset.model_used,
        )

        if self._store is not None:
            await self._store.create_run(run=run)

        try:
            total_questions = len(dataset.questions)
            completed_questions = 0
            failed_retrieval_count = 0
            semaphore = asyncio.Semaphore(self._run_concurrency)

            async def emit_run_progress() -> None:
                if run_progress_callback is not None:
                    await run_progress_callback(completed_questions, total_questions)
                if run_metrics_callback is not None:
                    await run_metrics_callback(
                        {
                            "processed_questions": completed_questions,
                            "total_questions": total_questions,
                            "failed_retrieval_count": failed_retrieval_count,
                            "retrieval_concurrency": self._run_concurrency,
                        }
                    )

            async def run_one(question_index: int) -> RagEvalResult:
                if control_callback is not None:
                    await control_callback()

                async with semaphore:
                    if control_callback is not None:
                        await control_callback()

                    try:
                        return await self._runner.run_question(
                            run_id=run.id,
                            project_id=project_id,
                            question=dataset.questions[question_index],
                        )
                    except RagEvalTechnicalAnswerError:
                        raise
                    except Exception as exc:
                        return self._runner.failed_result(
                            run_id=run.id,
                            question=dataset.questions[question_index],
                            error=exc,
                            stage="rag_eval_question",
                        )

            await emit_run_progress()
            tasks = [
                asyncio.create_task(run_one(question_index))
                for question_index in range(total_questions)
            ]

            try:
                for task in asyncio.as_completed(tasks):
                    if control_callback is not None:
                        await control_callback()

                    result = await task
                    run.results.append(result)
                    completed_questions += 1
                    if not result.is_passed:
                        failed_retrieval_count += 1

                    if self._store is not None:
                        await self._store.save_result(result=result)

                    await emit_run_progress()
            except Exception:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                raise
        except Exception:
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            if self._store is not None:
                await self._store.finish_run(run=run)
            raise

        run.status = "completed"
        run.finished_at = datetime.now(UTC)

        report = self._reporter.build_report(run=run)

        if self._store is not None:
            await self._store.finish_run(run=run)
            await self._store.save_report(report=report)

        if self._report_sink is not None:
            await self._report_sink.write_markdown_report(
                run_id=run.id,
                markdown=report.markdown,
            )
            await self._report_sink.write_json_report(
                run_id=run.id,
                payload=report.to_json(),
            )

        return run, report
