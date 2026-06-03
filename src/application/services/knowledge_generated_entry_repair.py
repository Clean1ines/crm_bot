from __future__ import annotations


class RetiredLegacyKnowledgePreprocessingError(RuntimeError):
    """Legacy pre-Workbench knowledge preprocessing was removed."""


def __getattr__(name: str) -> object:
    raise RetiredLegacyKnowledgePreprocessingError(
        f"{name} belongs to the retired legacy knowledge preprocessing layer"
    )
