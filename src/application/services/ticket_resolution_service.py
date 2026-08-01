from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from src.application.errors import ConflictError, ValidationError
from src.application.ports.conversation_summary_port import (
    ConversationSummaryGeneratorPort,
    TicketResolutionInput,
    TicketResolutionPayload,
    TicketResolutionSource,
    TicketResolutionStatus,
    TicketResolutionSummary,
)
from src.domain.runtime.language_policy import normalize_project_language
from src.domain.runtime.project_runtime_profile import ProjectRuntimeProfile


STRUCTURED_RESOLUTION_FIELDS = (
    "discussed_questions",
    "resolved_questions",
    "unresolved_questions",
    "manager_decisions",
    "customer_facts",
    "business_commitments",
)


class TicketResolutionService:
    def __init__(
        self,
        *,
        thread_runtime_state_repo,
        thread_read_repo,
        thread_message_repo=None,
        event_repo=None,
        memory_repo=None,
        project_configuration_repo=None,
        summary_generator: ConversationSummaryGeneratorPort | None = None,
        logger=None,
    ) -> None:
        self.thread_runtime_state_repo = thread_runtime_state_repo
        self.thread_read_repo = thread_read_repo
        self.thread_message_repo = thread_message_repo
        self.event_repo = event_repo
        self.memory_repo = memory_repo
        self.project_configuration_repo = project_configuration_repo
        self.summary_generator = summary_generator
        self.logger = logger

    async def generate_after_manager_close(
        self, thread_id: str
    ) -> TicketResolutionPayload | None:
        thread = await self.thread_read_repo.get_thread_with_project_view(thread_id)
        if not thread or not thread.project_id:
            return None

        current = await self._ticket_resolution(thread_id)
        base_version = _resolution_version(current)
        pending_version = base_version + 1
        final_version = base_version + 2
        pending_summary = thread.context_summary or "Итог обращения формируется."
        pending_resolution = build_ticket_resolution_payload(
            summary_text=pending_summary,
            status="pending",
            source=None,
            version=pending_version,
        )
        pending_written = (
            await self.thread_runtime_state_repo.compare_and_update_ticket_resolution(
                thread_id,
                expected_version=base_version,
                summary=pending_summary,
                resolution=pending_resolution,
            )
        )
        if not pending_written:
            self._log_warning(
                "ticket_resolution_pending_conflict",
                {
                    "project_id": thread.project_id,
                    "thread_id": thread_id,
                    "expected_version": base_version,
                },
            )
            return await self._ticket_resolution(thread_id)

        async def write_final(
            *,
            summary: str,
            resolution: TicketResolutionPayload,
        ) -> TicketResolutionPayload | None:
            written = await self.thread_runtime_state_repo.compare_and_update_ticket_resolution(
                thread_id,
                expected_version=pending_version,
                summary=summary,
                resolution=resolution,
            )
            if written:
                return resolution
            self._log_warning(
                "ticket_resolution_final_conflict",
                {
                    "project_id": thread.project_id,
                    "thread_id": thread_id,
                    "expected_version": pending_version,
                    "status": resolution.get("status"),
                },
            )
            return await self._ticket_resolution(thread_id)

        if self.summary_generator is None:
            summary = thread.context_summary or "Обращение закрыто менеджером."
            resolution = build_ticket_resolution_payload(
                summary_text=summary,
                status="missing",
                source=None,
                version=final_version,
            )
            return await write_final(summary=summary, resolution=resolution)

        self._log_info(
            "ticket_resolution_generation_started",
            {
                "project_id": thread.project_id,
                "thread_id": thread_id,
                "client_id": thread.client_id,
                "summary_version": pending_version,
            },
        )
        try:
            generated = await self.summary_generator.generate_ticket_resolution(
                await self._build_input(thread)
            )
            resolution = build_generated_ticket_resolution_payload(
                generated,
                version=final_version,
            )
            result = await write_final(
                summary=generated.summary_text,
                resolution=resolution,
            )
            if result is not None and result.get("status") == "generated":
                self._log_info(
                    "ticket_resolution_generated",
                    {
                        "project_id": thread.project_id,
                        "thread_id": thread_id,
                        "client_id": thread.client_id,
                        "summary_status": "generated",
                        "summary_version": final_version,
                    },
                )
            return result
        except Exception as exc:
            fallback_summary = (
                thread.context_summary or "Итог обращения не сформирован."
            )
            resolution = build_ticket_resolution_payload(
                summary_text=fallback_summary,
                status="failed",
                source="llm",
                version=final_version,
                error_type=type(exc).__name__,
            )
            result = await write_final(summary=fallback_summary, resolution=resolution)
            self._log_warning(
                "ticket_resolution_generation_failed",
                {
                    "project_id": thread.project_id,
                    "thread_id": thread_id,
                    "client_id": thread.client_id,
                    "summary_status": "failed",
                    "summary_version": final_version,
                    "error_type": type(exc).__name__,
                },
            )
            return result

    async def edit(
        self,
        *,
        thread_id: str,
        summary_text: str,
        expected_version: int,
        actor_user_id: str,
    ) -> TicketResolutionPayload:
        summary = " ".join(summary_text.split())
        if not summary:
            raise ValidationError("summary_text must not be blank")
        if len(summary) > 2000:
            raise ValidationError("summary_text is too long")

        current = await self._require_resolution_for_mutation(
            thread_id,
            allowed_statuses={"generated", "edited", "failed"},
        )
        if _resolution_version(current) != expected_version:
            raise ConflictError("Ticket resolution version conflict")

        resolution = build_ticket_resolution_payload(
            summary_text=summary,
            status="edited",
            source="manager",
            version=expected_version + 1,
            previous=current,
        )
        await self._compare_and_update(
            thread_id,
            expected_version=expected_version,
            summary=summary,
            resolution=resolution,
        )
        await self._emit_thread_event(
            thread_id,
            "ticket_resolution_edited",
            {"actor_user_id": actor_user_id, "version": expected_version + 1},
        )
        return resolution

    async def regenerate(
        self,
        *,
        thread_id: str,
        actor_user_id: str,
    ) -> TicketResolutionPayload:
        if self.summary_generator is None:
            raise ValidationError("summary generator is not configured")

        current = await self._require_resolution_for_mutation(
            thread_id,
            allowed_statuses={"generated", "edited", "failed", "missing"},
        )
        expected_version = _resolution_version(current)
        thread = await self.thread_read_repo.get_thread_with_project_view(thread_id)
        if not thread or not thread.project_id:
            raise ValidationError("Thread not found")

        generated = await self.summary_generator.generate_ticket_resolution(
            await self._build_input(thread)
        )
        resolution = build_generated_ticket_resolution_payload(
            generated,
            version=expected_version + 1,
        )
        await self._compare_and_update(
            thread_id,
            expected_version=expected_version,
            summary=generated.summary_text,
            resolution=resolution,
        )
        await self._emit_thread_event(
            thread_id,
            "ticket_resolution_regenerated",
            {"actor_user_id": actor_user_id, "version": expected_version + 1},
        )
        return resolution

    async def _compare_and_update(
        self,
        thread_id: str,
        *,
        expected_version: int,
        summary: str,
        resolution: TicketResolutionPayload,
    ) -> None:
        updated = (
            await self.thread_runtime_state_repo.compare_and_update_ticket_resolution(
                thread_id,
                expected_version=expected_version,
                summary=summary,
                resolution=resolution,
            )
        )
        if not updated:
            raise ConflictError("Ticket resolution version conflict")

    async def _require_resolution_for_mutation(
        self,
        thread_id: str,
        *,
        allowed_statuses: set[str],
    ) -> dict[str, object]:
        thread = await self.thread_read_repo.get_thread_with_project_view(thread_id)
        if not thread or not thread.project_id:
            raise ValidationError("Thread not found")
        if thread.status != "closed":
            raise ValidationError("Ticket resolution can be changed only after close")

        current = await self._ticket_resolution(thread_id)
        if not isinstance(current, dict):
            raise ValidationError("Thread has no manager ticket resolution")
        status = str(current.get("status") or "")
        if status not in allowed_statuses:
            raise ValidationError("Ticket resolution status cannot be changed manually")
        return current

    async def _ticket_resolution(self, thread_id: str) -> dict[str, object] | None:
        resolution = await self.thread_runtime_state_repo.get_ticket_resolution(
            thread_id
        )
        return resolution if isinstance(resolution, dict) else None

    async def _build_input(self, thread) -> TicketResolutionInput:
        messages: list[dict[str, object]] = []
        if self.thread_message_repo is not None and hasattr(
            self.thread_message_repo, "get_messages"
        ):
            raw_messages = await self.thread_message_repo.get_messages(
                thread.thread_id, 30, 0
            )
            messages = [_record(item) for item in raw_messages]

        events: list[dict[str, object]] = []
        if self.event_repo is not None and hasattr(
            self.event_repo, "get_events_for_thread"
        ):
            raw_events = await self.event_repo.get_events_for_thread(
                thread.thread_id, 30, 0
            )
            events = [_record(item) for item in reversed(list(raw_events)[:30])]

        user_memory: dict[str, object] = {}
        if self.memory_repo is not None and thread.project_id and thread.client_id:
            raw_memory = await self.memory_repo.get_for_user_view(
                thread.project_id,
                thread.client_id,
                limit=20,
            )
            user_memory = {
                str(item.key): item.value for item in raw_memory if hasattr(item, "key")
            }

        return TicketResolutionInput(
            project_id=thread.project_id,
            thread_id=thread.thread_id,
            existing_context_summary=thread.context_summary,
            messages=messages,
            events=events,
            user_memory=user_memory,
            target_language=await self._resolve_target_language(thread.project_id),
        )

    async def _resolve_target_language(self, project_id: str) -> str:
        if self.project_configuration_repo is None or not hasattr(
            self.project_configuration_repo,
            "get_project_configuration_view",
        ):
            return "ru"
        try:
            config = (
                await self.project_configuration_repo.get_project_configuration_view(
                    project_id
                )
            )
        except Exception as exc:
            self._log_warning(
                "ticket_resolution_project_language_load_failed",
                {
                    "project_id": project_id,
                    "error_type": type(exc).__name__,
                },
            )
            return "ru"
        record = (
            config.to_runtime_record()
            if hasattr(config, "to_runtime_record")
            else config
        )
        profile = ProjectRuntimeProfile.from_configuration(record)
        language = normalize_project_language(
            profile.target_language or profile.default_language or "ru"
        )
        return language if language in {"ru", "en", "de", "es"} else "ru"

    async def _emit_thread_event(
        self,
        thread_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        if self.event_repo is None or self.thread_read_repo is None:
            return
        thread = await self.thread_read_repo.get_thread_with_project_view(thread_id)
        if not thread or not thread.project_id:
            return
        await self.event_repo.append(
            stream_id=UUID(thread_id),
            project_id=UUID(thread.project_id),
            event_type=event_type,
            payload=payload,
        )

    def _log_info(self, message: str, extra: dict[str, object]) -> None:
        if self.logger is not None:
            self.logger.info(message, extra=extra)

    def _log_warning(self, message: str, extra: dict[str, object]) -> None:
        if self.logger is not None:
            self.logger.warning(message, extra=extra)


def build_generated_ticket_resolution_payload(
    summary: TicketResolutionSummary,
    *,
    version: int,
) -> TicketResolutionPayload:
    return build_ticket_resolution_payload(
        summary_text=summary.summary_text,
        status="generated",
        source="llm",
        version=version,
        structured={
            "discussed_questions": summary.discussed_questions,
            "resolved_questions": summary.resolved_questions,
            "unresolved_questions": summary.unresolved_questions,
            "manager_decisions": summary.manager_decisions,
            "customer_facts": summary.customer_facts,
            "business_commitments": summary.business_commitments,
        },
    )


def build_ticket_resolution_payload(
    *,
    summary_text: str,
    status: TicketResolutionStatus,
    source: TicketResolutionSource,
    version: int,
    structured: dict[str, object] | None = None,
    previous: dict[str, object] | None = None,
    error_type: str | None = None,
) -> TicketResolutionPayload:
    now = datetime.now(UTC).isoformat()
    payload: dict[str, object] = {
        "summary_text": summary_text[:2000],
        "status": status,
        "source": source,
        "version": version,
        "generated_at": _previous_generated_at(previous) if source != "llm" else now,
        "updated_at": now,
    }
    for key in STRUCTURED_RESOLUTION_FIELDS:
        value = (structured or {}).get(key)
        if value is None and previous is not None:
            value = previous.get(key)
        payload[key] = _string_list(value)
    if error_type:
        payload["error_type"] = error_type
    return cast(TicketResolutionPayload, payload)


def _resolution_version(value: object) -> int:
    if not isinstance(value, dict):
        return 0
    try:
        raw = value.get("version")
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str):
            return int(raw)
        return 0
    except (TypeError, ValueError):
        return 0


def _previous_generated_at(previous: dict[str, object] | None) -> str | None:
    if not isinstance(previous, dict):
        return None
    value = previous.get("generated_at")
    return str(value) if value else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:500] for item in value if str(item).strip()][:20]


def _record(item: object) -> dict[str, object]:
    if hasattr(item, "to_record"):
        value = item.to_record()
        return value if isinstance(value, dict) else {}
    if isinstance(item, dict):
        return {str(key): value for key, value in item.items()}
    return {}
