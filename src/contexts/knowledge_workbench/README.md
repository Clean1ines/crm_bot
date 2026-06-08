# Knowledge Workbench Context

## Назначение

`knowledge_workbench` — quality-control panel and lifecycle manager for knowledge engineering.

Этот context владеет смыслом knowledge surfaces и workflow качества знания.

Он не является generic execution runtime.

Он не является LLM runtime.

Он не является artifact store.

Он использует `execution_runtime`, `llm_runtime` и `artifact_runtime`, но не заменяет их.

## Subdomains

Knowledge Workbench contains these subdomains:

- Source Management;
- Knowledge Extraction;
- Surface Consolidation;
- RAG Enrichment;
- Retrieval Evaluation;
- Manual Curation;
- Publication.

## Owns

Canonical concepts:

- `SourceDocument`;
- `SourceUnit`;
- `SourceRef`;
- `ClaimObservation`;
- `DraftSurface`;
- `SurfaceCandidate`;
- `ConsolidatedSurface`;
- `KnowledgeSurface`;
- `RetrievalSurface`;
- `CanonicalIntent`;
- `EvidenceRef`;
- `PossibleQuestion`;
- `ExclusionScope`;
- `EnrichmentProposal`;
- `RetrievalEvalRun`;
- `RetrievalEvalCase`;
- `CurationDecision`;
- `PublicationRun`;
- `PublicationVersion`.

Use cases that belong here:

- `UploadSourceDocument`;
- `NormalizeSourceDocument`;
- `SplitSourceDocument`;
- `ExtractKnowledgeFromSourceUnit`;
- `ConsolidateSurfacesByIntent`;
- `ProposeSurfaceEnrichment`;
- `EvaluateSurfaceEnrichment`;
- `RunRetrievalEvaluation`;
- `EditKnowledgeSurface`;
- `RejectKnowledgeSurface`;
- `ApproveKnowledgeSurface`;
- `PublishKnowledgeSurfaces`;
- `CleanupIntermediateArtifacts`.

## Does not own

This context does not own:

- generic work item leasing;
- generic LLM provider routing;
- generic quota management;
- generic artifact persistence mechanics;
- Telegram transport;
- final conversation orchestration;
- manager handoff workflow.

## Prompt A rule

Prompt A belongs to Knowledge Workbench Extraction as a claim extraction adapter/use case.

Prompt A does not own:

- model fallback;
- provider routing;
- quota;
- lease;
- artifact persistence;
- stage transition.

## Prompt C rule

Prompt C belongs to Surface Consolidation.

Target meaning:

- intent-centered claim/surface consolidation;
- deduplication by user intent;
- enrichment of related observations;
- conflict/review flagging;
- one self-contained consolidated surface per intent when possible.

Old names such as `RegistryMerge`, `CanonicalRegistryMerge`, and `QuestionRegistry` must be treated as legacy naming unless explicitly mapped.

## Legacy / adapter warnings

`FAQ` is legacy product naming.

Target domain is Knowledge Workbench.

`RegistryMerge` is old naming. Target meaning is `SurfaceConsolidation` / `IntentConsolidation`.

`SectionBatchQueueItem` must not be used as canonical Workbench stage model.

## Placement rules

New canonical Workbench code goes here.

Do not add new generic dumping-ground files named:

- `service.py`;
- `services.py`;
- `repository.py`;
- `dto.py`.

Use explicit names such as:

- `extraction/domain/entities/claim_observation.py`;
- `extraction/application/use_cases/extract_knowledge_from_source_unit.py`;
- `extraction/infrastructure/llm/prompt_a_claim_extraction_adapter.py`;
- `surface_consolidation/application/use_cases/consolidate_surfaces_by_intent.py`;
- `publication/application/use_cases/publish_knowledge_surfaces.py`.

Subdomain folders should be introduced when the first canonical implementation for that subdomain appears.
