from __future__ import annotations


class WorkbenchRagEvalQuestionGenerationError(RuntimeError):
    pass


class WorkbenchRagEvalDegradedFallbackRequiredError(
    WorkbenchRagEvalQuestionGenerationError
):
    pass
