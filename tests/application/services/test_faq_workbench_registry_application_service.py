from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_registry_application_service import (
    ApplyFactRegistrySnapshotCommand,
    FaqWorkbenchRegistryApplicationService,
    MonotonicIdFactory,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    FactRegistry,
    FactRegistryStatus,
    RegistrySnapshot,
)


@dataclass(frozen=True, slots=True)
class FixedTimeProvider:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class InMemoryRegistryApplicationRepository:
    snapshots: list[RegistrySnapshot] = field(default_factory=list)

    async def create_registry_snapshot(self, snapshot: RegistrySnapshot) -> None:
        self.snapshots.append(snapshot)


def _registry(
    *,
    status: FactRegistryStatus = FactRegistryStatus.BUILDING,
) -> FactRegistry:
    return FactRegistry(
        registry_id="registry-1",
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        status=status,
        version=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _fact_registry() -> dict:
    return {
        "version": 1,
        "canonical_facts": [
            {
                "fact_id": "cf_product_definition",
                "claim": "Продукт является платформой управления AI-базами знаний.",
                "claim_kind": "definition",
                "granularity": "atomic",
                "triples": [
                    {
                        "subject": "Продукт",
                        "predicate": "is_a",
                        "object": "платформа управления AI-базами знаний",
                        "qualifiers": [],
                    },
                ],
                "mentions": [
                    {
                        "source_section_ref": "document-1#section-0001-product",
                        "source_local_ref": "c1",
                        "evidence_block": "Продукт — это платформа управления AI-базами знаний.",
                        "mention_relation": "initial",
                    },
                ],
                "question_variants": ["Что такое продукт?"],
                "scope": "Общее определение",
                "exclusion_scope": "",
                "derived_fact_notes": [],
                "status": "active",
            },
            {
                "fact_id": "cf_product_capability",
                "claim": "Продукт помогает создавать проверяемую AI-базу знаний.",
                "claim_kind": "capability",
                "granularity": "atomic",
                "triples": [
                    {
                        "subject": "Продукт",
                        "predicate": "has_capability",
                        "object": "создавать проверяемую AI-базу знаний",
                        "qualifiers": [],
                    },
                ],
                "mentions": [
                    {
                        "source_section_ref": "document-1#section-0001-product",
                        "source_local_ref": "c2",
                        "evidence_block": "Продукт помогает создать проверяемую AI-базу знаний.",
                        "mention_relation": "new",
                    },
                ],
                "question_variants": ["Что делает продукт?"],
                "scope": "Возможности продукта",
                "exclusion_scope": "",
                "derived_fact_notes": [],
                "status": "active",
            },
        ],
        "fact_relations": [
            {
                "source_fact_id": "cf_product_capability",
                "target_fact_id": "cf_product_definition",
                "relation": "refines",
                "reason": "Уточняет определение через возможность продукта.",
            },
        ],
    }


def _summary() -> dict:
    return {
        "created_fact_count": 2,
        "updated_fact_count": 0,
        "created_relation_count": 1,
        "notes": ["bootstrap registry"],
    }


@pytest.mark.asyncio
async def test_apply_fact_registry_snapshot_persists_snapshot_without_old_entries_or_applications() -> None:
    repository = InMemoryRegistryApplicationRepository()
    service = FaqWorkbenchRegistryApplicationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
        time_provider=FixedTimeProvider(datetime(2026, 6, 1, tzinfo=timezone.utc)),
    )

    result = await service.apply_fact_registry_snapshot(
        ApplyFactRegistrySnapshotCommand(
            registry=_registry(),
            fact_registry=_fact_registry(),
            registry_update_summary=_summary(),
            previous_snapshot_id="registry-snapshot-0",
            previous_snapshot_sequence_number=1,
            after_node_run_id="node-run-fact-registry-builder",
            after_section_id="section-1",
        )
    )

    assert result.fact_registry == _fact_registry()
    assert result.registry_update_summary == _summary()

    assert repository.snapshots == [result.snapshot]
    assert result.snapshot.snapshot_id == "registry-snapshot-1"
    assert result.snapshot.registry_id == "registry-1"
    assert result.snapshot.processing_run_id == "processing-run-1"
    assert result.snapshot.after_section_id == "section-1"
    assert result.snapshot.after_node_run_id == "node-run-fact-registry-builder"
    assert result.snapshot.sequence_number == 2

    assert result.snapshot.entries_payload["contract"] == "fact_registry"
    assert result.snapshot.entries_payload["previous_snapshot_id"] == "registry-snapshot-0"
    assert result.snapshot.entries_payload["fact_registry"] == _fact_registry()
    assert result.snapshot.entries_payload["registry_update_summary"] == _summary()

    assert result.snapshot.relations_payload == {
        "contract": "fact_registry_relations",
        "fact_relations": _fact_registry()["fact_relations"],
    }
    assert result.snapshot.entry_count == 2
    assert result.snapshot.relation_count == 1
    assert result.snapshot.claim_observation_count == 0
    assert result.snapshot.update_count == 3


