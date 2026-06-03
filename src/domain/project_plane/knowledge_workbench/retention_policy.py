from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkbenchRetentionState(StrEnum):
    ACTIVE_PROCESSING = "active_processing"
    READY_FOR_PUBLICATION = "ready_for_publication"
    PUBLISHED_RETAINED = "published_retained"
    TRANSIENT_PURGED = "transient_purged"
    DELETED = "deleted"


class WorkbenchRetentionCategory(StrEnum):
    TRANSIENT_UNTIL_PUBLICATION = "transient_until_publication"
    RETAINED_AFTER_PUBLICATION = "retained_after_publication"


class WorkbenchProcessingEntity(StrEnum):
    KNOWLEDGE_DOCUMENT_METADATA = "knowledge_document_metadata"

    DOCUMENT_SECTION = "document_section"
    KNOWLEDGE_PROCESSING_RUN = "knowledge_processing_run"
    PROCESSING_NODE_RUN = "processing_node_run"
    PROCESSING_NODE_ARTIFACT = "processing_node_artifact"
    MODEL_INVOCATION_DETAIL = "model_invocation_detail"
    PROCESSING_ERROR_REPORT = "processing_error_report"

    SECTION_FINDING = "section_finding"
    DETERMINISTIC_DEDUP_RESULT = "deterministic_dedup_result"
    REGISTRY_UPDATE_PROPOSAL = "registry_update_proposal"
    REGISTRY_UPDATE_APPLICATION = "registry_update_application"
    INTERMEDIATE_REGISTRY_SNAPSHOT = "intermediate_registry_snapshot"

    SURFACE_CANDIDATE = "surface_candidate"
    DEDUPLICATED_SURFACE_CANDIDATE = "deduplicated_surface_candidate"
    FINAL_SURFACE_DRAFT = "final_surface_draft"
    FINAL_RECONCILIATION_RUN = "final_reconciliation_run"
    FINAL_RECONCILIATION_SUGGESTION = "final_reconciliation_suggestion"
    SURFACE_MATERIALIZATION_RESULT = "surface_materialization_result"

    FINAL_FACT_REGISTRY = "final_fact_registry"
    FINAL_REGISTRY_SNAPSHOT = "final_registry_snapshot"
    FINAL_REGISTRY_ENTRY = "final_registry_entry"
    KNOWLEDGE_SURFACE = "knowledge_surface"
    SURFACE_RELATION = "surface_relation"

    SURFACE_CURATION_SESSION = "surface_curation_session"
    SURFACE_CURATION_CHANGE = "surface_curation_change"
    RUNTIME_PUBLICATION = "runtime_publication"
    RUNTIME_RETRIEVAL_ENTRY = "runtime_retrieval_entry"

    MODEL_USAGE_AGGREGATE = "model_usage_aggregate"
    RAG_EVAL_ARTIFACT = "rag_eval_artifact"
    PROJECT_SURFACE_RECONCILIATION_ARTIFACT = "project_surface_reconciliation_artifact"


@dataclass(frozen=True, slots=True)
class WorkbenchRetentionRule:
    entity: WorkbenchProcessingEntity
    category: WorkbenchRetentionCategory
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("retention rule reason must not be blank")


