from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.use_cases.generate_workbench_rag_eval_questions_batch import (
    WorkbenchRagEvalQuestionGenerationBatchExecutor,
)


async def test_legacy_sync_question_generation_batch_is_retired() -> None:
    with pytest.raises(RuntimeError, match="StartWorkbenchRagEvalV2"):
        await WorkbenchRagEvalQuestionGenerationBatchExecutor().generate_for_entries(
            entries=(),
            allow_degraded_llama_instant=False,
        )
