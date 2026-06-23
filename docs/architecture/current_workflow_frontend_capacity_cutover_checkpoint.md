Current Workflow Frontend / Capacity Cutover Checkpoint
1. Scope and baseline

This checkpoint is the current source-of-truth architecture note for the Workflow Frontend / Capacity cutover on main after:

main HEAD: 924d8eda Remove remaining next_attempt_at retry timer residue

previous relevant commits:

c6267de5 execution-runtime: remove sleeping work item retry model
cadcfec4 Split LLM success from WorkItem completion
fee9f0b6 Add frontend projection client and compaction shadow reducer

Scope:

workflow/capacity/attempt events
frontend projection envelopes
idempotent reducer patches
artifact surfaces / live overlays
CapacityWindow ownership
LLM Runtime / Workbench / Execution Runtime boundaries
next_attempt_at / DEFERRED removal
legacy execution_queue cleanup state

This document is the current checkpoint, not a full replacement for the detailed maps. Older architecture documents may still contain historical migration context. When those documents conflict with this checkpoint, this checkpoint wins unless a newer checkpoint explicitly supersedes it.

2. Original problem: full live-state snapshot polling

The old realtime model was:

handler
→ outbox INSERT
→ pg_notify
→ SSE listener
→ fetch full workflow live-state snapshot
→ full JSON replacement in frontend

Problems:

full multi-query snapshot on every update;
no monotonic frontend cursor;
no idempotent reducer patch;
artifact surface and live overlay mixed;
GET live-state had/has compatibility/bootstrap/debug role;
snapshot must remain only bootstrap/recovery/debug, not primary realtime transport.

The old snapshot path is allowed only as compatibility/bootstrap/recovery/debug read model. It must not remain the primary realtime transport target.

3. Current target: projection events + reducer + targeted reads

The target realtime path is:

canonical workflow/capacity/attempt event
→ frontend projection envelope
→ reducer/idempotent patch
→ artifact surface or live overlay
→ targeted read only for artifact bodies/bootstrap/recovery

Artifact surfaces:

SourceDocument
SourceUnit
ClaimBuilderWorkItem
DispatchAttempt
DraftClaimObservation
DraftClaimClusterGroup
DraftClaimClusterBatch
pending_reduction_work
compaction_frontier_nodes
compaction_attempts
capacity_windows

Live overlays:

work item state
attempt provider/validation/persistence status
retry eligibility
capacity remaining/reset/exhausted/wakeup
compaction frontier dirty flags

Targeted reads are allowed for:

bootstrap
recovery after missed events
heavy artifact bodies
document-card row bodies
frontier/node/body loading after result-applied events

Targeted reads are not a replacement for every-second full live-state polling.

4. What is already implemented

Implemented:

frontend projection event client exists;
pure compaction shadow reducer foundation exists;
compaction document-card reducer contract exists;
capacity window projection events exist:
workflow_capacity_window_observed
workflow_capacity_window_exhausted
workflow_capacity_window_scheduled_wakeup
workflow_capacity_window_leased_work_item
capacity projector allowlists payload and filters old item retry timer fields;
ClaimBuilder outcome visibility exists through enriched section outcome projections;
DraftClaimObservation row availability exists as document-card surface;
Compaction pending work / attempts / frontier contract is documented;
projection stream hookup into KnowledgePage is still later;
visible React data-source switch is still later;
CapacityWindow dashboard UI is still later.

Important: implemented projection-event client and shadow reducer foundation do not mean the old KnowledgePage/live-state UI path has already been fully replaced.

5. What changed after next_attempt_at / DEFERRED removal

Removed from canonical runtime:

WorkItem.next_attempt_at
execution_work_items.next_attempt_at
LlmDispatchExecutionResult.next_attempt_at
WorkItemAttemptOutcomeRecord.next_attempt_at
WorkItemStatus.DEFERRED
LlmDispatchExecutionStatus.DEFERRED
WorkItemAttemptOutcomeStatus.DEFERRED
WorkItemStateMachine.defer_leased

Meaning:

WorkItem no longer sleeps.
RETRYABLE_FAILED means immediate eligibility + priority before READY.
Capacity/provider reset must never become WorkItem timing.

This is a runtime cutover. Any remaining mentions of next_attempt_at in historical docs, generated frontend type residue, sanitizer tests, or explicit drop migrations are not current WorkItem runtime semantics.

6. WorkItem lifecycle source of truth

Current WorkItem lifecycle meaning:

