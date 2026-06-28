from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CapacityWindowBudgetSnapshot:
    provider: str
    account_ref: str | None
    model_ref: str
    remaining_minute_requests: int | None
    remaining_minute_tokens: int | None
    remaining_daily_requests: int | None
    remaining_daily_tokens: int | None
    reserved_minute_requests: int
    reserved_minute_tokens: int
    reserved_daily_requests: int
    reserved_daily_tokens: int
    minute_reset_at: datetime | None
    daily_reset_at: datetime | None
    frozen_until: datetime | None


@dataclass(frozen=True, slots=True)
class CapacityReservation:
    provider: str
    account_ref: str | None
    model_ref: str
    request_count: int
    token_count: int
    reserved_at: datetime


class CapacityWindowBudgetRepositoryPort(Protocol):
    async def get_window(
        self,
        *,
        provider: str,
        account_ref: str | None,
        model_ref: str,
    ) -> CapacityWindowBudgetSnapshot: ...

    async def try_reserve(
        self,
        *,
        provider: str,
        account_ref: str | None,
        model_ref: str,
        request_count: int,
        token_count: int,
        now: datetime,
    ) -> CapacityReservation | None: ...

    async def release_reservation(
        self,
        *,
        reservation: CapacityReservation,
        now: datetime,
    ) -> None: ...

    async def apply_capacity_observation(
        self,
        *,
        provider: str,
        account_ref: str | None,
        model_ref: str,
        remaining_minute_requests: int | None,
        remaining_minute_tokens: int | None,
        remaining_daily_requests: int | None,
        remaining_daily_tokens: int | None,
        minute_reset_at: datetime | None,
        daily_reset_at: datetime | None,
        observed_at: datetime,
    ) -> CapacityWindowBudgetSnapshot: ...

    async def freeze_until(
        self,
        *,
        provider: str,
        account_ref: str | None,
        model_ref: str,
        frozen_until: datetime,
        now: datetime,
    ) -> None: ...
