from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.domain.value_objects.reasoning_effort import (
    ReasoningEffort,
)


@dataclass(frozen=True, slots=True)
class ReasoningProfile:
    """Provider-neutral reasoning capability profile for a model.

    Some models do not support reasoning controls. Some support explicit
    disabling. The domain needs to represent that without knowing any concrete
    provider API parameter names.
    """

    supported_efforts: tuple[ReasoningEffort, ...] = ()
    default_effort: ReasoningEffort | None = None

    def __post_init__(self) -> None:
        if len(set(self.supported_efforts)) != len(self.supported_efforts):
            raise ValueError(
                "ReasoningProfile.supported_efforts must not contain duplicates"
            )

        if (
            self.default_effort is not None
            and self.default_effort not in self.supported_efforts
        ):
            raise ValueError(
                "ReasoningProfile.default_effort must be one of supported_efforts"
            )

    @property
    def supports_reasoning_control(self) -> bool:
        return bool(self.supported_efforts)

    @property
    def can_disable_reasoning(self) -> bool:
        return ReasoningEffort.NONE in self.supported_efforts

    @classmethod
    def unsupported(cls) -> "ReasoningProfile":
        return cls()

    @classmethod
    def disable_capable(
        cls,
        *,
        default_effort: ReasoningEffort | None = None,
    ) -> "ReasoningProfile":
        efforts = (
            ReasoningEffort.NONE,
            ReasoningEffort.DEFAULT,
            ReasoningEffort.LOW,
            ReasoningEffort.MEDIUM,
            ReasoningEffort.HIGH,
        )
        return cls(
            supported_efforts=efforts,
            default_effort=default_effort,
        )