READY:

eligible ordinary queued work.

RETRYABLE_FAILED:

eligible immediately;
prioritized before READY;
carries failure classification/retry_plan;
no timer.

LEASED:

active execution lease only.

COMPLETED:

domain result applied.

SPLIT_SUPERSEDED:

parent replaced by children.

USER_ACTION_REQUIRED:

actual user/manual decision.

CANCELLED:

explicit cancellation.

TERMINAL_FAILED:

restricted/suspicious;
not normal provider/capacity/domain retry result.

Forbidden interpretation:

RETRYABLE_FAILED does not mean waiting until provider reset.
RETRYABLE_FAILED does not own run_after.
RETRYABLE_FAILED does not own quota reset.
RETRYABLE_FAILED does not sleep.
7. LLM Runtime vs Workbench domain boundary

LLM Runtime owns:

provider call;
provider technical result;
token usage;
technical error kind;
capacity observation payload;
raw/parsed provider response contract.

Workbench owns:

semantic validation;
empty-claims policy;
evidence/possible_questions/exclusion rules;
retry/fallback/split decision;
claim persistence;
compaction result application.

Execution Runtime owns:

WorkItem lifecycle;
leases;
attempts;
generic outcome mechanics.

No layer may smuggle provider/account/model capacity timing into WorkItem lifecycle.

8. WorkItem completion invariant

Core invariant:

Provider success is not task success.
LLM output valid is not domain completed.
WorkItem COMPLETED only after domain application/persistence.

Claim Builder intended chain:

LLM success
→ output validation
→ persist validated draft claim observations or accept valid empty
→ record outcome / mark WorkItem completed

Compaction intended chain:

LLM success
→ output validation
→ ApplyDraftClaimCompactionResult mutates generated nodes/frontier
→ WorkItem/attempt completion reflects domain-applied result

Current proof status:

The boundary was explicitly strengthened by cadcfec4.
ClaimBuilder completion ordering is guarded by current outcome/persistence tests.
Compaction ResultApplied vs attempt success is documented and partially guarded.
Complete end-to-end ordering for every compaction branch still needs guard/audit.

Do not mark a WorkItem completed at provider success time.

9. CapacityWindow / admission target model

CapacityWindow owns provider/account/model capacity state.

WorkItem waits passively in DB. CapacityWindow/admission tries to lease eligible WorkItems whenever current remaining capacity can fit estimated cost. Window waits only when no eligible WorkItem fits current remaining capacity.

Important rule:

reset_at is not automatically unavailable_until.

reset_at:

capacity will refill/change at this time.

hard_unavailable_until:

provider/account/model cannot accept any request before this time.

Admission target:

eligible work:

RETRYABLE_FAILED first
READY second

estimated total:

estimated_prompt_tokens
estimated_completion_tokens
safety_overhead

admission:

pick first eligible item that fits current window;
reserve capacity;
lease WorkItem;
dispatch attempt;
update capacity observation;
immediately try again;
schedule wakeup only if nothing fits.

Admission must be able to skip a large item that does not fit residual tokens and select a smaller eligible item when such a policy is implemented and guarded.

10. Current CapacityWindow implementation status

Implemented:

capacity observation event/projection;
capacity exhausted event/projection;
capacity scheduled wakeup event/projection;
capacity leased work item event/projection;
compaction capacity correlation source model;
capacity projection payload guards.

Still not fully proven:

first-class durable CapacityWindow table/state as sole admission source of truth;
admission picking smaller WorkItems that fit residual tokens while larger ones wait;
complete frontend CapacityWindow dashboard UI;
elimination of scalar capacity_retry_at as orchestration shortcut.

Current state should be described as CapacityWindow event/projection boundary plus partial orchestration support, not as complete durable Capacity Runtime admission.

11. Frontend projection/reducer implementation status

Implemented:

frontend projection event client;
pure compaction shadow reducer foundation;
event id idempotency;
attempt dedupe by dispatch_attempt_id;
entity keys:
cluster_groups[group_ref]
cluster_batches[batch_ref]
compaction_frontier_nodes[node_ref]
pending_reduction_work[work_item_id]
compaction_attempts[dispatch_attempt_id]
capacity_windows[window_key]

Still later:

KnowledgePage projection stream hookup;
shadow parity/debug comparison with old workflow-live-state;
visible DocumentCard data-source switch;
CapacityWindow dashboard UI;
complete removal of live-state snapshot from primary realtime path.

