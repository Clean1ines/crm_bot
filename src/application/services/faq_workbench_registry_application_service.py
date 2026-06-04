from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from typing import Protocol

from src.application.ports.knowledge_workbench import (
    KnowledgeWorkbenchRegistryApplicationRepositoryPort,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    JsonValue,
    FactRegistry,
    RegistrySnapshot,
)


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(slots=True)
class MonotonicIdFactory:
    _counter: count[int]

    @classmethod
    def create(cls) -> MonotonicIdFactory:
        return cls(_counter=count(1))

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._counter)}"


@dataclass(frozen=True, slots=True)
class ApplyFactRegistrySnapshotCommand:
    """Persist Prompt C output as the next canonical registry snapshot.

    This service intentionally no longer applies Python-level surface/question
    update operations. Prompt C already produced the semantic registry state.
    The application step is now a thin single-writer persistence boundary.
    """

    registry: FactRegistry
    fact_registry: dict[str, JsonValue]
    registry_update_summary: dict[str, JsonValue]
    previous_snapshot_id: str | None
    previous_snapshot_sequence_number: int
    after_node_run_id: str
    after_section_id: str | None = None


@dataclass(frozen=True, slots=True)
class ApplyFactRegistrySnapshotResult:
    snapshot: RegistrySnapshot
    fact_registry: dict[str, JsonValue]
    registry_update_summary: dict[str, JsonValue]


