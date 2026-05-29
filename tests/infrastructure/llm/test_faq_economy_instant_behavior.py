from __future__ import annotations

import pytest

from src.domain.project_plane.retrieval_surface_compilation import (
    SurfaceDiscoveryResult,
)
from src.infrastructure.llm.groq_router import (
    GroqFallbackExhaustedError,
    GroqRouteFailureType,
)
from src.infrastructure.llm.knowledge_surface_compiler import GROQ_INSTANT_MODEL_ID
from src.infrastructure.llm.knowledge_surface_economy_instant import (
    GroqEconomyInstantKnowledgeSurfaceGraphCompiler,
    _merge_economy_subunit_outputs,
)
from tests.infrastructure.llm.faq_behavior_helpers import (
    candidate,
    draft,
    ownership,
    unit,
)


def test_economy_deterministic_merge_collapses_duplicate_subunit_surfaces() -> None:
    merged_candidates, merged_drafts, merged_ownership, merge_count = (
        _merge_economy_subunit_outputs(
            run_id="run-1",
            document_id="doc-1",
            candidates=(candidate("a"), candidate("b")),
            drafts=(
                draft("a", answer="First answer.", source_refs=("chunk:0",)),
                draft("b", answer="Second answer.", source_refs=("chunk:1",)),
            ),
            ownership=(ownership("a"), ownership("b")),
        )
    )

    assert merge_count == 1
    assert [item.local_surface_key for item in merged_candidates] == ["a"]
    assert [item.candidate_key for item in merged_drafts] == ["a"]
    assert merged_drafts[0].source_refs == ("chunk:0", "chunk:1")
    assert "First answer." in merged_drafts[0].answer
    assert "Second answer." in merged_drafts[0].answer
    assert merged_drafts[0].metadata["economy_deterministic_merge"] is True
    assert [item.surface_key for item in merged_ownership] == ["a"]


class EconomyCompletesAfterQuotaCompiler(
    GroqEconomyInstantKnowledgeSurfaceGraphCompiler
):
    def __init__(self) -> None:
        super().__init__(client=object(), model="large-model")  # type: ignore[arg-type]
        self.normal_discover_failures = 0
        self.instant_discover_calls = 0
        self.synthesis_models: list[str] = []

    async def discover_surfaces_for_source_unit(
        self,
        *,
        source_unit,
        file_name: str,
        run_id: str,
        **_: object,
    ):
        if self.model_name != GROQ_INSTANT_MODEL_ID and not source_unit.metadata.get(
            "economy_instant_subunit"
        ):
            self.normal_discover_failures += 1
            raise GroqFallbackExhaustedError(
                failure_type=GroqRouteFailureType.QUOTA_EXHAUSTED,
                message="large model quota exhausted",
            )

        assert self.model_name == GROQ_INSTANT_MODEL_ID
        self.instant_discover_calls += 1
        return SurfaceDiscoveryResult(
            surface_candidates=(
                candidate(
                    f"instant-{self.instant_discover_calls}",
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
        **_: object,
    ):
        assert self.model_name == GROQ_INSTANT_MODEL_ID
        self.synthesis_models.append(self.model_name)
        return draft(
            candidate.local_surface_key,
            canonical_question="How does instant fallback work?",
            answer="Instant fallback answer.",
            source_refs=source_unit.source_refs,
        )


@pytest.mark.asyncio
async def test_large_model_quota_exhaustion_compiles_document_with_instant_economy_mode() -> (
    None
):
    compiler = EconomyCompletesAfterQuotaCompiler()

    result = await compiler.compile_surfaces(
        mode="faq",
        source_units=(unit("Small body"),),
        file_name="faq.md",
        run_id="run-1",
    )

    assert compiler.normal_discover_failures == 1
    assert compiler.instant_discover_calls >= 1
    assert compiler.synthesis_models == [GROQ_INSTANT_MODEL_ID]
    assert result.model == GROQ_INSTANT_MODEL_ID
    assert result.metrics["economy_mode"] is True
    assert result.metrics["economy_reason"] == "groq_quota_exhausted"
    assert result.graph.metrics["economy_mode"] is True
    assert result.graph.surfaces
    assert result.graph.surfaces[0].metadata["economy_mode"] is True