Generated frontend types may still carry compatibility fields from the old live-state snapshot model. That residue is not current target architecture and should be cleaned in a separate frontend/generated-contract slice.

12. Legacy execution_queue status

execution_queue still exists and is runtime-used by old queue infrastructure/tools.

After commit 924d8eda, legacy execution_queue.next_attempt_at is removed by migration 099_drop_legacy_execution_queue_next_attempt_at.sql, and QueueRepository no longer uses sleeping retry timing.

This legacy queue is not the canonical Workbench Execution Runtime.

Do not delete the entire legacy queue as part of CapacityWindow work without a separate import/call graph audit covering:

src/infrastructure/queue/*
src/infrastructure/db/repositories/queue_repository.py
src/agent/nodes/*
src/tools/*
src/interfaces/http/dependencies.py
src/interfaces/http/metrics.py
src/interfaces/composition/fastapi_lifespan.py
13. TERMINAL_FAILED status and audit requirement

TERMINAL_FAILED remains present.

It must not represent:

normal capacity exhaustion;
normal provider rate limit;
normal validation retry;
normal model fallback;
normal retriable network/provider failure.

It should be restricted to non-recoverable cases after explicit audit, for example:

invariant violation;
irrecoverable corrupted state;
unsupported configuration;
authentication/authorization/configuration failure where retry cannot help;
explicit terminal domain/user-action decision.

Pending audit requirement:

Audit every producer of TERMINAL_FAILED / terminal_failed / TERMINAL_INVALID.

Classify each as:

truly terminal;
should be retryable;
should be user-action-required;
should be capacity-owned wait;
should be split/fallback.

Do not delete TERMINAL_FAILED blindly.

14. Stale docs / generated frontend type residue

Known stale/historical residue classes:

docs that still describe Patch 17C compatibility chain;
docs that mention LlmDispatchExecutionResult.next_attempt_at as migration baseline;
docs that mention WorkItem.next_attempt_at as old/current-to-target map;
generated/manual frontend live-state types that still contain next_attempt_at;
sanitizer tests that intentionally inject next_attempt_at to prove it is filtered;
explicit drop migrations that must mention removed columns.

Docs updated by this checkpoint must treat those as historical/superseded unless a section explicitly says it is describing old migration baseline.

Current source of truth:

docs/architecture/current_workflow_frontend_capacity_cutover_checkpoint.md

15. Next recommended implementation slice

Recommended next slice:

CapacityWindow durable admission checkpoint.

Minimal scope:

Audit current capacity_retry_at producers/consumers.
Define first-class durable provider/account/model CapacityWindow state or prove why existing observations are enough.
Make admission select RETRYABLE_FAILED before READY without WorkItem timers.
Add guard for "large item does not block smaller item that fits residual tokens" if target policy is adopted now.
Keep WorkItem passive.
Keep provider reset out of WorkItem/live-state retry_timer.
Add frontend projection stream hookup to KnowledgePage only after shadow parity path.

Do not mix this with deleting legacy queue or rewriting frontend UI rendering.

16. Non-negotiable invariants
WorkItem no longer stores next_attempt_at.
WorkItem no longer has DEFERRED lifecycle.
RETRYABLE_FAILED is immediately eligible.
RETRYABLE_FAILED is prioritized before READY.
CapacityWindow owns provider/account/model timing.
Provider reset is not WorkItem retry timer.
Provider success is not WorkItem completed.
LLM valid output is not WorkItem completed.
WorkItem completed means domain result applied/persisted.
Snapshot is bootstrap/recovery/debug, not primary realtime transport.
Projection events must be idempotently reducible.
Heavy bodies belong behind targeted reads.
Legacy execution_queue is separate from canonical Execution Runtime.
TERMINAL_FAILED must be audited and restricted.
17. Verification commands

Checkpoint guard:

python -m pytest tests/architecture/test_current_workflow_frontend_capacity_cutover_checkpoint.py -q -o addopts=''

Architecture test formatting/checks:

python -m ruff format tests/architecture

python -m ruff check tests/architecture

Docs link/status note check:

rg -n "Current status note after 924d8eda|current_workflow_frontend_capacity_cutover_checkpoint" docs/architecture/capacity_window_refactor_map.md docs/architecture/workflow_frontend_event_projection_map.md docs/architecture/draft_claim_compaction_document_card_contract.md

Runtime/frontend code should not be changed by this docs checkpoint. Use git diff --name-only to confirm only docs and architecture tests changed.