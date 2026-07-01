
Workbench Cleanup Plan and Technical Debt

Status: active cleanup plan.

Goal

Stop fixing symptoms inside a huge document card and instead canonize the current working pipeline.

Current working pipeline:

upload
→ source ingestion
→ workflow command drain
→ frontend projection events
→ reducer
→ document card live UI
Cleanup order
Phase 1 — document current state

Create these docs:

upload/process overview;
backend module map;
frontend projection/card map;
Claim Builder contract;
pause/resume contract;
cleanup plan.
Phase 2 — canonical Claim Builder frontend module

Extract from KnowledgeDocumentCard.tsx:

frontend/src/pages/knowledge/components/workflow-card/claim-builder/
  claimBuilderTypes.ts
  claimBuilderSelectors.ts
  claimBuilderLabels.ts
  ClaimBuilderPanel.tsx
  ClaimBuilderSectionRow.tsx
  ClaimBuilderAttemptRow.tsx
  ClaimBuilderDraftClaimArtifact.tsx

Rules:

KnowledgeDocumentCard becomes shell/coordinator.
Claim Builder module reads live projection only.
Attempts are mandatory.
Artifacts are linked to attempts by dispatch_attempt_id.
UI renders claim/questions/exclusion_scope.
No answerDraftsResponse.
No fragments/drafts/answers fallback.
Phase 3 — frontend API type cleanup

Add explicit type:

WorkbenchDraftClaimArtifactLiveState

Add to:

WorkbenchSectionQueueItemLiveState.draft_claims

Remove casts that hide the missing contract.

Phase 4 — remove old frontend answer draft path

Search/remove:

KnowledgeAnswerDraftsResponse
answerDraftsResponse
collectDraftClaims(answerDraftsResponse)
draftPreviewDocumentIds
knowledgeApi.fragments
old draft claim preview fetches used only by card.
Phase 5 — backend Claim Builder cleanup

Pin and clean:

Claim Builder output validation contract.
draft claim persistence candidate contract.
frontend projector contract.
read model contract.
tests for event payload and frontend projection coverage.
Phase 6 — split remaining card modules

After Claim Builder is canonical:

source ingestion panel;
embeddings/clustering panel;
compaction panel;
curation panel;
publication panel;
header/actions shell.
Technical debt register
TD-001: KnowledgeDocumentCard.tsx is still too large

Impact:

every patch risks breaking unrelated phases;
legacy fallback fields stay hidden in helpers;
UI structure is hard to reason about.

Resolution:
extract phase modules one by one, starting with Claim Builder.

TD-002: src/interfaces/http/knowledge.py is too broad

Impact:

upload, source reads, frontend events, draft claims, compaction, curation, publication live in one router file;
hard to see current API boundary.

Resolution:
split by route groups after current frontend cleanup is stable.

TD-003: old Workbench card fallback still exposes retired vocabulary

Impact:

fallback card view includes registry/surfaces/runtime/cancel action fields that can confuse frontend cleanup;
risks resurrecting old workflow concepts.

Resolution:
mark fallback as transitional; remove or replace with current Workbench live-state card model.

TD-004: section_lanes is transport terminology leaking into frontend

Impact:

UI code starts thinking in lanes instead of section rows.

Resolution:
keep transport shape but map to sectionRows in selectors.

TD-005: embedded frontend events and live-state read model need convergence tests

Impact:

optimistic upload, live-state fetch, and SSE replay can drift.

Resolution:
test:

initial live-state creation;
replay events;
SSE event application;
convergence after backend list query refresh.
TD-006: Claim Builder artifacts are attached to section items

Impact:

UI must map artifacts to attempts by dispatch_attempt_id.

Resolution:
short term: canonical selector does the mapping.
long term: normalized live-state or attempt-nested artifacts.

TD-007: pause/resume was inferred in frontend

Impact:

frontend may show wrong button when backend already exposes exact action contract.

Resolution:
primary button derives only from workflow.actions.

TD-008: evidence_block is not real evidence text yet

Impact:

UI may mislabel source_unit_ref as evidence.

Resolution:
display evidence only when backend stores real evidence excerpts, or label current value as source unit reference internally only.

Required verification commands

Frontend:

npm --prefix frontend run type-check

Backend focused tests:

pytest tests/contexts/knowledge_workbench/observability/application/projectors/test_claim_builder_section_outcome_frontend_workflow_event_projector.py
pytest tests/contexts/knowledge_workbench/application/sagas/test_handle_execute_claim_builder_section_command.py
pytest tests/api/test_knowledge.py

Architecture tests:

pytest tests/architecture/test_knowledge_extraction_frontend_workflow_projection_coverage.py
Next immediate implementation task

Before another UI cleanup patch:

grep -R "KnowledgeAnswerDraftsResponse\|answerDraftsResponse\|collectDraftClaims\|collectLiveDraftClaims\|fragments\|drafts\|answers\|section_lanes\|draft_claims" -n \
  frontend/src/pages/knowledge \
  frontend/src/shared/api/modules/knowledge.ts

Then extract canonical Claim Builder module.
