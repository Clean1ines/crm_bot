from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_dispatch_preparation import (
    WORKBENCH_RAG_EVAL_AUTOMATIC_FALLBACK_MODEL_REF,
    WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF,
    workbench_rag_eval_route_catalog,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelExecutionSettings,
    LlmModelRoute,
    LlmModelRouteCatalog,
    LlmModelRouteRole,
)


WORKBENCH_RAG_EVAL_ACCOUNT_REFS = (
    "groq_org_primary",
    "groq_org_secondary",
    "groq_org_tertiary",
    "groq_org_quaternary",
)


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionGenerationRouteCandidate:
    provider: str
    account_ref: str
    slot_index: int
    model_ref: str
    role: LlmModelRouteRole
    execution_settings: LlmModelExecutionSettings
    input_token_limit: int
    output_token_limit: int

    def __post_init__(self) -> None:
        _require_non_empty_text(self.provider, "provider")
        _require_non_empty_text(self.account_ref, "account_ref")
        _require_non_empty_text(self.model_ref, "model_ref")
        if not isinstance(self.slot_index, int):
            raise TypeError("slot_index must be int")
        if self.slot_index < 0:
            raise ValueError("slot_index must be >= 0")
        if not isinstance(self.role, LlmModelRouteRole):
            raise TypeError("role must be LlmModelRouteRole")
        if not isinstance(self.execution_settings, LlmModelExecutionSettings):
            raise TypeError("execution_settings must be LlmModelExecutionSettings")
        _require_positive_int(self.input_token_limit, "input_token_limit")
        _require_positive_int(self.output_token_limit, "output_token_limit")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionGenerationRoutePolicy:
    route_catalog: LlmModelRouteCatalog
    account_refs: tuple[str, ...] = WORKBENCH_RAG_EVAL_ACCOUNT_REFS
    provider: str = "groq"

    @classmethod
    def default(cls) -> "WorkbenchRagEvalQuestionGenerationRoutePolicy":
        return cls(route_catalog=workbench_rag_eval_route_catalog())

    def __post_init__(self) -> None:
        if not isinstance(self.route_catalog, LlmModelRouteCatalog):
            raise TypeError("route_catalog must be LlmModelRouteCatalog")
        if not isinstance(self.account_refs, tuple):
            raise TypeError("account_refs must be tuple")
        if not self.account_refs:
            raise ValueError("account_refs must be non-empty")
        for account_ref in self.account_refs:
            _require_non_empty_text(account_ref, "account_ref")
        _require_non_empty_text(self.provider, "provider")

        if (
            self.route_catalog.primary_model_ref()
            != WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF
        ):
            raise ValueError("Workbench RAG Eval primary model must be qwen/qwen3-32b")

        automatic_fallbacks = self.route_catalog.automatic_fallback_model_refs()
        if automatic_fallbacks != (WORKBENCH_RAG_EVAL_AUTOMATIC_FALLBACK_MODEL_REF,):
            raise ValueError(
                "Workbench RAG Eval automatic fallback must be openai/gpt-oss-120b"
            )

        if any(
            route.role is LlmModelRouteRole.DEGRADED_USER_CHOICE
            for route in self.route_catalog.routes
        ):
            raise ValueError(
                "Workbench RAG Eval must not expose a degraded user-choice route"
            )

    @property
    def max_parallel_lanes(self) -> int:
        return len(self.account_refs)

    @property
    def primary_model_ref(self) -> str:
        return WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF

    @property
    def automatic_fallback_model_ref(self) -> str:
        return WORKBENCH_RAG_EVAL_AUTOMATIC_FALLBACK_MODEL_REF

    def automatic_model_refs(self) -> tuple[str, ...]:
        return (
            self.primary_model_ref,
            self.automatic_fallback_model_ref,
        )

    def candidate_chain(
        self,
        *,
        entry_index: int,
    ) -> tuple[WorkbenchRagEvalQuestionGenerationRouteCandidate, ...]:
        _require_non_negative_int(entry_index, "entry_index")

        return tuple(
            self._candidate_for_route(
                route=self._require_route(model_ref),
                entry_index=entry_index,
                attempt_index=attempt_index,
            )
            for attempt_index, model_ref in enumerate(self.automatic_model_refs())
        )

    def _candidate_for_route(
        self,
        *,
        route: LlmModelRoute,
        entry_index: int,
        attempt_index: int,
    ) -> WorkbenchRagEvalQuestionGenerationRouteCandidate:
        lane_index = (entry_index + attempt_index) % len(self.account_refs)
        return WorkbenchRagEvalQuestionGenerationRouteCandidate(
            provider=self.provider,
            account_ref=self.account_refs[lane_index],
            slot_index=lane_index,
            model_ref=route.model_ref,
            role=route.role,
            execution_settings=route.execution_settings,
            input_token_limit=route.capacity_limits.input_token_limit,
            output_token_limit=route.capacity_limits.output_token_limit,
        )

    def _require_route(self, model_ref: str) -> LlmModelRoute:
        route = self.route_catalog.route_for_model_ref(model_ref)
        if route is None:
            raise ValueError(f"model_ref is not in route catalog: {model_ref}")
        return route


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
