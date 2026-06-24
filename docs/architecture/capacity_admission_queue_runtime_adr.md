# ADR: Capacity Admission Queue Runtime

Status: Accepted target architecture.

## Context

The current implementation already has separate pieces of a capacity-driven execution model:

- Execution Runtime owns generic `WorkItem` lifecycle.
- Work items move between `ready`, `leased`, `retryable_failed`, `completed`, `terminal_failed`, `cancelled`, `split_superseded`, and `user_action_required`.
- LLM work item schedules already carry admission-relevant token estimates.
- Capacity Runtime owns provider/account/model capacity observations, reservations, reset timing, and admission constraints.
- Knowledge Workbench sagas currently orchestrate claim-builder and compaction work through workflow commands.
- CapacityWindow workflow events already exist for exhausted windows, scheduled wakeups, and leased work items.
- Frontend live state must not be driven by repeated full snapshot polling.

The missing architectural layer is a durable queue/projection runtime that connects WorkItem lifecycle, capacity windows, and admission passes without mixing their responsibilities.

## Decision

Introduce a dedicated runtime/bounded context:

`capacity_admission_queue`

The Capacity Admission Queue Runtime owns durable projection and dispatch signals for capacity-based admission. It is not the source of truth for WorkItem lifecycle, LLM provider execution, Workbench semantics, or frontend rendering.

Its responsibility is:

1. Maintain a durable admission projection of work items relevant to capacity-based dispatch.
2. Coalesce due queue changes and capacity changes into dirty admission lanes.
3. Trigger admission passes for eligible lanes/windows.
4. Ensure admission is based on current capacity and fitting work items, not arbitrary candidate scan limits.
5. Support crash-safe, idempotent, multi-worker operation.

## Non-negotiable rules

### WorkItem remains generic

Execution Runtime owns WorkItem lifecycle only.

It must not know about:

- Groq;
- provider accounts;
- model routes;
- prompt contracts;
- token caps;
- Workbench claim/compaction semantics;
- frontend progress state.

Execution Runtime may emit lifecycle events or expose lifecycle changes, but it must remain context-agnostic.

### Requested items is not candidate scan

`requested_items` may be used only as an optional safety cap for how many items one admission pass may lease/start.

It must not decide how many due candidates are inspected.

These are forbidden as target architecture:

- `peek_due_work_items(requested_items=N)` as the main admission candidate source;
- bounded overfetch multipliers such as `requested_items * 4`;
- page scan as the semantic solution to capacity fitting;
- "first N did not fit, therefore capacity is exhausted".

Admission must search an indexed admission projection using a capacity fit predicate.

### Admission is lane-based, not window-addressed

A WorkItem lifecycle change does not target one specific CapacityWindow.

A lifecycle or split event marks an Admission Lane dirty.

An Admission Lane is identified by at least:

- `work_kind`;
- `provider`;
- `model_ref`.

It may also include project, tenant, workflow, organization, or account scope if needed by execution policy.

Capacity windows eligible for that lane may all attempt admission. Atomic capacity reservation and WorkItem lease decide which window wins.

### Queue changes are wakeups, not commands to pick an item

A queue change event does not mean:

"pick this exact WorkItem."

It means:

"the admission projection for this lane changed; run an admission pass."

The admission pass always consults the current projection and current capacity window state.

### Capacity changes are also wakeups

Capacity changes also dirty a lane or request an admission pass.

Examples:

- provider reset observed;
- reservation released;
- reservation expired;
- attempt finished and capacity became available;
- account/model route became available;
- manual resume.

### Retry priority

When a CapacityWindow performs an admission pass:

1. Find a fitting `retryable_failed` candidate for the lane and current remaining window.
2. If none exists, find a fitting `ready` candidate.
3. If none exists, do not lease work.

If many fitting retries exist, deterministic order is enough.

### Fitting predicate

Each admission candidate must have known cost before it becomes ordinary due work.

At minimum:

- `estimated_input_tokens`;
- `estimated_output_tokens`;
- `effective_output_cap_tokens`;
- `reserved_total_tokens`;
- `provider`;
- `model_ref`;
- `work_kind`.

A candidate fits a CapacityWindow only when its reserved total and output requirements fit the current remaining window for the selected provider/account/model.

### Split semantics

`split_superseded` means the parent WorkItem is no longer eligible for admission.

The parent transition itself does not wake admission as a new due item.

The split operation wakes admission because it creates child WorkItems that are `ready`.

A split transaction must:

1. mark the parent as `split_superseded`;
2. remove or mark the parent as non-due in the admission projection;
3. create N child WorkItems;
4. create N child admission projection rows with known token cost;
5. emit or coalesce one `DueWorkQueueChanged` event for the lane.

It must not emit one admission wakeup per child if one coalesced lane wakeup is enough.

### Leased-to-retry semantics

`leased -> retryable_failed` means a previously in-flight item returned to the due queue.

It does not mean the returning WorkItem must be selected directly.

It means:

1. update the admission projection to `retryable_failed`;
2. mark the lane dirty;
3. run admission;
4. select the best currently fitting retry/ready candidate by normal priority.

### Active leased semantics

If no fitting due item exists but there are active leased WorkItems in the lane, the lane/window is not complete.