@dataclass(frozen=True, slots=True)
class WorkbenchPublishRetentionPlan:
    processing_method: str
    state_before_publication: WorkbenchRetentionState
    state_after_publication: WorkbenchRetentionState
    rules: tuple[WorkbenchRetentionRule, ...]
    purge_transient_after_publication: bool
    resume_allowed_after_transient_purge: bool
    requires_final_registry: bool
    requires_final_surfaces: bool
    requires_runtime_publication: bool

    def __post_init__(self) -> None:
        if self.processing_method != "faq_section_registry_v1":
            raise ValueError("unexpected Workbench processing method")
        if (
            self.state_before_publication
            is not WorkbenchRetentionState.READY_FOR_PUBLICATION
        ):
            raise ValueError("publication requires ready_for_publication state")
        if self.state_after_publication is not WorkbenchRetentionState.TRANSIENT_PURGED:
            raise ValueError("publication must end with transient_purged state")
        if not self.purge_transient_after_publication:
            raise ValueError("publication must purge transient processing workspace")
        if self.resume_allowed_after_transient_purge:
            raise ValueError("resume must be forbidden after transient purge")
        if not self.requires_final_registry:
            raise ValueError("publication must require final registry")
        if not self.requires_final_surfaces:
            raise ValueError("publication must require final surfaces")
        if not self.requires_runtime_publication:
            raise ValueError("publication must require runtime publication")
        validate_publish_retention_rules(self.rules)

    @property
    def transient_entities(self) -> tuple[WorkbenchProcessingEntity, ...]:
        return tuple(
            rule.entity
            for rule in self.rules
            if rule.category is WorkbenchRetentionCategory.TRANSIENT_UNTIL_PUBLICATION
        )

    @property
    def retained_entities(self) -> tuple[WorkbenchProcessingEntity, ...]:
        return tuple(
            rule.entity
            for rule in self.rules
            if rule.category is WorkbenchRetentionCategory.RETAINED_AFTER_PUBLICATION
        )

    def rule_for(
        self,
        entity: WorkbenchProcessingEntity,
    ) -> WorkbenchRetentionRule:
        for rule in self.rules:
            if rule.entity is entity:
                return rule
        raise KeyError(entity)

    def is_transient_until_publication(
        self,
        entity: WorkbenchProcessingEntity,
    ) -> bool:
        return (
            self.rule_for(entity).category
            is WorkbenchRetentionCategory.TRANSIENT_UNTIL_PUBLICATION
        )

    def is_retained_after_publication(
        self,
        entity: WorkbenchProcessingEntity,
    ) -> bool:
        return (
            self.rule_for(entity).category
            is WorkbenchRetentionCategory.RETAINED_AFTER_PUBLICATION
        )


def transient_rule(
    entity: WorkbenchProcessingEntity,
    reason: str,
) -> WorkbenchRetentionRule:
    return WorkbenchRetentionRule(
        entity=entity,
        category=WorkbenchRetentionCategory.TRANSIENT_UNTIL_PUBLICATION,
        reason=reason,
    )


def retained_rule(
    entity: WorkbenchProcessingEntity,
    reason: str,
) -> WorkbenchRetentionRule:
    return WorkbenchRetentionRule(
        entity=entity,
        category=WorkbenchRetentionCategory.RETAINED_AFTER_PUBLICATION,
        reason=reason,
    )


