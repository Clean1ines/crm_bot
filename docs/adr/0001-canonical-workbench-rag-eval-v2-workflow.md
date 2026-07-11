# ADR-0001: Canonical Workbench RAG Eval V2 workflow

Date: 2026-07-10
Status: accepted — qgen complete; retrieval complete; adjudication complete; promotion candidate approve/reject complete
Deciders: crm_bot maintainers

Context

The previous Workbench RAG Eval path combined synchronous evaluation,
top-k diagnostic rows and direct promotion application.

That design did not provide:

durable phase progression;
generic execution-runtime work items;
capacity-aware preparation and wakeups;
persisted retry and fallback history;
a canonical retrieval outcome;
adjudication before promotion;
holdout protection;
reversible embedding changes;
post-promotion regression verification;
explicit accept or rollback.

The repository already contains generic workflow, execution, capacity,
reservation and provider-routing infrastructure. RAG Eval must reuse those
boundaries rather than creating a second runtime.

Decision

Workbench RAG Eval V2 is a persisted, backend-owned workflow.

Its intended lifecycle is:

scope resolution
→ question-generation scheduling
→ question-generation prepare
→ question-generation execute
→ question-generation reconcile
→ retrieval evaluation
→ adjudication scheduling
→ adjudication prepare
→ adjudication execute
→ adjudication reconcile
→ promotion review
→ grouped promotion application
→ reversible embedding revision
→ post-promotion verification
→ explicit accept or rollback
→ completed / blocked / failed
Generic runtime ownership

Both LLM phases use the existing generic runtime path:

workflow command
→ execution work item
→ persisted schedule
→ generic dispatch preparation
→ capacity projection
→ persisted reservation
→ lease
→ attempt
→ persisted dispatch
→ ExecutePreparedLlmDispatchAttempt
→ phase validator
→ domain persistence
→ capacity observation
→ wakeup
→ reconcile

RAG Eval must not implement a separate:

provider executor;
capacity registry;
RPM/TPM accounting path;
retry queue;
semaphore/gather dispatch pool;
in-memory work scheduler.

The production provider executor remains reachable only through the generic
prepared-dispatch execution composition.

Canonical question dataset

Every evaluated question has one of exactly three roles:

BASELINE
PROMOTION_POOL
HOLDOUT
BASELINE

Existing published possible questions are materialized as baseline questions.

They:

are evaluated through retrieval;
are never promotion candidates;
protect existing product behaviour during verification.
PROMOTION_POOL

Generated questions eligible for possible promotion are assigned to the
promotion pool.

Role membership alone does not authorize promotion. Promotion additionally
requires:

generated promotion eligibility;
low ambiguity risk;
an allowed retrieval classification;
successful adjudication;
explicit review approval.
HOLDOUT

At least two of every ten generated questions for a runtime entry are assigned
deterministically to the holdout set.

Holdout questions:

are never promoted in the same cycle;
participate in initial retrieval evaluation;
participate in post-promotion verification;
detect overfitting to promoted aliases.

Stable role assignment uses a deterministic digest, not Python's randomized
hash().

Canonical retrieval outcome

Top-k retrieval rows remain diagnostic evidence.

A separate canonical outcome is persisted for each:

run
question
evaluation stage

Supported stages include:

initial
verification_before
verification_after

The outcome contains:

expected runtime entry and fact
expected rank and score
best competitor runtime entry and fact
best competitor score
score margin
classification

The only valid classifications are:

PASS_STRONG
PASS_WEAK
CONFUSION
MISS
EXISTING_ALIAS_RETRIEVAL_FAILURE

The vocabulary:

TOP1
TOP3
TOP5
CONFUSED_WITHIN_DOCUMENT

is not a canonical domain contract and must not be introduced.

Classification is backend-owned. Frontend code must not infer it from raw
rank flags.

Adjudication gate

Retrieval failure does not automatically create a promotion candidate.

Eligible promotion-pool questions are adjudicated against:

the question;
the expected target claim;
the canonical retrieval outcome;
retrieved competitors.

The canonical verdicts are:

VALID_TARGET_QUERY
AMBIGUOUS
WRONG_EXPECTED_TARGET
UNSUPPORTED_BY_CLAIM
DUPLICATE_QUERY
OVERLAPPING_PUBLISHED_ENTRIES

A promotion candidate may be created only for VALID_TARGET_QUERY with an
affirmative promotion recommendation.

Baseline and holdout questions never become promotion candidates.

Promotion review

Promotion is an explicit stateful process.

The lifecycle distinguishes:

CANDIDATE
APPROVED
APPLYING
APPLIED
REJECTED
SUPERSEDED
REGRESSION_FAILED
ROLLED_BACK

