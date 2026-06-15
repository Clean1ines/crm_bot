from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelExecutionSettings,
    LlmModelRoute,
    LlmModelRouteCatalog,
    LlmModelRouteRole,
    default_groq_llm_model_route_catalog,
)


WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF = "qwen/qwen3-32b"
WORKBENCH_RAG_EVAL_DEGRADED_MODEL_REF = "llama-3.1-8b-instant"
WORKBENCH_RAG_EVAL_FORBIDDEN_AUTOMATIC_MODEL_REFS = ("openai/gpt-oss-120b",)
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

    @property
    def degraded(self) -> bool:
        return self.role is LlmModelRouteRole.DEGRADED_USER_CHOICE


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionGenerationRoutePolicy:
    route_catalog: LlmModelRouteCatalog
    account_refs: tuple[str, ...] = WORKBENCH_RAG_EVAL_ACCOUNT_REFS
    provider: str = "groq"

    @classmethod
    def default(cls) -> "WorkbenchRagEvalQuestionGenerationRoutePolicy":
        return cls(route_catalog=default_groq_llm_model_route_catalog())

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

    @property
    def max_parallel_lanes(self) -> int:
        return len(self.account_refs)

    @property
    def primary_model_ref(self) -> str:
        return WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF

    def automatic_model_refs(self) -> tuple[str, ...]:
        refs = (
            self.route_catalog.primary_model_ref(),
            *self.route_catalog.automatic_fallback_model_refs(),
        )
        return tuple(ref for ref in refs if self._is_allowed_automatic_ref(ref))

    def candidate_chain(
        self,
        *,
        entry_index: int,
        allow_degraded_llama_instant: bool,
    ) -> tuple[WorkbenchRagEvalQuestionGenerationRouteCandidate, ...]:
        _require_non_negative_int(entry_index, "entry_index")
        automatic = tuple(
            self._candidate_for_route(
                route=self._require_route(model_ref),
                entry_index=entry_index,
                attempt_index=attempt_index,
            )
            for attempt_index, model_ref in enumerate(self.automatic_model_refs())
        )
        if not allow_degraded_llama_instant:
            return automatic

        degraded = self._candidate_for_route(
            route=self._require_route(
                self.route_catalog.degraded_user_choice_model_ref()
            ),
            entry_index=entry_index,
            attempt_index=len(automatic),
        )
        if degraded.model_ref != WORKBENCH_RAG_EVAL_DEGRADED_MODEL_REF:
            raise ValueError(
                "Workbench RAG Eval degraded model must be llama-3.1-8b-instant"
            )
        return (*automatic, degraded)

    def requires_degraded_confirmation_after_automatic_chain(self) -> bool:
        return (
            self.route_catalog.degraded_user_choice_model_ref()
            == WORKBENCH_RAG_EVAL_DEGRADED_MODEL_REF
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

    def _is_allowed_automatic_ref(self, model_ref: str) -> bool:
        if model_ref in WORKBENCH_RAG_EVAL_FORBIDDEN_AUTOMATIC_MODEL_REFS:
            return False
        route = self.route_catalog.route_for_model_ref(model_ref)
        if route is None:
            return False
        return route.role in (
            LlmModelRouteRole.PRIMARY,
            LlmModelRouteRole.AUTOMATIC_FALLBACK,
        )


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