class FaqWorkbenchRegistryApplicationService:
    def __init__(
        self,
        repository: KnowledgeWorkbenchRegistryApplicationRepositoryPort,
        *,
        id_factory: IdFactory,
        time_provider: TimeProvider | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._time_provider = time_provider or SystemTimeProvider()

    async def apply_fact_registry_snapshot(
        self,
        command: ApplyFactRegistrySnapshotCommand,
    ) -> ApplyFactRegistrySnapshotResult:
        self._validate_command(command)

        now = self._time_provider.now()
        snapshot_id = self._id_factory.new_id("registry-snapshot")

        canonical_facts = command.fact_registry["canonical_facts"]
        fact_relations = command.fact_registry["fact_relations"]
        if not isinstance(canonical_facts, list):
            raise DomainInvariantError("fact_registry.canonical_facts must be a list")
        if not isinstance(fact_relations, list):
            raise DomainInvariantError("fact_registry.fact_relations must be a list")

        update_count = (
            _non_negative_int(command.registry_update_summary, "created_fact_count")
            + _non_negative_int(command.registry_update_summary, "updated_fact_count")
            + _non_negative_int(
                command.registry_update_summary, "created_relation_count"
            )
        )

        snapshot = RegistrySnapshot(
            snapshot_id=snapshot_id,
            registry_id=command.registry.registry_id,
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            after_section_id=command.after_section_id,
            after_node_run_id=command.after_node_run_id,
            sequence_number=command.previous_snapshot_sequence_number + 1,
            entries_payload={
                "contract": "fact_registry",
                "previous_snapshot_id": command.previous_snapshot_id,
                "fact_registry": command.fact_registry,
                "registry_update_summary": command.registry_update_summary,
            },
            relations_payload={
                "contract": "fact_registry_relations",
                "fact_relations": fact_relations,
            },
            entry_count=len(canonical_facts),
            relation_count=len(fact_relations),
            claim_observation_count=0,
            update_count=update_count,
            created_at=now,
        )

        await self._repository.create_registry_snapshot(snapshot)

        return ApplyFactRegistrySnapshotResult(
            snapshot=snapshot,
            fact_registry=command.fact_registry,
            registry_update_summary=command.registry_update_summary,
        )

    def _validate_command(self, command: ApplyFactRegistrySnapshotCommand) -> None:
        if command.registry.status.value in {"deleted", "invalidated"}:
            raise DomainInvariantError(
                "cannot apply fact registry snapshot to deleted/invalidated registry"
            )
        if command.previous_snapshot_sequence_number < 0:
            raise DomainInvariantError(
                "previous_snapshot_sequence_number must be non-negative"
            )
        if not command.after_node_run_id.strip():
            raise DomainInvariantError(
                "fact registry snapshot requires after_node_run_id"
            )

        self._validate_fact_registry(command.fact_registry)
        self._validate_registry_update_summary(command.registry_update_summary)

    def _validate_fact_registry(self, fact_registry: dict[str, JsonValue]) -> None:
        version = fact_registry.get("version")
        if not isinstance(version, int) or version < 1:
            raise DomainInvariantError(
                "fact_registry.version must be a positive integer"
            )

        canonical_facts = fact_registry.get("canonical_facts")
        if not isinstance(canonical_facts, list):
            raise DomainInvariantError("fact_registry.canonical_facts must be a list")

        fact_relations = fact_registry.get("fact_relations")
        if not isinstance(fact_relations, list):
            raise DomainInvariantError("fact_registry.fact_relations must be a list")

        fact_ids: set[str] = set()
        for index, raw_fact in enumerate(canonical_facts):
            if not isinstance(raw_fact, dict):
                raise DomainInvariantError(f"canonical fact #{index} must be an object")

            fact_id = _required_str(raw_fact, "fact_id", f"canonical fact #{index}")
            if fact_id in fact_ids:
                raise DomainInvariantError(f"duplicate canonical fact id: {fact_id}")
            fact_ids.add(fact_id)

            _required_str(raw_fact, "claim", f"canonical fact #{index}")
            _required_str(raw_fact, "claim_kind", f"canonical fact #{index}")
            _required_str(raw_fact, "granularity", f"canonical fact #{index}")
            _required_str(raw_fact, "status", f"canonical fact #{index}")
            _required_list(raw_fact, "triples", f"canonical fact #{index}")
            _required_list(raw_fact, "mentions", f"canonical fact #{index}")
            _required_list(raw_fact, "question_variants", f"canonical fact #{index}")
            _required_list(raw_fact, "derived_fact_notes", f"canonical fact #{index}")

        for index, raw_relation in enumerate(fact_relations):
            if not isinstance(raw_relation, dict):
                raise DomainInvariantError(f"fact relation #{index} must be an object")

            source_fact_id = _required_str(
                raw_relation,
                "source_fact_id",
                f"fact relation #{index}",
            )
            target_fact_id = _required_str(
                raw_relation,
                "target_fact_id",
                f"fact relation #{index}",
            )
            _required_str(raw_relation, "relation", f"fact relation #{index}")
            _required_str(raw_relation, "reason", f"fact relation #{index}")

            if source_fact_id not in fact_ids:
                raise DomainInvariantError(
                    f"fact relation #{index} references unknown source_fact_id"
                )
            if target_fact_id not in fact_ids:
                raise DomainInvariantError(
                    f"fact relation #{index} references unknown target_fact_id"
                )

    def _validate_registry_update_summary(
        self,
        registry_update_summary: dict[str, JsonValue],
    ) -> None:
        for key in (
            "created_fact_count",
            "updated_fact_count",
            "created_relation_count",
        ):
            _non_negative_int(registry_update_summary, key)

        notes = registry_update_summary.get("notes")
        if not isinstance(notes, list):
            raise DomainInvariantError("registry_update_summary.notes must be a list")


def _required_str(
    payload: dict[str, JsonValue],
    key: str,
    context: str,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DomainInvariantError(f"{context}.{key} is required")
    return value.strip()


def _required_list(
    payload: dict[str, JsonValue],
    key: str,
    context: str,
) -> list[JsonValue]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise DomainInvariantError(f"{context}.{key} must be a list")
    return value


def _non_negative_int(
    payload: dict[str, JsonValue],
    key: str,
) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or value < 0:
        raise DomainInvariantError(
            f"registry_update_summary.{key} must be a non-negative integer"
        )
    return value


__all__ = [
    "ApplyFactRegistrySnapshotCommand",
    "ApplyFactRegistrySnapshotResult",
    "FaqWorkbenchRegistryApplicationService",
    "MonotonicIdFactory",
]