Approval and application are separate states.

The previous ambiguous ACCEPTED state must not remain the final canonical
review/application contract.

Implementation checkpoint

The qgen, initial retrieval and adjudication portions of this decision are
implemented:

generated roles are persisted atomically;
published possible questions are materialized as BASELINE;
`RUN_RETRIEVAL_EVALUATION` uses the production `SearchPublishedWorkbenchRuntime`;
canonical initial outcomes are persisted before adjudication scheduling;
`SCHEDULE_ADJUDICATION_WORK` creates stable adjudication work items only for
eligible promotion-pool outcomes;
`PREPARE_ADJUDICATION_DISPATCH_BATCH` uses generic capacity admission and
reservation;
`EXECUTE_ADJUDICATION` uses `ExecutePreparedLlmDispatchAttempt` and strict
contract validation;
`RECONCILE_ADJUDICATION_PROGRESS` drains only after persisted adjudication
coverage;
promotion candidates are created only behind the `VALID_TARGET_QUERY` and
`promotion_recommended=true` gate;
the run transitions to `PROMOTION_REVIEW` after successful adjudication drain
or zero-eligible scheduling;
persisted promotion candidates expose their question, outcome and adjudication
linkage;
operator approval and rejection use explicit, idempotent state transitions;
review actions leave the run in `PROMOTION_REVIEW` and do not mutate retrieval
runtime entries or invoke providers.

Reversible grouped application

Approved promotions are grouped by target runtime entry.

For each affected runtime entry, the system performs:

one complete alias-set calculation
one embedding-text build
one embedding generation
one revision snapshot
one atomic runtime-entry mutation

A revision is created before or atomically with the mutation.

The revision stores:

previous aliases
new aliases
previous embedding text
new embedding text
previous embedding vector
new embedding vector
source run
source candidates
status

Only one active pending revision may exist for a runtime entry.

Post-promotion verification

Applied revisions are not immediately treated as permanently accepted.

Verification evaluates:

promoted questions;
holdout questions;
baseline aliases;
relevant neighbouring or competing surfaces.

Persisted before/after metrics include:

top-1 hit rate
top-3 hit rate
top-5 hit rate
mean expected rank
mean expected score
mean score margin
confusion count
miss count
existing-alias failure count
neighbour regression count

A regression result is persisted before any rollback action.

Operator actions remain explicit:

accept revision
rollback revision

Rollback restores in one transaction:

previous aliases
previous embedding text
previous embedding vector
Persisted progression and frontend ownership

Run status, current phase, progress and capacity-wait state are persisted by
the backend.

Public read APIs expose that persisted state.

The frontend:

does not infer workflow phase from counters;
does not infer retrieval classification from raw top-k rows;
does not use component-local state as workflow truth;
restores the complete view after reload from the backend read model;
receives live invalidation through the existing workflow-event transport.
Deployment rollback versus product revision rollback

These are different mechanisms.

Deployment rollback

If the new workflow implementation must be disabled operationally:

disable or revert the new workflow composition and handlers;
leave additive schema in place;
repair schema through forward migrations only.
Product revision rollback

If a promoted embedding revision fails verification:

use the persisted revision;
restore aliases, embedding text and embedding vector atomically;
persist the revision and promotion states as rolled back.

Deployment rollback must never be used as a substitute for product revision
rollback.

Alternatives considered
Separate RAG Eval worker and capacity registry

Rejected because it would duplicate:

admission;
reservations;
provider routing;
retry scheduling;
capacity observations;
attempt and dispatch persistence.
Synchronous evaluation

Rejected because it cannot safely support:

delayed capacity wakeups;
durable retries;
process restart recovery;
long-running progression;
persisted frontend state.
Promote every miss

Rejected because a miss can mean:

ambiguous wording;
wrong expected target;
unsupported query;
duplicate query;
overlap between published entries.

Adjudication is mandatory.

Immediate irreversible embedding mutation

Rejected because it cannot restore the prior retrieval surface after a
regression.

Automatic rollback without diagnostics

Rejected because it can erase the evidence needed to understand the regression.

Diagnostics are persisted first; accept and rollback are explicit actions.

Consequences
additive migrations are required for progression, roles, outcomes,
adjudications, candidate review actions, revisions and verification;
both LLM phases use generic execution and capacity runtime infrastructure;
retrieval outcomes become first-class persisted entities;
frontend and backend contracts evolve together;
promotion application becomes more expensive but bounded to affected runtime
entries;
every embedding mutation becomes auditable and reversible;
the implementation remains incomplete until explicit candidate approve/reject,
revisions, verification, accept/rollback and full frontend progression are
delivered and all final gates pass.
