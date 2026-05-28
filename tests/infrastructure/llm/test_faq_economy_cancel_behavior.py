from __future__ import annotations

import time

import pytest

from src.domain.project_plane.retrieval_surface_compilation import (
    SurfaceDiscoveryResult,
)
from src.infrastructure.llm.knowledge_surface_compiler import GROQ_INSTANT_MODEL_ID
from src.infrastructure.llm.knowledge_surface_economy_instant import (
    GroqEconomyInstantKnowledgeSurfaceGraphCompiler,
    KnowledgeSurfaceCompilationCancelled,
)
from tests.infrastructure.llm.faq_behavior_helpers import candidate, draft, unit


class CancelAwareEconomyCompiler(GroqEconomyInstantKnowledgeSurfaceGraphCompiler):
    def __init__(self) -> None:
        super().__init__(
            client=object(),  # type: ignore[arg-type]
            model=GROQ_INSTANT_MODEL_ID,
        )
        self.discover_calls = 0
        self.synthesis_calls = 0

    async def discover_surfaces_for_source_unit(
        self,
        *,
        source_unit,
        file_name: str,
        run_id: str,
    ):
        self.discover_calls += 1
        return SurfaceDiscoveryResult(
            surface_candidates=(
                candidate(
                    f"candidate-{self.discover_calls}",
                    source_unit_id=source_unit.id,
                ),
            ),
            warnings=(),
            metrics={},
        )

    async def synthesize_surface_answer(
        self,
        *,
        source_unit,
        candidate,
        local_relations,
        related_candidates,
        file_name: str,
        run_id: str,
    ):
        self.synthesis_calls += 1
        return draft(
            candidate.local_surface_key,
            canonical_question=f"Question {self.synthesis_calls}",
            answer=f"Answer {self.synthesis_calls}",
            source_refs=source_unit.source_refs,
        )


@pytest.mark.asyncio
async def test_cancel_after_first_progress_event_stops_before_next_llm_work() -> None:
    compiler = CancelAwareEconomyCompiler()
    cancelled = False

    async def cancel_check() -> None:
        if cancelled:
            raise KnowledgeSurfaceCompilationCancelled("cancelled by test")

    async def progress(event) -> None:
        nonlocal cancelled
        if event["stage_kind"] == "economy_instant_subunit":
            cancelled = True

    compiler.set_cancel_check(cancel_check)
    compiler.set_progress_callback(progress)

    body = "\n\n".join(("# One\n" + "A" * 5000, "# Two\n" + "B" * 5000))

    with pytest.raises(KnowledgeSurfaceCompilationCancelled):
        await compiler._compile_source_unit_in_economy_mode(
            unit_index=1,
            source_unit_count=1,
            unit=unit(body),
            file_name="faq.md",
            run_id="run-1",
            started_monotonic=time.monotonic(),
            concurrency=1,
            reason="quota_exhausted",
        )

    assert compiler.discover_calls == 1
    assert compiler.synthesis_calls == 1