It is waiting for in-flight work.

When leased work returns to `retryable_failed`, `ready`, `completed`, `terminal_failed`, `split_superseded`, or another relevant lifecycle state, the projection and lane state must be updated.

### Source of truth and wakeups

Postgres is the durable source of truth.

`LISTEN/NOTIFY` or in-process notifications may be used only as wakeups.

They must never be the only source of truth.

A dispatcher must be able to crash and resume from durable tables.

## Target components

### CapacityAdmissionWorkItemProjection

Durable read model of WorkItems relevant to capacity admission.

Potential table:

`capacity_admission_work_items`

Candidate columns:

- `work_item_id`;
- `work_kind`;
- `workflow_run_id`;
- `project_id`;
- `provider`;
- `model_ref`;
- `status`;
- `retry_plan`;
- `estimated_input_tokens`;
- `estimated_output_tokens`;
- `effective_output_cap_tokens`;
- `reserved_total_tokens`;
- `source_ref`;
- `created_at`;
- `updated_at`.

The status is a projection of Execution Runtime lifecycle state, not the authoritative lifecycle source.

### CapacityAdmissionLane

A logical lane of work that a dispatcher can wake and a CapacityWindow can attempt to drain.

Candidate lane key:

- `work_kind`;
- `provider`;
- `model_ref`;
- optional project/tenant/workflow/account scope.

### DueWorkQueueChanged

Durable event or coalesced dirty flag meaning:

"The due queue projection for this lane changed."

Reasons include:

- `work_item_scheduled_ready`;
- `work_item_returned_retryable`;
- `work_item_released_ready`;
- `user_action_resolved_ready`;
- `user_action_resolved_retryable`;
- `split_created_child_ready_items`.

### CapacityWindowChanged

Durable event or coalesced dirty flag meaning:

"Capacity for this lane/window changed and admission should be retried."

Reasons include:

- `provider_reset_observed`;
- `reservation_released`;
- `reservation_expired`;
- `attempt_finished_capacity_available`;
- `manual_resume`;
- `account_model_available`.

### AdmissionDispatcher

A durable dispatcher that:

1. reads dirty lanes;
2. obtains a lane lock or claim;
3. runs one or more admission passes;
4. clears or reschedules lane state only when safe;
5. handles duplicate wakeups idempotently.

### CapacityWindowAdmissionPass

Application service that:

1. reads current capacity window state;
2. finds one fitting `retryable_failed` candidate;
3. otherwise finds one fitting `ready` candidate;
4. reserves capacity;
5. leases WorkItem by id;
6. starts attempt or appends execute command;
7. emits capacity/admission events;
8. repeats while capacity remains available.

## Target fit query

The candidate query must search the indexed admission projection, not a small arbitrary prefix of due WorkItems.

Conceptual retry query:

```sql
SELECT work_item_id
FROM capacity_admission_work_items
WHERE work_kind = $1
  AND provider = $2
  AND model_ref = $3
  AND status = 'retryable_failed'
  AND reserved_total_tokens <= $4
ORDER BY updated_at, work_item_id
LIMIT 1;

If no retry fits, the same query is run for ready.

The actual implementation may include account, tenant, project, workflow, route, lock, or reservation constraints.

Race handling

Multiple windows/workers may try the same candidate.

Correctness must rely on atomic operations:

reserve or lock capacity for a provider/account/model window;
lease WorkItem by id with FOR UPDATE SKIP LOCKED;
make duplicate admission passes harmless.

If a candidate is lost to another worker, the admission pass retries against current projection/capacity state.

Migration plan
Phase 1: ADR and guards

Create this ADR and architecture tests that prevent returning to requested_items-driven candidate scan.

Phase 2: Schema

Add durable admission projection and lane/event/dirty state tables.

Phase 3: Projection on scheduling

When WorkItems are scheduled, write admission projection rows with known token cost in the same transaction or through a durable outbox projection.

Phase 4: Projection on lifecycle changes

When WorkItems transition, update projection and emit/coalesce lane dirty signals.

Important transitions:

ready -> leased;
retryable_failed -> leased;
leased -> retryable_failed;
leased -> ready;
leased -> completed;
leased -> terminal_failed;
leased -> split_superseded;
user_action_required -> ready;
user_action_required -> retryable_failed.
Phase 5: Fit-aware admission repository

Add repository/query methods that find fitting retry/ready candidates from the projection.

Phase 6: Dispatcher

Add lane dispatcher with durable locks/cursors/claims and idempotent processing.

Phase 7: Replace prepare hot path

Replace prepare_llm_dispatch_batch candidate scan/lease path with CapacityWindowAdmissionPass.

Phase 8: Split integration

Ensure split creates child admission projection rows and emits one coalesced due queue changed signal.

Phase 9: Capacity changed integration

Ensure provider reset, reservation release/expiry, and attempt completion can wake admission lanes.

Phase 10: Frontend live state

Expose event/projection deltas, not full snapshot polling.

Explicit non-goals for ADR-1

ADR-1 does not implement:

new production tables;
new dispatcher;
new repository;
new frontend reducers;
migration away from workflow commands;
deletion of existing prepare handlers;
provider API calls.

ADR-1 defines the target architecture and guards against known wrong designs.
