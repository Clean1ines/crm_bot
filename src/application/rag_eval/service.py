from __future__ import annotations

import asyncio
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
    RagEvalResult,
    RagEvalRun,
    RagQualityReport,
    new_eval_id,
)


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
