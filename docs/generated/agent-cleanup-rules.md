# Agent Cleanup Rules

## No compatibility by default

Compatibility with legacy Workbench / registry / old document processing is not a goal.

## No legacy bridges

Do not preserve legacy state by synchronizing it with current runtime state.

If legacy state conflicts with current runtime state, remove dependency on legacy state.
Do not add bridges, mappers, fallback reads, or compatibility projections unless explicitly requested as a temporary deletion migration.

## Do not upgrade legacy into architecture

If a table/field exists only because old code needs it, classify it as legacy.
Do not make it authoritative by adding new reads.

## Current authority must have causal power

A table/field is current authority only if current executable code reads it to decide future work.

## Pause rule

Do not implement pause by checking knowledge_extraction_workflow_runs.status.
Pause must be runtime-native.

## Post-pause rule

Do not discard already-started LLM results.
Do block new dispatch/lease/execute waves while paused.

## Patch rule

Before patching any pause/status/UI hydration behavior, complete source-of-truth audit.

## Proven current vocabulary

Use only vocabulary proven by current executable code, DB tables, runtime events, or frontend/API contracts.

Current proven terms:
- SourceDocument / source_document_ref
- SourceUnit / source_unit_ref
- workflow_run_id
- workflow command
- work_item_id
- attempt_id
- DraftClaimObservation / observation_ref
- DraftClaimEmbedding
- DraftClaimCompactionGroup / group_ref
- DraftClaimCompactionBatch / batch_ref
- DraftClaimCompactionNode / node_ref
- DraftClaimCurationWorkspace / workspace_ref
- DraftClaimCurationItem / item_ref
- RuntimePublication / publication_id
- RuntimeRetrievalEntry / runtime_entry_id
- FrontendWorkflowEvent
- RuntimeProgressSnapshot
- RuntimeTimelineEntry

Rejected or unproven terms:
- CompilerRun: rejected unless proven by current executable code
- AnswerCandidate: likely legacy/unproven
- CandidateCluster: suspect; use DraftClaimCompactionGroup or claim cluster if proven by UI contract
- CanonicalKnowledgeEntry: rejected; too close to legacy canonical facts/registry semantics
- KnowledgeEnrichment: likely legacy/unproven
- RetrievalSurface: concept-only unless proven by current runtime retrieval code
- EvalCase/RagEval: partially valid but transitional; requires separate RAG Eval audit
- KnowledgeEditAction: unproven unless tied to current curation item actions

Avoid upgrading these legacy names into new code:
- `processing_run_id`
- `node_run_id`
- `fact_registry`
- `canonical_facts`
- `knowledge_base`
- `knowledge_documents`
- `execution_queue`

## Source-of-truth test

Before using a table as authority, answer:
- Is it read to append the next runtime command?
- Is it read before command dispatch?
- Is it read before work-item lease?
- Is it read before LLM attempt execution?
- Is it read before retry/defer/block/cancel?
- Is it read to decide paused/running/completed future behavior?

If all answers are no, it is projection, domain data, compatibility, or delete candidate, not current authority.
