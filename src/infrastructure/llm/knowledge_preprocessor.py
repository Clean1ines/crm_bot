from __future__ import annotations


class RetiredLegacyKnowledgePreprocessorError(RuntimeError):
    """The old GroqKnowledgePreprocessor belonged to the retired compiler path."""


class GroqKnowledgePreprocessor:
    """Retired legacy preprocessor entrypoint.

    FAQ document processing now uses FAQ Workbench claim-observation and
    registry-merge generators. Do not route production uploads through this class.
    """

    model_name = "retired_legacy_knowledge_preprocessor"

    async def preprocess(self, *args: object, **kwargs: object) -> object:
        raise RetiredLegacyKnowledgePreprocessorError(
            "Legacy GroqKnowledgePreprocessor.preprocess is retired. "
            "Use FAQ Workbench document processing instead."
        )

    async def resolve_answer_cases(self, *args: object, **kwargs: object) -> object:
        raise RetiredLegacyKnowledgePreprocessorError(
            "Legacy GroqKnowledgePreprocessor.resolve_answer_cases is retired. "
            "Use FAQ Workbench registry/evidence trace flows instead."
        )


__all__ = [
    "GroqKnowledgePreprocessor",
    "RetiredLegacyKnowledgePreprocessorError",
]
