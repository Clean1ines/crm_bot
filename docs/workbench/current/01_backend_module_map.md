
Backend Module Map: Upload → Processing

Status: current backend module map.

HTTP boundary

Primary router:

src/interfaces/http/knowledge.py

Current responsibilities:

project access checks;
upload endpoint;
source unit read endpoint;
frontend workflow event list/stream endpoints;
draft claim read endpoints;
workflow live-state access;
pause/resume/delete/curation/publication endpoints;
compatibility/fallback card view helpers still present.

Important note:
The file is too broad. It is currently both an API router and a composition/read-model adapter surface. This is technical debt.

Upload composition

Main composition:

src/interfaces/composition/knowledge_extraction_workflow_after_upload.py
src/interfaces/composition/knowledge_extraction_after_upload_composition.py

Current flow:

RunKnowledgeExtractionWorkflowAfterUpload.execute
→ source_ingestion_runner.execute
→ _drain_until_blocked_or_idle
→ _run_one_drain_transaction
→ DrainKnowledgeExtractionWorkflowCommands.execute
→ ProjectFrontendWorkflowEvent
→ CollectingFrontendWorkflowEventRepository
→ PostgresFrontendWorkflowEventRepository
→ publish_frontend_workflow_events

RunKnowledgeExtractionWorkflowAfterUpload wires repositories and policies for:

source management;
workflow runtime UoW;
execution runtime work item scheduling;
claim builder LLM dispatch preparation;
claim builder LLM attempt execution;
capacity observations;
draft claim persistence/read;
embeddings;
compaction;
curation;
frontend event projection.
Source ingestion

Key saga/use case:

src/contexts/knowledge_workbench/application/sagas/run_source_ingestion_first_phase.py

Upload creates a RunSourceIngestionFirstPhaseCommand with:

project_id;
actor;
original_filename;
source_format;
content_bytes;
raw_text;
occurred_at.

Source ingestion persists:

source document;
source units;
workflow run / initial workflow state;
commands needed to start extraction.
Workflow command drain

Main drain use case:

src/contexts/knowledge_workbench/application/sagas/drain_knowledge_extraction_workflow_commands.py

The after-upload runner drains commands immediately after source ingestion, bounded by max_drain_commands.

Current upload endpoint passes:

max_drain_commands=10

This makes upload more than a simple enqueue operation: it starts immediate workflow progress and emits frontend projection events.

Claim Builder command execution

Main file:

src/contexts/knowledge_workbench/application/sagas/handle_execute_claim_builder_section_command.py

Main responsibilities:

execute prepared LLM dispatch attempt;
validate Claim Builder output;
decide next action;
persist validated draft claims;
record capacity observations;
append workflow outcome event;
project frontend workflow event;
append reconcile command;
save progress snapshot;
append timeline entry;
mark command completed.

Current validated claim payload path:

LLM output
→ ClaimBuilderLlmDispatchOutputValidator
→ ClaimBuilderOutputValidationPolicy
→ ValidatedClaimBuilderClaim
→ _draft_claim_candidates
→ PersistValidatedDraftClaimObservationsPort
→ _draft_claims_event_payload
→ WorkflowEvent payload["draft_claims"]
→ frontend projector
Frontend workflow projection backend side

Projector facade:

src/contexts/knowledge_workbench/observability/application/projectors/knowledge_extraction_frontend_workflow_event_projector.py

Claim Builder section outcome projector:

src/contexts/knowledge_workbench/observability/application/projectors/claim_builder_section_outcome_frontend_workflow_event_projector.py

The Claim Builder projector maps canonical workflow events to frontend event patches:

extracted;
retryable failed;
terminal failed.

For successful extraction it passes through draft_claims.

Live-state read model

Composition:

src/interfaces/composition/faq_workbench_workflow_live_state.py

Current responsibilities:

read current document/workflow row;
read section queue rows from execution work items;
read LLM attempts;
read model usage;
read claim clusters;
read counts;
read timeline;
derive timer state from workflow status and pause/resume timeline events;
expose workflow actions;
expose curation availability.

Important current backend contract:

workflow.actions is the source of truth for pause/resume buttons.
workflow.section_lanes is transport/read-model shape for section work items.
workflow.llm_attempts is transport/read-model shape for LLM attempts.
frontend should build UI sectionRows from these transport shapes.
Persistence modules

Relevant persistence modules:

src/contexts/knowledge_workbench/source_management/infrastructure/postgres/postgres_source_management_repository.py

src/contexts/workflow_runtime/infrastructure/postgres/postgres_workflow_runtime_unit_of_work.py

src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_scheduling_repository.py

src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_progress_read_repository.py

src/contexts/knowledge_workbench/extraction/infrastructure/postgres/postgres_validated_draft_claim_observation_persistence.py

src/contexts/knowledge_workbench/extraction/infrastructure/postgres/postgres_draft_claim_observation_read_repository.py

src/contexts/knowledge_workbench/observability/infrastructure/postgres/postgres_frontend_workflow_event_repository.py
Backend technical debt
TD-BE-001: knowledge.py is too broad

src/interfaces/http/knowledge.py currently owns many unrelated API concerns:

upload;
source unit reads;
frontend event stream;
draft claim reads;
compaction reads;
curation;
publication;
legacy gone endpoints;
fallback card view.

Desired split:

knowledge_upload_routes.py
knowledge_workflow_event_routes.py
knowledge_source_unit_routes.py
knowledge_draft_claim_routes.py
knowledge_curation_routes.py
knowledge_publication_routes.py
TD-BE-002: old card fallback still exposes legacy-ish registry/surface fields

_workbench_document_card_view_fallback still returns fields like:

registry;
surfaces;
runtime;
cancel_processing visible/running fallback.

This is risky because the current canonical UI should be driven by live workflow state and frontend projection, not old card metadata.

TD-BE-003: section_lanes is backend/read-model transport terminology

It is okay as read-model transport shape, but UI module should not use lane terminology as user-facing model. Frontend selector should map:
workflow.section_lanes[].items[] → ClaimBuilderSectionRowView[].

TD-BE-004: frontend events and live-state both describe similar state

There are two read paths:

persisted/streamed frontend workflow events;
backend live-state query.

This is valid, but docs/tests must pin down convergence rules:

live-state seeds current state;
event stream applies increments;
reducer produces current projection;
card renders projection.
TD-BE-005: targeted read fields may be transitional

Claim Builder projector emits:

draft_claims_scope
targeted_read_kind

Current frontend path should use embedded payload.draft_claims. Keep targeted read fields until confirmed unused, then remove in separate backend cleanup.
