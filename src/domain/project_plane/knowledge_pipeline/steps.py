from dataclasses import dataclass

from .states import KnowledgePipelineState


@dataclass(frozen=True, slots=True)
class KnowledgePipelineStep:
    state: KnowledgePipelineState
    label: str
