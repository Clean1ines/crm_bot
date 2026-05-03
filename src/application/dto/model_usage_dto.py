from __future__ import annotations

from dataclasses import dataclass

from src.domain.project_plane.model_usage_views import (
    ModelUsageBreakdownView,
    ModelUsageDailyView,
    ModelUsageSummaryView,
)


@dataclass(frozen=True, slots=True)
class ModelUsageBreakdownDto:
    provider: str
    model: str
    usage_type: str
    source: str
    tokens_input: int
    tokens_output: int
    tokens_total: int
    estimated_cost_usd: float
    events_count: int

    @classmethod
    def from_view(cls, view: ModelUsageBreakdownView) -> "ModelUsageBreakdownDto":
        return cls(
            provider=view.provider,
            model=view.model,
            usage_type=view.usage_type,
            source=view.source,
            tokens_input=view.tokens_input,
            tokens_output=view.tokens_output,
            tokens_total=view.tokens_total,
            estimated_cost_usd=view.estimated_cost_usd,
            events_count=view.events_count,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "usage_type": self.usage_type,
            "source": self.source,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "tokens_total": self.tokens_total,
            "estimated_cost_usd": self.estimated_cost_usd,
            "events_count": self.events_count,
        }


@dataclass(frozen=True, slots=True)
class ModelUsageDailyDto:
    day: str
    tokens_total: int
    estimated_cost_usd: float

    @classmethod
    def from_view(cls, view: ModelUsageDailyView) -> "ModelUsageDailyDto":
        return cls(
            day=view.day.isoformat(),
            tokens_total=view.tokens_total,
            estimated_cost_usd=view.estimated_cost_usd,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "day": self.day,
            "tokens_total": self.tokens_total,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


@dataclass(frozen=True, slots=True)
class ModelUsageSummaryDto:
    counter_enabled: bool
    monthly_budget_tokens: int
    remaining_tokens: int
    tokens_month_total: int
    tokens_today_total: int
    estimated_cost_month_usd: float
    breakdown: tuple[ModelUsageBreakdownDto, ...]
    daily: tuple[ModelUsageDailyDto, ...]

    @classmethod
    def disabled(cls, *, monthly_budget_tokens: int) -> "ModelUsageSummaryDto":
        return cls(
            counter_enabled=False,
            monthly_budget_tokens=monthly_budget_tokens,
            remaining_tokens=monthly_budget_tokens,
            tokens_month_total=0,
            tokens_today_total=0,
            estimated_cost_month_usd=0.0,
            breakdown=(),
            daily=(),
        )

    @classmethod
    def from_view(
        cls,
        view: ModelUsageSummaryView,
        *,
        counter_enabled: bool,
    ) -> "ModelUsageSummaryDto":
        return cls(
            counter_enabled=counter_enabled,
            monthly_budget_tokens=view.monthly_budget_tokens,
            remaining_tokens=view.remaining_tokens,
            tokens_month_total=view.tokens_month_total,
            tokens_today_total=view.tokens_today_total,
            estimated_cost_month_usd=view.estimated_cost_month_usd,
            breakdown=tuple(
                ModelUsageBreakdownDto.from_view(item) for item in view.breakdown
            ),
            daily=tuple(ModelUsageDailyDto.from_view(item) for item in view.daily),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "counter_enabled": self.counter_enabled,
            "monthly_budget_tokens": self.monthly_budget_tokens,
            "remaining_tokens": self.remaining_tokens,
            "tokens_month_total": self.tokens_month_total,
            "tokens_today_total": self.tokens_today_total,
            "estimated_cost_month_usd": self.estimated_cost_month_usd,
            "breakdown": [item.to_dict() for item in self.breakdown],
            "daily": [item.to_dict() for item in self.daily],
        }
