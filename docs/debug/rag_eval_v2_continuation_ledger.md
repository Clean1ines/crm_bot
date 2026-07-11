# RAG Eval V2 continuation ledger

## Current checkpoint

**Date:** 2026-07-11
**Committed base:** `aef56def22f943ee1f0caa1037682ffa542ad974`  
**Working tree:** contains the adjudication runtime vertical checkpoint
**Overall status:** IN PROGRESS — qgen complete; retrieval complete; adjudication complete; promotion review ready

This document describes the current working tree. It must not instruct a future
agent to recreate question-generation workflow components that already exist.

---

## Canonical contracts fixed in the current checkpoint

### Question roles

The only valid question roles are:

```text
BASELINE
PROMOTION_POOL
HOLDOUT

Semantics:

existing published possible questions become BASELINE;
generated questions are deterministically divided into PROMOTION_POOL
and HOLDOUT;
each generated set contains at least two holdout questions;
BASELINE and HOLDOUT are never promotion-eligible;
HOLDOUT questions must participate in post-promotion verification and
must never be promoted in the same cycle.
Retrieval classifications

The only valid canonical retrieval classifications are:

PASS_STRONG
PASS_WEAK
CONFUSION
MISS
EXISTING_ALIAS_RETRIEVAL_FAILURE

The previous temporary vocabulary:

TOP1
TOP3
TOP5
CONFUSED_WITHIN_DOCUMENT

is invalid and must not be reintroduced.

Retrieval outcome identity

A canonical retrieval outcome is scoped by:

outcome_id
run_id
question_id
project_id
evaluation_stage

The supported stages are:

initial
verification_before
verification_after

The uniqueness boundary is:

(run_id, question_id, evaluation_stage)

A retrieval outcome contains:

expected runtime entry and fact
expected rank and score
best competitor runtime entry and fact
best competitor score
score margin
canonical classification
Implemented and currently verified
Generic preparation/runtime foundation
PrepareLlmDispatchBatch uses DispatchPreparationBuilderRegistry.
Claim Builder remains the default preparation builder.
Work-kind-specific builders can be registered without duplicating generic:
capacity projection;
admission;
reservations;
leases;
attempts;
persisted dispatches;
retry scheduling.
Separate RAG Eval work kinds exist:
workbench_rag_eval.question_generation;
workbench_rag_eval.adjudication.
Question generation
one published runtime entry maps to one qgen work item;
one qgen work item maps to one normal LLM dispatch;
qgen uses the generic prepared-dispatch execution path;
direct provider dispatch from the RAG Eval context is forbidden;
the qgen parser requires exactly ten generated questions;
exact question-kind distribution is validated;
duplicate generated questions are rejected;
duplicates against existing possible questions are rejected;
generation model, account and slot metadata are persisted;
the route catalog is:
primary: qwen/qwen3-32b;
automatic fallback: openai/gpt-oss-120b.
Start workflow

StartWorkbenchRagEvalV2 currently:

resolves active published entries;
rejects an empty selected scope;
creates a running run;
persists the initial phase and progress projection;
schedules one qgen work item per selected entry;
appends the initial durable qgen prepare command;
returns an asynchronous running projection through HTTP 202;
does not wait for LLM completion.
Workflow definition and qgen handlers

The separate RAG Eval workflow vocabulary exists, including commands/events for
the intended complete cycle.

The following qgen commands are implemented and wired:

PREPARE_QUESTION_GENERATION_DISPATCH_BATCH
EXECUTE_QUESTION_GENERATION
RECONCILE_QUESTION_GENERATION_PROGRESS

The qgen prepare handler:

calls generic PrepareLlmDispatchBatch;
appends durable execute commands;
supports delayed preparation through run_after;
writes workflow events and timeline entries.

The qgen execute path:

calls ExecutePreparedLlmDispatchAttempt;
validates and persists generated questions;
persists capacity observations;
appends capacity-window wakeups;
appends a durable reconcile command;
writes workflow events and timeline entries.

The qgen reconcile path supports:

PREPARE_NEXT_BATCH_NOW
PREPARE_NEXT_BATCH_LATER
WAIT_FOR_ACTIVE_ATTEMPTS
QUESTION_GENERATION_DRAINED
QUESTION_GENERATION_BLOCKED

A qgen run may drain only when:

total work-item count is greater than zero;
all work items completed successfully;
there are no terminal failures;
there are no waiting or active items;
every expected runtime entry has exactly ten persisted generated questions.

Successful qgen drain transitions to retrieval evaluation and appends one
idempotent retrieval command.

Persisted run progression foundation

Run persistence now supports:

RUNNING
WAITING_CAPACITY
PROMOTION_REVIEW
VERIFYING
COMPLETED
BLOCKED
FAILED

Persisted phases include the complete intended lifecycle.

The run/read projection currently contains:

current phase;
selected entry count;
scheduled qgen item count;
waiting/running/completed/failed counts;
generated question-set count;
capacity next-due timestamp;
capacity model/account metadata;
blocked and failed reasons.
adjudication totals/waiting/running/completed/failed;
promotion candidate count.
Roles and retrieval outcome foundation

The current checkpoint contains additive migrations:

120_extend_workbench_rag_eval_run_progression.sql
121_add_workbench_rag_eval_question_roles.sql
122_create_workbench_rag_eval_retrieval_outcomes.sql
123_add_workbench_rag_eval_retrieval_progress.sql
124_add_workbench_rag_eval_evaluated_at.sql
125_create_workbench_rag_eval_question_adjudications.sql
126_add_workbench_rag_eval_adjudication_progress.sql

Migration 121 supports:

baseline
promotion_pool
holdout

Migration 122 supports:

pass_strong
pass_weak
confusion
miss
existing_alias_retrieval_failure

The repository can persist:

question-role assignments;
run/project/stage-scoped canonical retrieval outcomes.

The exact per-entry question coverage query has been changed to a grouped
aggregate that rejects:

zero entries;
missing entries;
nine-question sets;
eleven-question sets;
any entry whose count is not exactly ten.
Production composition foundation

A separate RAG Eval workflow runtime composition exists and reuses:

the generic preparation boundary;
the generic prepared-dispatch execution boundary;
the existing multi-account Groq executor;
execution-runtime repositories;
workflow-runtime repositories;
capacity observation persistence;
the RAG Eval repository.

The shared runtime loop currently invokes the RAG Eval due-command pump.

Delayed-command selection, pump failure isolation and transaction boundaries
are covered by focused production composition tests.

Frontend checkpoint

The current frontend changes:

remove stale local lastRun as workflow truth;
read the visible run from the persisted latest-run query;
centralize React Query keys;
treat the HTTP 202 result as a started run, not a completed run;
invalidate persisted run queries after start and promotion actions.

This is not the completed frontend progression UI.

Current verified test evidence

Adjudication continuation checkpoint:

- Focused RAG Eval/backend slice: `200 passed`.
- Full backend: `2676 passed, 2 skipped`.
- Ruff: passed.
- Mypy: passed.
- Frontend type-check/build/tests: passed.
- Frontend tests: `56 passed`.
- Changed RAG Eval frontend ESLint: no RAG Eval frontend changes in this checkpoint.

Latest canonical repair slice:

35 passed

It covers:

exact canonical question roles;
exact canonical retrieval classifications;
run/project/stage-scoped outcome construction;
role and outcome migration contracts;
role determinism and minimum holdout allocation;
holdout promotion prohibition;
all five retrieval classifications;
exact score-margin calculation;
qgen reconcile decisions and transitions;
persisted progression repository behaviour;
exact question-set coverage;
canonical outcome persistence.

Previous checkpoint evidence recorded by the implementation agent:

qgen/retry/runtime focused slice: 34 passed
persisted progression slice: 23 passed
roles/outcomes slice before canonical repair: 17 passed
production composition slice: 5 passed
frontend tests: 54 passed
frontend type-check: passed
frontend build: passed
Ruff focused checks: passed

These previous focused counts are historical evidence only. They do not replace
the required final full-suite gates.

Completed in this continuation

- qgen output validation is separated from route/retry decisions and uses a named validation policy/config.
- Generated roles are assigned before persistence and written in the same INSERT path; generated sets contain at least two HOLDOUT questions.
- The legacy synchronous `RunWorkbenchRagEval` boundary is retired fail-fast and production composition no longer uses it.
- Existing published possible questions are materialized idempotently as BASELINE immediately before retrieval.
- `RUN_RETRIEVAL_EVALUATION` is registered in dispatcher, drain and production runtime composition.
- Production `SearchPublishedWorkbenchRuntime` evaluates all persisted roles project-wide with `top_k >= 5`.
- Diagnostic top-k rows and canonical `initial` outcomes are persisted idempotently; no promotion candidates are created.
- Retrieval counters and phase transition to `ADJUDICATION_SCHEDULING` are persisted, with one durable `SCHEDULE_ADJUDICATION_WORK` command.
- Migration `123_add_workbench_rag_eval_retrieval_progress.sql` adds retrieval counters.
- Migration `125_create_workbench_rag_eval_question_adjudications.sql` adds persisted adjudications with `(run_id, question_id, outcome_id)` uniqueness.
- Migration `126_add_workbench_rag_eval_adjudication_progress.sql` adds adjudication counters and persisted promotion candidate count.

Four-account support

The production composition proof covers four configured Groq account refs, four
distinct transports, real admission across multiple accounts, persisted
dispatch account refs, per-account/model capacity observations and persisted
reservation safety on repeated preparation.

Production pump

The pump is composed and invoked from the shared runtime loop. The production
matrix covers due command selection, future `run_after` exclusion, later
due-command pickup, completed-command exclusion, failure isolation between
runs, no blocked-command busy loop, repeated-pump idempotency and observable
per-run failures.
Adjudication

The adjudication vertical is implemented:

- `SCHEDULE_ADJUDICATION_WORK` plans one stable work item for each eligible initial outcome.
- Eligibility is limited to PROMOTION_POOL, promotion-eligible, low-ambiguity questions with MISS, CONFUSION or policy-enabled PASS_WEAK classifications.
- BASELINE, HOLDOUT, PASS_STRONG, existing-alias failures, non-promotion-eligible questions and medium/high ambiguity risks are excluded.
- The exact work kind is `workbench_rag_eval.adjudication`.
- The adjudication prompt is versioned as `workbench_rag_eval_question_adjudication.ru.v1.txt`.
- `RagEvalAdjudicationDispatchPreparationBuilder` is registered through `DispatchPreparationBuilderRegistry`.
- `PREPARE_ADJUDICATION_DISPATCH_BATCH` reuses generic capacity admission, reservations, leases, attempts and dispatch persistence.
- `EXECUTE_ADJUDICATION` calls `ExecutePreparedLlmDispatchAttempt`, strict-validates output and persists model/account/slot/attempt metadata.
- Invalid output retry, fallback to `openai/gpt-oss-120b`, capacity wait and terminal failure handling remain owned by the generic persisted attempt path.
- `RECONCILE_ADJUDICATION_PROGRESS` supports now/later/wait/drained/blocked decisions.
- Drained adjudication creates promotion candidates only for `VALID_TARGET_QUERY` with `promotion_recommended=true`.
- Terminal adjudication failure blocks the run and does not create candidates.
- Zero eligible scheduling transitions directly to PROMOTION_REVIEW with zero candidates and a canonical candidates-ready event.
Retrieval

The retrieval handler and production transition now exist. Baseline
materialization, diagnostic top-k rows, canonical outcomes, evaluated statuses,
retrieval counters, run phase, workflow event, timeline, progress snapshot,
next adjudication scheduling command and completion retrieval command are
covered by a single transaction-boundary proof.

Not implemented

The following verticals remain incomplete:

Promotion review actions:
explicit candidate approve/reject transitions.

Reversible revisions:
grouped application per runtime entry;
alias-count policy;
one embedding recalculation per affected entry;
revision snapshot before mutation;
single active pending revision invariant;
atomic mutation plus revision creation.

Verification:
before/after verification dataset;
baseline verification;
holdout verification;
neighbour/competitor regression checks;
persisted verification metrics;
regression-failed state.

Accept/rollback:
explicit accept;
explicit rollback;
restoration of previous aliases, embedding text and embedding vector.

Full frontend progression:
full phase progression;
capacity-wait details;
attempts, retries and fallback display;
canonical retrieval outcomes;
adjudication display;
candidate approval/rejection;
revision state;
before/after verification metrics;
accept/rollback actions;
RAG Eval workflow-event/SSE invalidation.
Final quality gates

Current checkpoint validation:

```text
focused RAG Eval/backend slice: 200 passed
full backend: 2676 passed, 2 skipped
ruff: passed
mypy: passed
frontend type-check/build/tests: passed
frontend tests: 56 passed
changed RAG Eval frontend ESLint: no RAG Eval frontend changes in this checkpoint
```

Next exact implementation sequence

Continue from the current working tree in this exact order.

1. Implement explicit promotion review actions
candidate approve/reject state transitions;
API/read projection.
2. Implement reversible grouped application
revisions migration/model/repository;
atomic snapshot and mutation;
one embedding generation per target entry;
active-revision guard.
3. Implement post-promotion verification
before/after retrieval outcomes;
baseline/holdout/neighbour metrics;
regression policy;
explicit accept/rollback.
4. Complete API, SSE and frontend
persisted read endpoints;
workflow-event projection;
full progression UI;
revision controls.
5. Run all final gates

Do not report the original RAG Eval V2 task as complete until every required
backend and frontend gate passes.

Continuation instruction

Continue from the current working tree.

Do not restart question generation.

Do not recreate:

workflow enums;
qgen planner;
qgen prepare;
qgen execute;
qgen reconcile;
run progression migration;
question-role migration;
retrieval-outcome migration;
production runtime composition foundation.

The qgen/retrieval/adjudication checkpoint is ready for the next vertical:
explicit promotion review actions.

Do not commit or push without an explicit user request.
