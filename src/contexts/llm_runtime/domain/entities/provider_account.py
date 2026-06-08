from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_account_status import (
    ProviderAccountStatus,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId


@dataclass(frozen=True, slots=True)
class ProviderAccount:
    provider_id: ProviderId
    account_ref: ProviderAccountRef
    account_rank: int
    status: ProviderAccountStatus = ProviderAccountStatus.ENABLED

    def __post_init__(self) -> None:
        if self.account_rank < 0:
            raise ValueError("ProviderAccount.account_rank must be >= 0")

    @property
    def enabled(self) -> bool:
        return self.status is ProviderAccountStatus.ENABLED
