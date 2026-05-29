from __future__ import annotations

from typing import cast

import pytest
from groq import AsyncGroq

from src.infrastructure.llm.knowledge_surface_parallel_graph_compiler import (
    GroqParallelKnowledgeSurfaceGraphCompiler,
    _UnitCompilationResult,
    _unit_result_to_checkpoint,
)
from tests.infrastructure.llm.faq_behavior_helpers import (
    candidate,
    draft,
    ownership,
    unit,
)


class CheckpointOnlyCompiler(GroqParallelKnowledgeSurfaceGraphCompiler):
    async def _compile_source_unit(self, **kwargs):
        raise AssertionError("checkpointed source unit must not be recompiled")

    async def _judge_global_relations(self, **kwargs):
        return (), (), ()

    async def _reassign_questions(self, **kwargs):
        return (), ()


@pytest.mark.asyncio
async def test_checkpointed_source_unit_is_restored_without_llm_work() -> None:
    compiler = CheckpointOnlyCompiler(
        client=cast(AsyncGroq, object()),
        model="checkpoint-model",
    )
    restored = _UnitCompilationResult(
        unit_index=1,
        candidates=(candidate("checkpointed"),),
        local_relations=(),
        drafts=(draft("checkpointed", canonical_question="What is restored?"),),
        ownership_decisions=(ownership("checkpointed", "What is restored?"),),
        reassignments=(),
        warnings=("checkpoint warning",),
    )
    compiler.set_source_unit_result_checkpoints(
        {
            "unit:key": _unit_result_to_checkpoint(
                source_unit_key="unit:key",
                result=restored,
            )
        }
    )

    events: list[dict[str, object]] = []

    async def progress(event):
        events.append(dict(event))

    compiler.set_progress_callback(progress)

    result = await compiler.compile_surfaces(
        mode="faq",
        source_units=(unit("Restored body"),),
        file_name="faq.md",
        run_id="run-1",
    )

    assert any(
        event["stage_kind"] == "source_unit_checkpoint_reused" for event in events
    )
    assert result.graph.surfaces[0].canonical_question == "What is restored?"
    assert result.graph.surfaces[0].local_surface_key == "checkpointed"
    assert result.metrics["surface_count"] == 1
