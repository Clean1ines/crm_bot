"""Queue handlers for metrics jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from src.infrastructure.db.repositories.metrics_repository import MetricsRepository
from src.application.ports.thread_port import ThreadReadPort
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_exceptions import PermanentJobError

logger = get_logger(__name__)


async def handle_update_metrics(
    job: Mapping[str, object],
    *,
    metrics_repo: MetricsRepository,
    thread_read_repo: ThreadReadPort,
) -> None:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PermanentJobError("update_metrics payload must be an object")

    thread_id = payload.get("thread_id")
    if not thread_id:
        logger.error(
            "update_metrics job missing thread_id", extra={"job_id": job.get("id")}
        )
        raise PermanentJobError("update_metrics job missing thread_id")

    await metrics_repo.update_thread_metrics(
        thread_id=str(thread_id),
        total_messages=payload.get("total_messages"),
        ai_messages=payload.get("ai_messages"),
        manager_messages=payload.get("manager_messages"),
        escalated=payload.get("escalated"),
        resolution_time=payload.get("resolution_time"),
    )

    if payload.get("close_ticket"):
        thread_info = await thread_read_repo.get_thread_with_project_view(
            str(thread_id)
        )
        if not thread_info:
            logger.warning(
                "Thread not found for project daily update",
                extra={"thread_id": thread_id},
            )
            return

        project_id = getattr(thread_info, "project_id", None)
        if not project_id and isinstance(thread_info, Mapping):
            project_id = thread_info.get("project_id")

        if project_id:
            await metrics_repo.update_project_daily_metrics(
                project_id=str(project_id),
                date=datetime.utcnow().date(),
                total_threads_delta=1,
                escalations_delta=1 if payload.get("escalated") else 0,
            )


async def handle_aggregate_metrics(
    job: Mapping[str, object],
    *,
    metrics_repo: MetricsRepository,
) -> None:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PermanentJobError("aggregate_metrics payload must be an object")

    date_str = payload.get("date")
    if not date_str:
        logger.error(
            "aggregate_metrics job missing date", extra={"job_id": job.get("id")}
        )
        raise PermanentJobError("aggregate_metrics job missing date")

    try:
        target_date = datetime.strptime(str(date_str), "%Y-%m-%d").date()
    except ValueError as exc:
        logger.error("Invalid aggregate_metrics date format", extra={"date": date_str})
        raise PermanentJobError(
            f"Invalid aggregate_metrics date format: {date_str}"
        ) from exc

    await metrics_repo.aggregate_for_date(target_date)
