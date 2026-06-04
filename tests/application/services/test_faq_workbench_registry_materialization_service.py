from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Mapping

import pytest

from src.application.services.faq_workbench_registry_materialization_service import (
    FaqWorkbenchRegistryMaterializationService,
    MaterializeFactRegistrySnapshotCommand,
)
from src.domain.project_plane.knowledge_workbench import RegistrySnapshot


@dataclass(slots=True)
class FakeRepository:
    canonical_facts: tuple[Mapping[str, object], ...] = ()
    fact_mentions: tuple[Mapping[str, object], ...] = ()
    fact_relations: tuple[Mapping[str, object], ...] = ()
    surfaces: tuple[Mapping[str, object], ...] = ()
    calls: list[str] = field(default_factory=list)

    async def replace_canonical_facts_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        canonical_facts: tuple[Mapping[str, object], ...],
    ) -> int:
        self.calls.append(f"canonical:{snapshot.snapshot_id}")
        self.canonical_facts = canonical_facts
        return len(canonical_facts)

    async def replace_fact_mentions_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        fact_mentions: tuple[Mapping[str, object], ...],
    ) -> int:
        self.calls.append(f"mentions:{snapshot.snapshot_id}")
        self.fact_mentions = fact_mentions
        return len(fact_mentions)

    async def replace_fact_relations_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        fact_relations: tuple[Mapping[str, object], ...],
    ) -> int:
        self.calls.append(f"relations:{snapshot.snapshot_id}")
        self.fact_relations = fact_relations
        return len(fact_relations)

    async def replace_surfaces_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        surfaces: tuple[Mapping[str, object], ...],
    ) -> int:
        self.calls.append(f"surfaces:{snapshot.snapshot_id}")
        self.surfaces = surfaces
        return len(surfaces)


def _snapshot() -> RegistrySnapshot:
    return RegistrySnapshot(
        snapshot_id="snapshot-1",
        registry_id="registry-1",
        processing_run_id="run-1",
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        after_node_run_id="node-run-1",
        sequence_number=2,
        entries_payload={
            "contract": "fact_registry",
            "fact_registry": {
                "version": 1,
                "canonical_facts": [
                    {
                        "fact_id": "fact-1",
                        "fact_key": "fact-1",
                        "claim": "Бот отвечает клиентам в Telegram.",
                        "claim_kind": "capability",
                        "granularity": "atomic",
                        "question_variants": ["Может ли бот отвечать клиентам?"],
                        "answer": "Да, бот отвечает клиентам в Telegram.",
                        "scope": "Telegram",
                        "exclusion_scope": "",
                        "source_refs": ["section-1"],
                        "evidence": ["evidence text"],
                        "mentions": [
                            {
                                "source_section_id": "section-1",
                                "source_section_ref": "section-1",
                                "source_local_ref": "c1",
                                "evidence_block": "evidence text",
                            }
                        ],
                        "derived_fact_notes": [],
                        "status": "active",
                    }
                ],
                "fact_relations": [
                    {
                        "source_fact_id": "fact-1",
                        "target_fact_id": "fact-2",
                        "relation": "supports",
                        "reason": "test relation",
                    }
                ],
            },
        },
        relations_payload={"contract": "fact_registry_relations"},
        entry_count=1,
        relation_count=1,
        claim_observation_count=1,
        update_count=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_materializes_fact_registry_snapshot_into_first_class_tables() -> None:
    repository = FakeRepository()
    service = FaqWorkbenchRegistryMaterializationService(repository)

    result = await service.materialize_fact_registry_snapshot(
        MaterializeFactRegistrySnapshotCommand(snapshot=_snapshot())
    )

    assert result.canonical_fact_count == 1
    assert result.fact_mention_count == 1
    assert result.fact_relation_count == 1
    assert result.surface_count == 1

    assert repository.calls == [
        "canonical:snapshot-1",
        "mentions:snapshot-1",
        "relations:snapshot-1",
        "surfaces:snapshot-1",
    ]

    fact = repository.canonical_facts[0]
    assert fact["fact_id"] == "fact-1"
    assert fact["registry_id"] == "registry-1"
    assert fact["possible_questions"] == ("Может ли бот отвечать клиентам?",)
    assert fact["scope"] == "Telegram"

    mention = repository.fact_mentions[0]
    assert mention["fact_id"] == "fact-1"
    assert mention["registry_id"] == "registry-1"
    assert mention["source_section_id"] == "section-1"
    assert mention["evidence_block"] == "evidence text"

    relation = repository.fact_relations[0]
    assert relation["source_fact_id"] == "fact-1"
    assert relation["target_fact_id"] == "fact-2"
    assert relation["relation"] == "supports"

    surface = repository.surfaces[0]
    assert surface["fact_id"] == "fact-1"
    assert surface["status"] == "ready"
    assert surface["curation_state"] == "auto_materialized"
    assert surface["question_variants"] == ("Может ли бот отвечать клиентам?",)
