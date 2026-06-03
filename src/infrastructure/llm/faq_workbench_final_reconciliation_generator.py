from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from src.application.ports.faq_workbench_final_reconciliation_generator import (
    FaqWorkbenchFinalReconciliationGenerationCommand,
    FaqWorkbenchFinalReconciliationGenerationError,
    FaqWorkbenchFinalReconciliationGenerationResult,
    FaqWorkbenchFinalReconciliationGeneratorPort,
    FinalReconciliationAdvice,
)
from src.application.ports.llm_json_invocation import LlmJsonInvocationPort
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    JsonValue,
)
from src.domain.project_plane.llm_routing import (
    LlmInvocationStatus,
    LlmJsonInvocationRequest,
)


class FaqWorkbenchFinalReconciliationInvocationError(
    FaqWorkbenchFinalReconciliationGenerationError
):
    """Infrastructure alias for final reconciliation invocation failures."""


@dataclass(frozen=True, slots=True)
class FaqWorkbenchFinalReconciliationGeneratorConfig:
    prompt_path: Path
    operation_name: str = "faq_surface_final_reconciliation"
    route_purpose: str = "workbench_final_reconciliation"


@dataclass(frozen=True, slots=True)
class FaqWorkbenchFinalReconciliationGenerator(
    FaqWorkbenchFinalReconciliationGeneratorPort
):
    llm_invocation: LlmJsonInvocationPort
    config: FaqWorkbenchFinalReconciliationGeneratorConfig

    async def generate_final_reconciliation(
        self,
        command: FaqWorkbenchFinalReconciliationGenerationCommand,
    ) -> FaqWorkbenchFinalReconciliationGenerationResult:
        prompt = self.build_prompt(command)
        result = await self.llm_invocation.invoke_json(
            LlmJsonInvocationRequest(
                operation_name=self.config.operation_name,
                prompt=prompt,
                route_purpose=self.config.route_purpose,
                idempotency_key=(
                    f"{command.registry_snapshot.document_id}:"
                    f"{command.registry_snapshot.snapshot_id}:"
                    f"{command.node_run_id}"
                ),
            )
        )

        if result.status is not LlmInvocationStatus.SUCCESS:
            raise FaqWorkbenchFinalReconciliationInvocationError(result)

        if result.parsed_json is None:
            raise DomainInvariantError(
                "final reconciliation invocation returned empty JSON"
            )

        advice = self.parse_final_reconciliation_payload(result.parsed_json)
        parsed_payload: JsonValue = {
            "surface_adjustments": advice.surface_adjustments,
            "relations": advice.relations,
            "merge_decisions": advice.merge_decisions,
            "warnings": advice.warnings,
            "metrics": advice.metrics,
        }
        raw_payload: JsonValue = {
            "operation_name": self.config.operation_name,
            "raw_text": result.raw_text,
            "parsed_json": result.parsed_json,
        }

        return FaqWorkbenchFinalReconciliationGenerationResult(
            advice=advice,
            invocation=result,
            raw_output_artifact_payload=raw_payload,
            parsed_output_artifact_payload=parsed_payload,
        )

    def build_prompt(
        self,
        command: FaqWorkbenchFinalReconciliationGenerationCommand,
    ) -> str:
        template = self.config.prompt_path.read_text(encoding="utf-8")
        payload: JsonValue = {
            "node": self.config.operation_name,
            "registry_snapshot": command.registry_snapshot.entries_payload,
            "registry_snapshot_meta": {
                "snapshot_id": command.registry_snapshot.snapshot_id,
                "registry_id": command.registry_snapshot.registry_id,
                "processing_run_id": command.registry_snapshot.processing_run_id,
                "project_id": command.registry_snapshot.project_id,
                "document_id": command.registry_snapshot.document_id,
                "sequence_number": command.registry_snapshot.sequence_number,
                "entry_count": command.registry_snapshot.entry_count,
                "relation_count": command.registry_snapshot.relation_count,
                "claim_observation_count": command.registry_snapshot.claim_observation_count,
                "update_count": command.registry_snapshot.update_count,
            },
            "canonical_facts": [
                self._registry_entry_payload(entry)
                for entry in command.canonical_facts
            ],
            "proposed_final_surfaces": command.proposed_final_surfaces,
            "proposed_relations": command.proposed_relations,
            "proposed_merge_decisions": command.proposed_merge_decisions,
            "aggregate_metrics": command.aggregate_metrics,
        }
        return template + "\n\nINPUT_JSON:\n" + self._json_dumps(payload)

    def parse_final_reconciliation_payload(
        self,
        payload: JsonValue,
    ) -> FinalReconciliationAdvice:
        if not isinstance(payload, dict):
            raise DomainInvariantError("final reconciliation payload must be an object")

        surface_adjustments = self._object_tuple(
            payload,
            "surface_adjustments",
        )
        relations = self._object_tuple(payload, "relations")
        merge_decisions = self._object_tuple(payload, "merge_decisions")
        warnings = self._string_tuple(payload, "warnings")
        metrics = self._object_value(payload, "metrics", default={})

        return FinalReconciliationAdvice(
            surface_adjustments=surface_adjustments,
            relations=relations,
            merge_decisions=merge_decisions,
            warnings=warnings,
            metrics=metrics,
        )

    def _registry_entry_payload(self, entry: object) -> JsonValue:
        return {
            "fact_id": getattr(entry, "fact_id"),
            "fact_key": getattr(entry, "fact_key"),
            "claim": getattr(entry, "claim"),
            "question_variants": tuple(getattr(entry, "question_variants")),
            "claim_kind": getattr(getattr(entry, "claim_kind"), "value", None),
            "answer": getattr(entry, "answer"),
            "short_answer": getattr(entry, "short_answer"),
            "answer_scope": getattr(entry, "answer_scope"),
            "retrieval_scope": getattr(entry, "retrieval_scope"),
            "exclusion_scope": getattr(entry, "exclusion_scope"),
            "evidence_quotes": tuple(getattr(entry, "evidence_quotes")),
            "source_refs": tuple(getattr(entry, "source_refs")),
            "source_section_ids": tuple(getattr(entry, "source_section_ids")),
            "source_chunk_indexes": tuple(getattr(entry, "source_chunk_indexes")),
            "parent_fact_ids": tuple(getattr(entry, "parent_fact_ids")),
            "child_fact_ids": tuple(getattr(entry, "child_fact_ids")),
            "duplicate_fact_ids": tuple(getattr(entry, "duplicate_fact_ids")),
            "overlap_fact_ids": tuple(getattr(entry, "overlap_fact_ids")),
            "role_label_metadata": getattr(entry, "role_label_metadata"),
            "status": getattr(getattr(entry, "status"), "value", None),
        }

    def _object_tuple(
        self,
        payload: dict[str, object],
        key: str,
    ) -> tuple[JsonValue, ...]:
        if key not in payload or payload[key] is None:
            return ()

        raw_value = payload[key]
        if not isinstance(raw_value, list):
            raise DomainInvariantError(f"{key} must be a list")

        items: list[JsonValue] = []
        for item in raw_value:
            if not isinstance(item, dict):
                raise DomainInvariantError(f"{key} items must be objects")
            items.append(cast(JsonValue, item))
        return tuple(items)

    def _string_tuple(
        self,
        payload: dict[str, object],
        key: str,
    ) -> tuple[str, ...]:
        if key not in payload or payload[key] is None:
            return ()

        raw_value = payload[key]
        if not isinstance(raw_value, list):
            raise DomainInvariantError(f"{key} must be a list")

        values: list[str] = []
        for item in raw_value:
            if not isinstance(item, str):
                raise DomainInvariantError(f"{key} items must be strings")
            stripped = item.strip()
            if stripped:
                values.append(stripped)
        return tuple(values)

    def _object_value(
        self,
        payload: dict[str, object],
        key: str,
        *,
        default: JsonValue,
    ) -> JsonValue:
        raw_value = payload.get(key, default)
        if not isinstance(raw_value, dict):
            raise DomainInvariantError(f"{key} must be an object")
        return cast(JsonValue, raw_value)

    def _json_dumps(self, value: JsonValue) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError as exc:
            raise DomainInvariantError("value is not JSON serializable") from exc


__all__ = [
    "FaqWorkbenchFinalReconciliationGenerator",
    "FaqWorkbenchFinalReconciliationGeneratorConfig",
    "FaqWorkbenchFinalReconciliationInvocationError",
]
