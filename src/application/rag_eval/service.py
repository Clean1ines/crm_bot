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
    ) -> None:
        self._entry_source = entry_source
        self._dataset_generator = dataset_generator
        self._runner = runner
        self._reporter = reporter or RagQualityReporter()
        self._store = store
        self._report_sink = report_sink
        self._run_concurrency = max(1, min(16, run_concurrency))

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
                "generation_strategy": "streaming_entry_question_variants",
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

        entry_queue: asyncio.Queue[RagEvalEvidenceEntry | None] = asyncio.Queue()
        question_queue: asyncio.Queue[RagEvalQuestion | None] = asyncio.Queue()
        state_lock = asyncio.Lock()
        stop_heartbeat = asyncio.Event()
        started_at = datetime.now(UTC)
        state: dict[str, int] = {
            "entries_processed": 0,
            "active_generation_workers": 0,
            "active_retrieval_workers": 0,
            "generated_questions": 0,
            "processed_questions": 0,
            "failed_retrieval_count": 0,
            "actionable_improvements_count": 0,
            "json_parse_failures": 0,
            "provider_failures": 0,
            "retry_count": 0,
            "fallback_used_count": 0,
        }

        generation_workers_count = max(
            1, getattr(self._dataset_generator, "_max_concurrency", 1)
        )
        retrieval_workers_count = self._run_concurrency

        for entry in entries:
            await entry_queue.put(entry)
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
            return {
                "stage": "streaming_retrieval_eval",
                "status": "running",
                "entries_total": entries_total,
                "entries_processed": current["entries_processed"],
                "active_generation_workers": current["active_generation_workers"],
                "active_retrieval_workers": current["active_retrieval_workers"],
                "generated_questions": current["generated_questions"],
                "processed_questions": current["processed_questions"],
                "queued_questions": question_queue.qsize(),
                "total_questions": max(
                    current["generated_questions"],
                    current["processed_questions"],
                ),
                "failed_retrieval_count": current["failed_retrieval_count"],
                "actionable_improvements_count": current[
                    "actionable_improvements_count"
                ],
                "questions_per_minute": round(
                    current["processed_questions"] / minutes, 2
                ),
                "entries_per_minute": round(current["entries_processed"] / minutes, 2),
                "last_update_seconds_ago": 0,
                "json_parse_failures": current["json_parse_failures"],
                "provider_failures": current["provider_failures"],
                "retry_count": current["retry_count"],
                "fallback_used_count": current["fallback_used_count"],
                "dataset_generation_concurrency": generation_workers_count,
                "retrieval_concurrency": retrieval_workers_count,
            }

        async def emit_progress() -> None:
            metrics = await snapshot()
            if progress_callback is not None:
                await progress_callback(
                    _metric_int(metrics["generated_questions"]),
                    max(_metric_int(metrics["generated_questions"]), entries_total),
                    _metric_int(metrics["entries_processed"]),
                )
            if dataset_metrics_callback is not None:
                await dataset_metrics_callback(metrics)
            if run_progress_callback is not None:
                await run_progress_callback(
                    _metric_int(metrics["processed_questions"]),
                    _metric_int(metrics["total_questions"]),
                )
            if run_metrics_callback is not None:
                await run_metrics_callback(metrics)

        async def heartbeat() -> None:
            while not stop_heartbeat.is_set():
                await asyncio.sleep(1.0)
                await emit_progress()

        async def generation_worker() -> None:
            while True:
                entry = await entry_queue.get()
                try:
                    if entry is None:
                        return
                    if control_callback is not None:
                        await control_callback()
                    async with state_lock:
                        state["active_generation_workers"] += 1
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
                        dataset.questions.extend(questions)
                        dataset.total_questions = len(dataset.questions)
                        state["generated_questions"] += len(questions)
                        state["entries_processed"] += 1
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
                        await self._store.save_dataset(dataset=dataset)
                    for question in questions:
                        await question_queue.put(question)
                    await emit_progress()
                finally:
                    if entry is not None:
                        async with state_lock:
                            state["active_generation_workers"] = max(
                                0,
                                state["active_generation_workers"] - 1,
                            )
                        await emit_progress()
                    entry_queue.task_done()

        async def retrieval_worker() -> None:
            while True:
                question = await question_queue.get()
                try:
                    if question is None:
                        return
                    if control_callback is not None:
                        await control_callback()
                    async with state_lock:
                        state["active_retrieval_workers"] += 1
                    await emit_progress()
                    try:
                        result = await self._runner.run_question(
                            run_id=run.id,
                            project_id=project_id,
                            question=question,
                        )
                    except RagEvalTechnicalAnswerError:
                        raise
                    except Exception as exc:
                        result = self._runner.failed_result(
                            run_id=run.id,
                            question=question,
                            error=exc,
                            stage="streaming_rag_eval_question",
                        )
                    run.results.append(result)
                    if self._store is not None:
                        await self._store.save_result(result=result)
                    async with state_lock:
                        state["processed_questions"] += 1
                        if not result.is_passed:
                            state["failed_retrieval_count"] += 1
                        if result.proposed_actions:
                            state["actionable_improvements_count"] += 1
                    await emit_progress()
                finally:
                    if question is not None:
                        async with state_lock:
                            state["active_retrieval_workers"] = max(
                                0,
                                state["active_retrieval_workers"] - 1,
                            )
                        await emit_progress()
                    question_queue.task_done()

        generation_tasks = [
            asyncio.create_task(generation_worker())
            for _ in range(generation_workers_count)
        ]
        retrieval_tasks = [
            asyncio.create_task(retrieval_worker())
            for _ in range(retrieval_workers_count)
        ]
        heartbeat_task = asyncio.create_task(heartbeat())

        try:
            await emit_progress()
            await asyncio.gather(*generation_tasks)
            for _ in range(retrieval_workers_count):
                await question_queue.put(None)
            await question_queue.join()
            await asyncio.gather(*retrieval_tasks)
        except Exception:
            for task in generation_tasks + retrieval_tasks:
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
