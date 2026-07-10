# RAG Eval V2 continuation ledger

## Current checkpoint

**Date:** 2026-07-10  
**Committed base:** `aef56def22f943ee1f0caa1037682ffa542ad974`  
**Working tree:** contains an uncommitted continuation checkpoint  
**Overall status:** IN PROGRESS — full RAG Eval V2 Definition of Done is not complete

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
Roles and retrieval outcome foundation

The current checkpoint contains additive migrations:

120_extend_workbench_rag_eval_run_progression.sql
121_add_workbench_rag_eval_question_roles.sql
122_create_workbench_rag_eval_retrieval_outcomes.sql

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

This is a composition foundation. Full delayed-command and transactional pump
behaviour has not yet been proven end to end.

Frontend checkpoint

The current frontend changes:

remove stale local lastRun as workflow truth;
read the visible run from the persisted latest-run query;
centralize React Query keys;
treat the HTTP 202 result as a started run, not a completed run;
invalidate persisted run queries after start and promotion actions.

This is not the completed frontend progression UI.

Current verified test evidence

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

Partial implementations that must not be described as complete
Retry and fallback

Retry/fallback policy files exist, but the current qgen validator still requires
a canonical cleanup.

Known problems that remain to be resolved:

retry limit is currently selected inside the qgen validation path;
invalid output handling still catches an overly broad exception;
real input-token data must be used for oversized-input fallback decisions;
retry/fallback must be proven through persisted attempts and dispatches;
minute, daily, auth, oversized-input and invalid-contract paths require
explicit end-to-end tests.

Do not report retry/fallback as complete until those tests pass.

Four-account support

The current test proves that:

four configured Groq account refs create four transport objects;
generic preparation receives the account refs.

It does not yet prove all of:

real admission across accounts;
persisted attempt allocations;
persisted dispatch account refs;
per-account capacity observations;
reservation safety under concurrent preparation.

Do not call this a complete four-account integration proof.

Production pump

The pump is composed and invoked from the shared runtime loop.

Still required:

due RAG Eval command selection test;
future run_after exclusion;
later due-command pickup;
completed-command exclusion;
transaction boundary proof;
failure isolation between runs;
no blocked-command busy loop.
Roles lifecycle

Role vocabulary, deterministic policy and persistence foundation exist.

Still required:

materialize existing published aliases as BASELINE;
persist generated questions as PROMOTION_POOL or HOLDOUT;
expose roles through the read API;
enforce candidate prohibition for holdouts;
use holdouts in post-promotion verification.
Retrieval

Canonical outcome model, migration, policy and repository persistence exist.

The actual retrieval workflow handler does not exist yet.

Not implemented

The following verticals remain incomplete:

Retrieval workflow
production retrieval handler;
baseline materialization;
evaluation of baseline, promotion-pool and holdout questions;
top-k diagnostic persistence through the workflow;
canonical outcome persistence through the workflow;
idempotent rerun behaviour;
transition to adjudication scheduling;
dispatcher registration for retrieval execution.
Adjudication
versioned adjudication prompt;
eligibility planner;
adjudication work items;
adjudication preparation;
adjudication execution;
adjudication retry/fallback;
adjudication reconcile;
adjudication persistence;
terminal-failure blocking.
Promotion review
canonical candidate policy;
VALID_TARGET_QUERY gate;
explicit approve/reject transitions;
expanded promotion statuses;
candidate linkage to outcome and adjudication;
holdout and baseline exclusion.
Reversible application
grouped application per runtime entry;
alias-count policy;
one embedding recalculation per affected entry;
revision snapshot before mutation;
single active pending revision invariant;
atomic mutation plus revision creation.
Verification
before/after verification dataset;
baseline verification;
holdout verification;
neighbour/competitor regression checks;
persisted verification metrics;
regression-failed state;
explicit accept;
explicit rollback;
restoration of previous aliases, embedding text and embedding vector.
HTTP and read model
outcomes endpoint;
adjudications endpoint;
revisions endpoint;
verification endpoint;
candidate approve/reject endpoints;
apply-approved endpoint;
accept-revision endpoint;
rollback-revision endpoint;
complete persisted progression payloads for all phases.
Frontend
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

The complete required gates have not yet passed:

python -m ruff format --check src tests
python -m ruff check src tests
python -m mypy src
python -m pytest -q

cd frontend
npm run lint
npm run type-check
npm run build
npm test -- --run

Current full-suite failures must not be labelled “pre-existing” unless that is
proven against the clean committed base.

Next exact implementation sequence

Continue from the current working tree in this exact order.

1. Finish current checkpoint correctness
clean up qgen invalid-output retry/fallback separation;
remove hard-coded or fabricated retry inputs;
fix the current full backend architecture failure;
fix current mypy failures without restoring the legacy direct runtime;
prove the due-command pump behaviour;
prove four-account admission/reservation/dispatch behaviour;
run the complete repaired qgen/runtime focused suite.
2. Implement retrieval workflow
materialize baseline questions;
persist generated roles;
execute production retrieval;
persist top-k rows;
persist canonical outcomes;
register and dispatch retrieval command;
transition to adjudication scheduling.
3. Implement adjudication
migration/model/repository;
prompt and validator;
planner;
generic prepare/execute/reconcile;
retry/fallback;
terminal blocking.
4. Implement promotion review
candidate policy;
approve/reject state transitions;
API/read projection.
5. Implement reversible grouped application
revisions migration/model/repository;
atomic snapshot and mutation;
one embedding generation per target entry;
active-revision guard.
6. Implement post-promotion verification
before/after retrieval outcomes;
baseline/holdout/neighbour metrics;
regression policy;
explicit accept/rollback.
7. Complete API, SSE and frontend
persisted read endpoints;
workflow-event projection;
full progression UI;
revision controls.
8. Run all final gates

Do not report the original RAG Eval V2 task as complete until every required
backend and frontend gate passes.

Continuation instruction

Continue from the current uncommitted working tree.

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

First finish the partial correctness items listed above, then implement the
retrieval workflow vertical.

Do not commit or push without an explicit user request.
