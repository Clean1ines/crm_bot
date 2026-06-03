from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

from src.application.ports.faq_workbench_registry_merge_generator import (
    FaqWorkbenchRegistryMergeGenerationCommand,
    FaqWorkbenchRegistryMergeGenerationError,
    FaqWorkbenchRegistryMergeGenerationResult,
    FaqWorkbenchRegistryMergeGeneratorPort,
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


class FaqWorkbenchRegistryMergeInvocationError(
    FaqWorkbenchRegistryMergeGenerationError
):
    """Infrastructure alias for Prompt C invocation failures."""


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class FaqWorkbenchRegistryMergeGeneratorConfig:
    prompt_path: Path
    operation_name: str = "faq_fact_registry_canonicalization"
    route_purpose: str = "workbench_fact_registry_canonicalization"


@dataclass(frozen=True, slots=True)
class FaqWorkbenchRegistryMergeGenerator(FaqWorkbenchRegistryMergeGeneratorPort):
    llm_invocation: LlmJsonInvocationPort
    config: FaqWorkbenchRegistryMergeGeneratorConfig
    id_factory: IdFactory
    time_provider: TimeProvider = SystemTimeProvider()

    async def generate_registry_updates(
        self,
        command: FaqWorkbenchRegistryMergeGenerationCommand,
    ) -> FaqWorkbenchRegistryMergeGenerationResult:
        """Run Prompt C over one canonicalization unit."""

        prompt = self.build_prompt(command)
        result = await self.llm_invocation.invoke_json(
            LlmJsonInvocationRequest(
                operation_name=self.config.operation_name,
                prompt=prompt,
                route_purpose=self.config.route_purpose,
                idempotency_key=(
                    f"{command.registry.document_id}:"
                    f"{command.canonicalization_unit.unit_id}:"
                    f"{command.node_run_id}:fact-registry"
                ),
            )
        )

        if result.status is not LlmInvocationStatus.SUCCESS:
            raise FaqWorkbenchRegistryMergeInvocationError(result)

        if result.parsed_json is None:
            raise DomainInvariantError("Prompt C returned empty JSON")

        fact_registry, registry_update_summary = self.parse_fact_registry_payload(
            result.parsed_json
        )

        warnings = self._warnings_from_payload(result.parsed_json)
        metrics = self._metrics_from_payload(result.parsed_json)
        parsed_payload: JsonValue = {
            "fact_registry": fact_registry,
            "registry_update_summary": registry_update_summary,
            "warnings": list(warnings),
            "metrics": metrics,
        }
        raw_payload: JsonValue = {
            "operation_name": self.config.operation_name,
            "prompt_version": command.prompt_version,
            "canonicalization_unit_id": command.canonicalization_unit.unit_id,
            "raw_text": result.raw_text,
            "parsed_json": result.parsed_json,
        }

        return FaqWorkbenchRegistryMergeGenerationResult(
            fact_registry=fact_registry,
            registry_update_summary=registry_update_summary,
            invocation=result,
            raw_output_artifact_payload=raw_payload,
            parsed_output_artifact_payload=parsed_payload,
            warnings=warnings,
            metrics=metrics,
        )

    def build_prompt(
        self,
        command: FaqWorkbenchRegistryMergeGenerationCommand,
    ) -> str:
        prompt_template = self._load_prompt_template()
        input_payload: JsonValue = {
            "canonicalization_unit": command.canonicalization_unit.to_prompt_payload(),
            "registry_snapshot_payload": command.registry_snapshot_payload,
            "relevant_registry_state": command.relevant_registry_state,
            "canonical_facts": [
                self._json_safe(fact)
                for fact in command.canonical_facts
            ],
        }

        return "\n\n".join(
            (
                prompt_template.strip(),
                "INPUT JSON:",
                json.dumps(
                    input_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                ),
            )
        )

    def parse_fact_registry_payload(
        self,
        payload: JsonValue,
    ) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
        if not isinstance(payload, dict):
            raise DomainInvariantError("Prompt C payload must be a JSON object")

        allowed_keys = {
            "fact_registry",
            "registry_update_summary",
            "warnings",
            "metrics",
        }
        unknown_keys = set(payload) - allowed_keys
        if unknown_keys:
            raise DomainInvariantError(
                "Prompt C payload contains unsupported keys: "
                + ", ".join(sorted(unknown_keys))
            )

        fact_registry = payload.get("fact_registry")
        if not isinstance(fact_registry, dict):
            raise DomainInvariantError("Prompt C payload must contain fact_registry object")

        registry_update_summary = payload.get("registry_update_summary")
        if not isinstance(registry_update_summary, dict):
            raise DomainInvariantError(
                "Prompt C payload must contain registry_update_summary object"
            )

        self._validate_fact_registry(fact_registry)
        self._validate_registry_update_summary(registry_update_summary)

        return (
            cast(dict[str, JsonValue], fact_registry),
            cast(dict[str, JsonValue], registry_update_summary),
        )

    def _validate_fact_registry(self, fact_registry: dict[str, JsonValue]) -> None:
        version = fact_registry.get("version")
        if not isinstance(version, int) or version < 1:
            raise DomainInvariantError("fact_registry.version must be a positive integer")

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
            fact_id = self._required_str(raw_fact, "fact_id", f"canonical fact #{index}")
            if fact_id in fact_ids:
                raise DomainInvariantError(f"duplicate canonical fact id: {fact_id}")
            fact_ids.add(fact_id)

            self._required_str(raw_fact, "claim", f"canonical fact #{index}")
            self._required_str(raw_fact, "claim_kind", f"canonical fact #{index}")
            self._required_str(raw_fact, "granularity", f"canonical fact #{index}")
            self._required_str(raw_fact, "status", f"canonical fact #{index}")
            self._required_list(raw_fact, "triples", f"canonical fact #{index}")
            self._required_list(raw_fact, "mentions", f"canonical fact #{index}")
            self._required_list(raw_fact, "question_variants", f"canonical fact #{index}")
            self._required_list(raw_fact, "derived_fact_notes", f"canonical fact #{index}")

        for index, raw_relation in enumerate(fact_relations):
            if not isinstance(raw_relation, dict):
                raise DomainInvariantError(f"fact relation #{index} must be an object")
            source_fact_id = self._required_str(
                raw_relation,
                "source_fact_id",
                f"fact relation #{index}",
            )
            target_fact_id = self._required_str(
                raw_relation,
                "target_fact_id",
                f"fact relation #{index}",
            )
            self._required_str(raw_relation, "relation", f"fact relation #{index}")
            self._required_str(raw_relation, "reason", f"fact relation #{index}")

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
            value = registry_update_summary.get(key)
            if not isinstance(value, int) or value < 0:
                raise DomainInvariantError(
                    f"registry_update_summary.{key} must be a non-negative integer"
                )

        notes = registry_update_summary.get("notes")
        if not isinstance(notes, list):
            raise DomainInvariantError("registry_update_summary.notes must be a list")

    def _warnings_from_payload(self, payload: JsonValue) -> tuple[str, ...]:
        if not isinstance(payload, dict):
            return ()
        raw_warnings = payload.get("warnings", ())
        if not isinstance(raw_warnings, list):
            return ()
        return tuple(item for item in raw_warnings if isinstance(item, str) and item.strip())

    def _metrics_from_payload(self, payload: JsonValue) -> dict[str, JsonValue]:
        if not isinstance(payload, dict):
            return {}
        raw_metrics = payload.get("metrics", {})
        if not isinstance(raw_metrics, dict):
            return {}
        return cast(dict[str, JsonValue], raw_metrics)

    def _json_safe(self, value: object) -> JsonValue:
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        if hasattr(value, "value") and isinstance(value.value, str):
            return value.value
        if isinstance(value, tuple | list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if hasattr(value, "__dataclass_fields__"):
            return {
                name: self._json_safe(getattr(value, name))
                for name in value.__dataclass_fields__
            }
        return str(value)

    def _required_str(
        self,
        payload: dict[str, JsonValue],
        key: str,
        context: str,
    ) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise DomainInvariantError(f"{context}.{key} is required")
        return value.strip()

    def _required_list(
        self,
        payload: dict[str, JsonValue],
        key: str,
        context: str,
    ) -> list[JsonValue]:
        value = payload.get(key)
        if not isinstance(value, list):
            raise DomainInvariantError(f"{context}.{key} must be a list")
        return value

    def _load_prompt_template(self) -> str:
        return self.config.prompt_path.read_text(encoding="utf-8")


__all__ = [
    "FaqWorkbenchRegistryMergeGenerator",
    "FaqWorkbenchRegistryMergeGeneratorConfig",
    "FaqWorkbenchRegistryMergeInvocationError",
]