@pytest.mark.asyncio
async def test_apply_fact_registry_snapshot_rejects_deleted_registry() -> None:
    service = FaqWorkbenchRegistryApplicationService(
        InMemoryRegistryApplicationRepository(),
        id_factory=MonotonicIdFactory.create(),
    )

    with pytest.raises(DomainInvariantError, match="deleted/invalidated registry"):
        await service.apply_fact_registry_snapshot(
            ApplyFactRegistrySnapshotCommand(
                registry=_registry(status=FactRegistryStatus.DELETED),
                fact_registry=_fact_registry(),
                registry_update_summary=_summary(),
                previous_snapshot_id="registry-snapshot-0",
                previous_snapshot_sequence_number=1,
                after_node_run_id="node-run-fact-registry-builder",
            )
        )


@pytest.mark.parametrize(
    ("fact_registry", "message"),
    [
        ({}, "fact_registry.version must be a positive integer"),
        (
            {"version": 1, "canonical_facts": {}, "fact_relations": []},
            "fact_registry.canonical_facts must be a list",
        ),
        (
            {"version": 1, "canonical_facts": [], "fact_relations": {}},
            "fact_registry.fact_relations must be a list",
        ),
        (
            {
                "version": 1,
                "canonical_facts": [
                    {
                        "fact_id": "cf_a",
                        "claim": "A",
                        "claim_kind": "definition",
                        "granularity": "atomic",
                        "triples": [],
                        "mentions": [],
                        "question_variants": [],
                        "derived_fact_notes": [],
                        "status": "active",
                    },
                    {
                        "fact_id": "cf_a",
                        "claim": "A duplicate",
                        "claim_kind": "definition",
                        "granularity": "atomic",
                        "triples": [],
                        "mentions": [],
                        "question_variants": [],
                        "derived_fact_notes": [],
                        "status": "active",
                    },
                ],
                "fact_relations": [],
            },
            "duplicate canonical fact id",
        ),
        (
            {
                "version": 1,
                "canonical_facts": [
                    {
                        "fact_id": "cf_a",
                        "claim": "A",
                        "claim_kind": "definition",
                        "granularity": "atomic",
                        "triples": [],
                        "mentions": [],
                        "question_variants": [],
                        "derived_fact_notes": [],
                        "status": "active",
                    },
                ],
                "fact_relations": [
                    {
                        "source_fact_id": "cf_a",
                        "target_fact_id": "missing",
                        "relation": "extends",
                        "reason": "bad relation",
                    }
                ],
            },
            "unknown target_fact_id",
        ),
    ],
)
@pytest.mark.asyncio
async def test_apply_fact_registry_snapshot_validates_fact_registry_contract(
    fact_registry: dict,
    message: str,
) -> None:
    service = FaqWorkbenchRegistryApplicationService(
        InMemoryRegistryApplicationRepository(),
        id_factory=MonotonicIdFactory.create(),
    )

    with pytest.raises(DomainInvariantError, match=message):
        await service.apply_fact_registry_snapshot(
            ApplyFactRegistrySnapshotCommand(
                registry=_registry(),
                fact_registry=fact_registry,
                registry_update_summary=_summary(),
                previous_snapshot_id="registry-snapshot-0",
                previous_snapshot_sequence_number=1,
                after_node_run_id="node-run-fact-registry-builder",
            )
        )


@pytest.mark.asyncio
async def test_apply_fact_registry_snapshot_validates_summary_counts() -> None:
    service = FaqWorkbenchRegistryApplicationService(
        InMemoryRegistryApplicationRepository(),
        id_factory=MonotonicIdFactory.create(),
    )

    bad_summary = {
        "created_fact_count": -1,
        "updated_fact_count": 0,
        "created_relation_count": 0,
        "notes": [],
    }

    with pytest.raises(DomainInvariantError, match="created_fact_count"):
        await service.apply_fact_registry_snapshot(
            ApplyFactRegistrySnapshotCommand(
                registry=_registry(),
                fact_registry=_fact_registry(),
                registry_update_summary=bad_summary,
                previous_snapshot_id="registry-snapshot-0",
                previous_snapshot_sequence_number=1,
                after_node_run_id="node-run-fact-registry-builder",
            )
        )


def test_registry_application_service_repository_does_not_need_old_entry_or_application_methods() -> None:
    repository = InMemoryRegistryApplicationRepository()

    assert not hasattr(repository, "upsert_fact_registry_entries")
    assert not hasattr(repository, "create_registry_update_applications")
