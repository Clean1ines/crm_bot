
Claim Builder Contract

Status: current contract snapshot.

Output contract from LLM

Validation policy file:

src/contexts/knowledge_workbench/extraction/application/policies/claim_builder_output_validation_policy.py

The validated Claim Builder output item has exactly these fields:

claim
granularity
possible_questions
exclusion_scope

ClaimBuilderOutputValidationPolicy rejects claim items whose key set differs from that exact set.

Validated domain model:

ValidatedClaimBuilderClaim

Fields:

claim: str
granularity: DraftClaimGranularity
possible_questions: tuple[str, ...]
exclusion_scope: str
evidence_block: str

Current implementation sets evidence_block to source_unit_ref.

Persistence candidate contract

Created in:

src/contexts/knowledge_workbench/application/sagas/handle_execute_claim_builder_section_command.py::_draft_claim_candidates

Persisted candidate fields:

workflow_run_id
stage_run_id
prompt_id
prompt_version
source_document_ref
source_unit_ref
source_unit_ordinal
work_item_id
dispatch_attempt_id
claim_index
provider
model_ref
claim
granularity
possible_questions
exclusion_scope
evidence_block
validation_decision
Workflow event payload contract

Created in:

src/contexts/knowledge_workbench/application/sagas/handle_execute_claim_builder_section_command.py::_draft_claims_event_payload

Each frontend-facing draft claim event payload item:

{
  "observation_ref": "{dispatch_attempt_id}:claim:{index}",
  "workflow_run_id": "...",
  "source_document_ref": "...",
  "source_unit_ref": "...",
  "section_id": "...",
  "work_item_id": "...",
  "dispatch_attempt_id": "...",
  "claim_index": 0,
  "provider": "...",
  "model_ref": "...",
  "claim": "...",
  "granularity": "...",
  "possible_questions": ["..."],
  "exclusion_scope": "...",
  "evidence_block": "...",
  "validation_decision": "..."
}
Frontend projector contract

Projector:

src/contexts/knowledge_workbench/observability/application/projectors/claim_builder_section_outcome_frontend_workflow_event_projector.py

Successful section extraction patch includes:

workflow_run_id
source_document_ref
source_unit_ref
dispatch_attempt_id
work_item_id
source_unit_claim_builder_status = completed
work_item_state = completed
dispatch_attempt_state = completed
persisted_draft_claim_count
draft_claims_available = true
draft_claims_count
draft_claims
draft_claims_scope
targeted_read_kind
provider/account_ref/model_ref
actual_prompt_tokens
actual_completion_tokens
actual_total_tokens
validation metadata
Frontend reducer contract

Reducer:

frontend/src/pages/knowledge/shadow/workflowFrontendProjectionReducer.ts

Current path:

payload.draft_claims
→ section item draft_claims

Selector should then build:

section row
→ attempts by section_id
→ artifacts by dispatch_attempt_id
UI contract

Claim Builder artifact UI must render exactly:

Факт: {claim}
Вопросы: {possible_questions}
Не является темой факта: {exclusion_scope}

Do not render technical ids as user-facing content.

Allowed technical metadata in collapsed/small line:

model/provider;
token counts;
attempt status;
error kind/user message.

Not allowed as fact body:

section_id;
source_unit_ref;
source_document_ref;
work_item_id;
dispatch_attempt_id.
Contract tests to add/keep

Backend tests should cover:

validation accepts exact claim/granularity/possible_questions/exclusion_scope;
validation rejects extra legacy fields;
_draft_claims_event_payload includes dispatch_attempt_id/work_item_id/source_unit_ref and artifact fields;
Claim Builder frontend projector passes draft_claims.

Frontend tests should cover:

reducer attaches payload.draft_claims;
selector links artifacts to attempts by dispatch_attempt_id;
UI renders claim/questions/exclusion_scope labels.
Claim Builder technical debt
TD-CB-001: evidence_block currently equals source_unit_ref

Current validation model has evidence_block, but implementation sets it to source_unit_ref. This is acceptable only as explicit current behavior. It should not be displayed as source evidence excerpt unless backend starts storing an actual evidence excerpt.

TD-CB-002: draft_claims are attached to section item, not attempt

Event payload has dispatch_attempt_id, so frontend selector can map artifacts to attempts. Longer-term live-state could make this explicit by nesting artifacts under attempts or by exposing a normalized draft_claims collection.

TD-CB-003: targeted_read_kind and draft_claims_scope may be transitional

These fields are useful for future targeted reads, but current live UI has embedded draft_claims. Do not remove until tests prove no active consumer.

TD-CB-004: old answer drafts/fragments path conflicts with current contract

Any UI code that falls back to title/question/answer/content/text/body/fragments/drafts/answers is incompatible with the current Claim Builder contract and should be removed.
