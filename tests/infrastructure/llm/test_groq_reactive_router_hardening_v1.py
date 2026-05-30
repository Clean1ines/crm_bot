from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.llm.groq_router import (
    GROQ_MODEL_LLAMA_31_8B,
    GROQ_MODEL_LLAMA_33_70B,
    GROQ_MODEL_LLAMA_4_SCOUT,
    GROQ_MODEL_QWEN3_32B,
    GroqFallbackExhaustedError,
    GroqFallbackPolicy,
    GroqLimitKind,
    GroqModelRouter,
    GroqRouteFailureType,
    classify_groq_exception,
)
from src.infrastructure.llm.knowledge_surface_economy_instant import (
    GroqEconomyInstantKnowledgeSurfaceGraphCompiler,
)
from src.infrastructure.llm.knowledge_surface_graph_compiler_v2 import (
    _is_large_request_error,
)
from src.infrastructure.llm.knowledge_surface_parallel_graph_compiler import (
    DEFAULT_FAQ_SURFACE_GRAPH_CONCURRENCY,
    GroqParallelKnowledgeSurfaceGraphCompiler,
)


class ProviderError(RuntimeError):
    def __init__(self, text: str, *, status_code: int | None = None) -> None:
        super().__init__(text)
        self.status_code = status_code


@pytest.mark.asyncio
async def test_instant_first_chain_is_hard_invariant() -> None:
    seen_models: list[str] = []
    router = GroqModelRouter()

    async def create_call(kwargs: dict[str, object]) -> str:
        seen_models.append(str(kwargs["model"]))
        return "ok"

    result = await router.run_chat_completion(
        create_call=create_call,
        kwargs={"model": GROQ_MODEL_LLAMA_33_70B},
        operation_name="test",
    )

    assert result == "ok"
    assert seen_models[0] == GROQ_MODEL_LLAMA_31_8B


def test_no_output_prediction_symbols() -> None:
    root = Path(__file__).resolve().parents[3]
    forbidden = (
        "_estimate_request" + "_tokens",
        "GROQ_INSTANT_FREE_" + "TPM_LIMIT",
        "expected_output" + "_tokens",
        "max_completion_tokens" + " table",
        "task_" + "kind",
    )

    for path in (root / "src").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{marker} found in {path}"


def test_tpm_is_not_large_request_error() -> None:
    exc = ProviderError(
        "Rate limit reached: tokens per minute TPM exhausted",
        status_code=429,
    )

    assert classify_groq_exception(exc) == GroqLimitKind.TPM
    assert _is_large_request_error(exc) is False


def test_output_too_large_is_classified() -> None:
    markers = (
        "max_completion_tokens is too high for this model",
        "maximum completion tokens exceeded",
        "output too large for model",
        "reduce max_tokens",
    )

    for marker in markers:
        assert classify_groq_exception(ProviderError(marker, status_code=400)) == (
            GroqLimitKind.OUTPUT_TOO_LARGE
        )


@pytest.mark.asyncio
async def test_output_too_large_routes_to_larger_output_capacity_model() -> None:
    seen_models: list[str] = []
    router = GroqModelRouter(
        GroqFallbackPolicy(
            cheap_small_chain=(GROQ_MODEL_LLAMA_31_8B,),
            primary_chain=(GROQ_MODEL_LLAMA_31_8B, GROQ_MODEL_QWEN3_32B),
            large_request_chain=(GROQ_MODEL_LLAMA_4_SCOUT,),
            max_attempts_per_call=8,
        )
    )

    async def create_call(kwargs: dict[str, object]) -> str:
        model = str(kwargs["model"])
        seen_models.append(model)
        if model == GROQ_MODEL_LLAMA_31_8B:
            raise ProviderError(
                "max_completion_tokens is too high for this model",
                status_code=400,
            )
        return model

    result = await router.run_chat_completion(
        create_call=create_call,
        kwargs={"model": GROQ_MODEL_LLAMA_31_8B},
        operation_name="test",
    )

    assert seen_models[0] == GROQ_MODEL_LLAMA_31_8B
    assert result in {GROQ_MODEL_QWEN3_32B, GROQ_MODEL_LLAMA_4_SCOUT}
    assert result != GROQ_MODEL_LLAMA_31_8B


@pytest.mark.asyncio
async def test_all_fallbacks_exhausted_uses_economy_instant_split(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    async def fake_economy(
        self: GroqEconomyInstantKnowledgeSurfaceGraphCompiler,
        **kwargs: object,
    ) -> str:
        called["reason"] = kwargs["reason"]
        return "economy-result"

    monkeypatch.setattr(
        GroqEconomyInstantKnowledgeSurfaceGraphCompiler,
        "_compile_source_unit_in_economy_mode",
        fake_economy,
    )

    async def failing_parent(
        self: GroqEconomyInstantKnowledgeSurfaceGraphCompiler,
        **kwargs: object,
    ) -> object:
        raise GroqFallbackExhaustedError(
            failure_type=GroqRouteFailureType.OUTPUT_TOO_LARGE,
            message="output too large",
        )

    monkeypatch.setattr(
        GroqParallelKnowledgeSurfaceGraphCompiler,
        "_compile_source_unit",
        failing_parent,
    )

    compiler = GroqEconomyInstantKnowledgeSurfaceGraphCompiler(
        client=object(),
        model=GROQ_MODEL_LLAMA_31_8B,
    )
    result = await compiler._compile_source_unit(
        unit_index=1,
        source_unit_count=1,
        unit=object(),
        file_name="x.md",
        run_id="run",
        started_monotonic=0.0,
        concurrency=3,
    )

    assert result == "economy-result"
    assert called["reason"] == GroqRouteFailureType.OUTPUT_TOO_LARGE.value


def test_faq_surface_graph_concurrency_is_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAQ_SURFACE_GRAPH_CONCURRENCY", "8")

    compiler = GroqParallelKnowledgeSurfaceGraphCompiler(
        client=object(),
        model=GROQ_MODEL_LLAMA_31_8B,
    )

    assert DEFAULT_FAQ_SURFACE_GRAPH_CONCURRENCY == 3
    assert compiler._concurrency() == 3


def test_output_too_large_exhaustion_failure_type() -> None:
    router = GroqModelRouter()
    exc = router._exhausted_error(
        last_limit_kind=GroqLimitKind.OUTPUT_TOO_LARGE,
        last_error=ProviderError("output too large"),
        reason="test",
    )

    assert exc.failure_type == GroqRouteFailureType.OUTPUT_TOO_LARGE
