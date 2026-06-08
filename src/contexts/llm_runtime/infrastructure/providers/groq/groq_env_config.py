from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.contexts.llm_runtime.infrastructure.providers.groq.groq_http_transport import (
    GroqApiKeyRef,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    GroqAccountSeed,
)


@dataclass(frozen=True, slots=True)
class GroqEnvAccountConfig:
    """Resolved Groq account configuration.

    `account_ref` is a local capacity-slot label.
    `api_key` may contain the actual secret and must not be logged.
    """

    account_seed: GroqAccountSeed
    api_key: GroqApiKeyRef


@dataclass(frozen=True, slots=True)
class GroqEnvConfig:
    accounts: tuple[GroqEnvAccountConfig, ...]

    def __post_init__(self) -> None:
        if not self.accounts:
            raise ValueError("GroqEnvConfig.accounts must not be empty")


@dataclass(frozen=True, slots=True)
class GroqEnvAccountSpec:
    account_ref: str
    env_var_name: str
    account_rank: int

    def __post_init__(self) -> None:
        if not self.account_ref or not self.account_ref.strip():
            raise ValueError("account_ref must be non-empty")
        if not self.env_var_name or not self.env_var_name.strip():
            raise ValueError("env_var_name must be non-empty")
        if self.account_rank < 0:
            raise ValueError("account_rank must be >= 0")


class GroqEnvConfigLoader:
    """Load explicit Groq account configuration from a provided mapping.

    The mapping is injected so this loader is testable and does not directly
    depend on global process environment in domain/application code.
    """

    def load(
        self,
        *,
        env: Mapping[str, str],
        account_specs: tuple[GroqEnvAccountSpec, ...],
    ) -> GroqEnvConfig:
        if not account_specs:
            raise ValueError("account_specs must not be empty")

        accounts: list[GroqEnvAccountConfig] = []

        for spec in account_specs:
            raw_value = env.get(spec.env_var_name)
            if raw_value is None or not raw_value.strip():
                continue

            accounts.append(
                GroqEnvAccountConfig(
                    account_seed=GroqAccountSeed(
                        account_ref=spec.account_ref,
                        account_rank=spec.account_rank,
                    ),
                    api_key=GroqApiKeyRef(raw_value),
                ),
            )

        if not accounts:
            raise ValueError(
                "No Groq API keys were resolved from provided account specs"
            )

        return GroqEnvConfig(accounts=tuple(accounts))