FAQ_DOCUMENT_PUBLISH_RETENTION_RULES: tuple[WorkbenchRetentionRule, ...] = (
    retained_rule(
        WorkbenchProcessingEntity.KNOWLEDGE_DOCUMENT_METADATA,
        "document card and publication status remain visible after publication",
    ),
    transient_rule(
        WorkbenchProcessingEntity.DOCUMENT_SECTION,
        "sections are checkpoint workspace; final surfaces embed retained evidence",
    ),
    transient_rule(
        WorkbenchProcessingEntity.KNOWLEDGE_PROCESSING_RUN,
        "run state is resumable workspace and cannot survive transient purge",
    ),
    transient_rule(
        WorkbenchProcessingEntity.PROCESSING_NODE_RUN,
        "node runs are execution checkpoints until successful publication",
    ),
    transient_rule(
        WorkbenchProcessingEntity.PROCESSING_NODE_ARTIFACT,
        "raw inputs, raw LLM outputs and parsed node outputs are transient",
    ),
    transient_rule(
        WorkbenchProcessingEntity.MODEL_INVOCATION_DETAIL,
        "per-attempt provider/key/model details are execution workspace",
    ),
    transient_rule(
        WorkbenchProcessingEntity.PROCESSING_ERROR_REPORT,
        "successful publication replaces processing errors with final state",
    ),
    transient_rule(
        WorkbenchProcessingEntity.SECTION_FINDING,
        "findings are proposals and must not remain as runtime knowledge",
    ),
    transient_rule(
        WorkbenchProcessingEntity.DETERMINISTIC_DEDUP_RESULT,
        "dedup output is an intermediate code-node artifact",
    ),
    transient_rule(
        WorkbenchProcessingEntity.REGISTRY_UPDATE_PROPOSAL,
        "LLM advisory proposals never remain as registry truth",
    ),
    transient_rule(
        WorkbenchProcessingEntity.REGISTRY_UPDATE_APPLICATION,
        "applications are replay/checkpoint data; final registry is retained",
    ),
    transient_rule(
        WorkbenchProcessingEntity.INTERMEDIATE_REGISTRY_SNAPSHOT,
        "intermediate snapshots are resume checkpoints only",
    ),
    transient_rule(
        WorkbenchProcessingEntity.SURFACE_CANDIDATE,
        "surface candidates are pre-materialization workspace",
    ),
    transient_rule(
        WorkbenchProcessingEntity.DEDUPLICATED_SURFACE_CANDIDATE,
        "deduplicated candidates are pre-materialization workspace",
    ),
    transient_rule(
        WorkbenchProcessingEntity.FINAL_SURFACE_DRAFT,
        "final drafts are replaced by published fact-registry runtime retrieval entries",
    ),
    transient_rule(
        WorkbenchProcessingEntity.FINAL_RECONCILIATION_RUN,
        "bounded reconciliation run is an execution artifact",
    ),
    transient_rule(
        WorkbenchProcessingEntity.FINAL_RECONCILIATION_SUGGESTION,
        "suggestions are applied or rejected before final materialization",
    ),
    transient_rule(
        WorkbenchProcessingEntity.SURFACE_MATERIALIZATION_RESULT,
        "materialization result is replaced by final surfaces and registry",
    ),
    retained_rule(
        WorkbenchProcessingEntity.FINAL_FACT_REGISTRY,
        "final registry remains as the source model for published surfaces",
    ),
    retained_rule(
        WorkbenchProcessingEntity.FINAL_REGISTRY_SNAPSHOT,
        "one final published snapshot remains for audit and reprocess seed",
    ),
    retained_rule(
        WorkbenchProcessingEntity.FINAL_REGISTRY_ENTRY,
        "final entries explain which question model produced surfaces",
    ),
    retained_rule(
        WorkbenchProcessingEntity.KNOWLEDGE_SURFACE,
        "final surfaces are the curated publication unit",
    ),
    retained_rule(
        WorkbenchProcessingEntity.SURFACE_RELATION,
        "accepted final relations are part of published knowledge structure",
    ),
    retained_rule(
        WorkbenchProcessingEntity.SURFACE_CURATION_SESSION,
        "curation state explains what the user published or discarded",
    ),
    retained_rule(
        WorkbenchProcessingEntity.SURFACE_CURATION_CHANGE,
        "published curation changes remain as user-facing edit history",
    ),
    retained_rule(
        WorkbenchProcessingEntity.RUNTIME_PUBLICATION,
        "publication record is the runtime cutover boundary",
    ),
    retained_rule(
        WorkbenchProcessingEntity.RUNTIME_RETRIEVAL_ENTRY,
        "runtime retrieval uses only published entries",
    ),
    retained_rule(
        WorkbenchProcessingEntity.MODEL_USAGE_AGGREGATE,
        "token usage aggregates remain for billing, limits and observability",
    ),
    retained_rule(
        WorkbenchProcessingEntity.RAG_EVAL_ARTIFACT,
        "RAG eval is a post-publication quality/enrichment workflow",
    ),
    retained_rule(
        WorkbenchProcessingEntity.PROJECT_SURFACE_RECONCILIATION_ARTIFACT,
        "project reconciliation is a separate cross-document workflow",
    ),
)


def validate_publish_retention_rules(
    rules: tuple[WorkbenchRetentionRule, ...],
) -> None:
    seen: set[WorkbenchProcessingEntity] = set()
    for rule in rules:
        if rule.entity in seen:
            raise ValueError(f"duplicate retention rule for {rule.entity}")
        seen.add(rule.entity)

    missing = set(WorkbenchProcessingEntity) - seen
    if missing:
        missing_names = ", ".join(sorted(item.value for item in missing))
        raise ValueError(f"missing retention rules: {missing_names}")


FAQ_DOCUMENT_PUBLISH_RETENTION_PLAN = WorkbenchPublishRetentionPlan(
    processing_method="faq_section_registry_v1",
    state_before_publication=WorkbenchRetentionState.READY_FOR_PUBLICATION,
    state_after_publication=WorkbenchRetentionState.TRANSIENT_PURGED,
    rules=FAQ_DOCUMENT_PUBLISH_RETENTION_RULES,
    purge_transient_after_publication=True,
    resume_allowed_after_transient_purge=False,
    requires_final_registry=True,
    requires_final_surfaces=True,
    requires_runtime_publication=True,
)


def publish_retention_plan() -> WorkbenchPublishRetentionPlan:
    return FAQ_DOCUMENT_PUBLISH_RETENTION_PLAN


__all__ = [
    "FAQ_DOCUMENT_PUBLISH_RETENTION_PLAN",
    "FAQ_DOCUMENT_PUBLISH_RETENTION_RULES",
    "WorkbenchProcessingEntity",
    "WorkbenchPublishRetentionPlan",
    "WorkbenchRetentionCategory",
    "WorkbenchRetentionRule",
    "WorkbenchRetentionState",
    "publish_retention_plan",
    "retained_rule",
    "transient_rule",
    "validate_publish_retention_rules",
]
