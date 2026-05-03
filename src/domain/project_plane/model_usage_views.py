from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, TypeAlias

from src.domain.project_plane.json_types import JsonObject

ModelUsageType: TypeAlias = Literal["embedding", "llm"]
ModelUsageSource: TypeAlias = Literal[
    "knowledge_upload", "knowledge_preprocessing", "rag_search"
]


@dataclass(frozen=True, slots=True)
class ModelUsageMeasurement:
    provider: str
    model: str
    usage_type: ModelUsageType
    tokens_input: int
    tokens_output: int | None
    tokens_total: int
    estimated_cost_usd: float | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelUsageEventCreate:
    project_id: str
    provider: str
    model: str
    usage_type: ModelUsageType
    source: ModelUsageSource
    tokens_input: int
    tokens_output: int | None
    tokens_total: int
    estimated_cost_usd: float | None = None
    document_id: str | None = None
    thread_id: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    @classmethod
    def from_measurement(
        cls,
        *,
        project_id: str,
        source: ModelUsageSource,
        measurement: ModelUsageMeasurement,
        document_id: str | None = None,
        thread_id: str | None = None,
    ) -> "ModelUsageEventCreate":
        return cls(
            project_id=project_id,
            provider=measurement.provider,
            model=measurement.model,
            usage_type=measurement.usage_type,
            source=source,
            tokens_input=measurement.tokens_input,
            tokens_output=measurement.tokens_output,
            tokens_total=measurement.tokens_total,
            estimated_cost_usd=measurement.estimated_cost_usd,
            document_id=document_id,
            thread_id=thread_id,
            metadata=measurement.metadata,
        )


@dataclass(frozen=True, slots=True)
class ModelUsageBreakdownView:
    provider: str
    model: str
    usage_type: ModelUsageType
    source: ModelUsageSource
    tokens_input: int
    tokens_output: int
    tokens_total: int
    estimated_cost_usd: float
    events_count: int


@dataclass(frozen=True, slots=True)
class ModelUsageDailyView:
    day: date
    tokens_total: int
    estimated_cost_usd: float


@dataclass(frozen=True, slots=True)
class ModelUsageSummaryView:
    project_id: str
    month_start: datetime
    month_end: datetime
    today_start: datetime
    tokens_month_total: int
    tokens_today_total: int
    estimated_cost_month_usd: float
    monthly_budget_tokens: int
    remaining_tokens: int
    breakdown: tuple[ModelUsageBreakdownView, ...] = ()
    daily: tuple[ModelUsageDailyView, ...] = ()
