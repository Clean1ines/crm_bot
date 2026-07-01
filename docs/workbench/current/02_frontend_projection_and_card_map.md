
Frontend Projection and Document Card Map

Status: current frontend map.

Frontend page

Main page:

frontend/src/pages/knowledge/KnowledgePage.tsx

Current responsibilities:

fetch document list;
manage optimistic upload documents;
seed initial workflow live state;
subscribe/list frontend workflow events;
reduce frontend workflow projection events;
pass live state into KnowledgeDocumentCard;
manage card actions;
handle upload drag/drop/file input.

Recent upload-related commit:

64d7412b Restore optimistic knowledge upload projection
Optimistic upload

File:

frontend/src/pages/knowledge/optimisticUpload.ts

Purpose:

compute stable optimistic document id;
compute optimistic workflow run id;
create optimistic Workbench document/card object;
let UI show card immediately after upload begins.

Important rule:
Optimistic upload must not invent future processing results. It only creates initial processing shell and initial workflow live-state.

Frontend reducer

Current live projection reducer:

frontend/src/pages/knowledge/shadow/workflowFrontendProjectionReducer.ts

Important:
The directory name shadow does not mean this is dead legacy. This reducer is current live UI infrastructure.

Current responsibilities:

create initial workflow live-state response;
apply frontend workflow event envelopes;
maintain workflow stages;
maintain section queue items;
maintain LLM attempts;
attach draft claims to section items;
update clusters/compaction/curation state;
recompute counters/usage.

Claim Builder draft claim path:

event.payload.draft_claims
→ draftClaimsFromPayload(payload)
→ attachDraftClaimsToSectionItem(response, sourceUnitRef, draftClaims)
→ workflow.section_lanes[].items[].draft_claims

Attempts path:

event.payload.dispatch_attempt_id
→ upsertAttempt(...)
→ workflow.llm_attempts[]
Document card

Main component:

frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx

Current status:

Works functionally enough to show upload/workflow progress.
Still too large.
Still mixes canonical live projection with legacy fallback concepts.
Claim Builder section should be extracted first.
Existing extracted files
frontend/src/pages/knowledge/components/workflow-card/workflowCardLabels.ts

Currently extracted label/tone helpers live here.

Required canonical frontend structure

Target structure:

frontend/src/pages/knowledge/components/workflow-card/
  workflowCardLabels.ts

frontend/src/pages/knowledge/components/workflow-card/claim-builder/
  claimBuilderTypes.ts
  claimBuilderSelectors.ts
  claimBuilderLabels.ts
  ClaimBuilderPanel.tsx
  ClaimBuilderSectionRow.tsx
  ClaimBuilderAttemptRow.tsx
  ClaimBuilderDraftClaimArtifact.tsx
Claim Builder frontend model

Transport state:

workflow.section_lanes[].items[]
workflow.llm_attempts[]

Canonical UI view model:

type ClaimBuilderSectionRowView = {
  sectionId: string;
  sectionIndex: number;
  sectionTextPreview: string | null;
  status: string;
  attemptCount: number;
  attempts: ClaimBuilderAttemptView[];
};

type ClaimBuilderAttemptView = {
  attemptId: string;
  sectionId: string;
  status: string;
  provider: string | null;
  modelName: string | null;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  errorKind: string | null;
  errorMessageUser: string | null;
  artifacts: ClaimBuilderDraftClaimArtifactView[];
};

type ClaimBuilderDraftClaimArtifactView = {
  observationRef: string;
  dispatchAttemptId: string;
  workItemId: string;
  sourceUnitRef: string;
  claimIndex: number;
  claim: string;
  granularity: string;
  possibleQuestions: string[];
  exclusionScope: string;
  evidenceBlock: string;
  validationDecision: string | null;
};
Claim Builder UI structure
ClaimBuilderPanel
  ClaimBuilderSectionRow[]
    section status
    source unit preview
    attempts[]
      attempt status
      minimal model/tokens/error
      artifacts[]
        Факт: claim
        Вопросы: possible_questions
        Не является темой факта: exclusion_scope

Attempts are mandatory.
Successful attempt artifacts are mandatory.

Pause/resume button contract

Frontend must not infer pause/resume by permutations of timer/status strings.

Source of truth:

workflow.actions

Rendering rule:

enabled+visible resume_processing exists → show "Продолжить"
else enabled+visible pause_processing exists → show "Пауза"
else show no primary processing control

Current related commit:

11227042 Restore stable processing control visibility

Needed follow-up:
make KnowledgeDocumentCard use only backend action contract for selecting the primary processing control.

Frontend technical debt
TD-FE-001: Claim Builder is not extracted as module

KnowledgeDocumentCard.tsx should be reduced to shell/coordinator. Claim Builder should be its own module.

TD-FE-002: old answer draft / fragment fallback must be removed

Do not use:

answerDraftsResponse;
KnowledgeAnswerDraftsResponse;
collectDraftClaims(answerDraftsResponse);
generic containers fragments, drafts, answers, items;
generic fields title, question, canonical_question, answer, content, text, body.

Current canonical source for Claim Builder UI is live projection.

TD-FE-003: section_lanes should not leak into UI model

Transport shape can stay section_lanes.
Frontend module should expose sectionRows.

TD-FE-004: API type lacks explicit draft_claims on section queue item

Add:

export type WorkbenchDraftClaimArtifactLiveState = {
  observation_ref: string;
  workflow_run_id?: string;
  source_document_ref?: string;
  source_unit_ref: string;
  section_id?: string;
  work_item_id: string;
  dispatch_attempt_id: string;
  claim_index: number;
  provider?: string;
  model_ref?: string;
  claim: string;
  granularity: string;
  possible_questions: string[];
  exclusion_scope: string;
  evidence_block: string;
  validation_decision?: string;
};

and:

draft_claims?: WorkbenchDraftClaimArtifactLiveState[];

to WorkbenchSectionQueueItemLiveState.

TD-FE-005: reducers need contract tests around Claim Builder artifacts

Test should assert:

workflow_claim_builder_section_extracted event with draft_claims
→ reducer attaches draft_claims to matching section item
→ attempts remain linked by dispatch_attempt_id

