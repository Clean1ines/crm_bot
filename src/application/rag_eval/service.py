from __future__ import annotations

from datetime import UTC, datetime

from src.application.rag_eval.ports import (
    RagEvalChunkSourcePort,
    RagEvalDatasetGeneratorPort,
    RagEvalReportSinkPort,
    RagEvalStorePort,
)
from src.application.rag_eval.reporter import RagQualityReporter
from src.application.rag_eval.runner import RagEvalRunner
from src.application.rag_eval.schemas import (
    RagEvalRun,
    RagQualityReport,
    new_eval_id,
)


class RagEvalService:
    def __init__(
        self,
        *,
        chunk_source: RagEvalChunkSourcePort,
        dataset_generator: RagEvalDatasetGeneratorPort,
        runner: RagEvalRunner,
        reporter: RagQualityReporter | None = None,
        store: RagEvalStorePort | None = None,
        report_sink: RagEvalReportSinkPort | None = None,
    ) -> None:
        self._chunk_source = chunk_source
        self._dataset_generator = dataset_generator
        self._runner = runner
        self._reporter = reporter or RagQualityReporter()
        self._store = store
        self._report_sink = report_sink

    async def generate_dataset_and_run(
        self,
        *,
        project_id: str,
        document_id: str,
        max_questions: int,
    ) -> tuple[RagEvalRun, RagQualityReport]:
        chunks = await self._chunk_source.load_document_chunks(
            project_id=project_id,
            document_id=document_id,
        )

        dataset = await self._dataset_generator.generate_dataset(
            project_id=project_id,
            document_id=document_id,
            chunks=chunks,
            max_questions=max_questions,
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
            for question in dataset.questions:
                result = await self._runner.run_question(
                    run_id=run.id,
                    project_id=project_id,
                    question=question,
                )
                run.results.append(result)

                if self._store is not None:
                    await self._store.save_result(result=result)
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
