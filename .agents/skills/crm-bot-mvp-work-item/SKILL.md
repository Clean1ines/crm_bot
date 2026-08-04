---
name: crm-bot-mvp-work-item
description: Execute one approved crm_bot Pilot v0.1 backlog work item from repository requirements, accepted ADRs, QA design, tests, evidence, and gated local commit.
---

# crm_bot MVP Work Item

Use this skill whenever the user names a release backlog ID or asks to execute a Pilot v0.1 backlog item.

## Purpose

Convert an approved repository work-item contract into a minimal, verified, documented, atomic implementation change.

The user prompt chooses the task. The repository defines the task.

## Required inputs

Resolve and read:

1. `AGENTS.md`;
2. `.codex/workflows/mvp-work-item.md`;
3. `docs/releases/pilot-v0.1/WORK_ITEM_EXECUTION_CONTRACT.md`;
4. the unique backlog card for the requested ID;
5. every requirement linked by the card in `MVP_SPEC.md`;
6. every acceptance test linked by the card in `ACCEPTANCE_TEST_PLAN.md`;
7. every risk linked by the card in `RISK_REGISTER.md`;
8. every ADR linked by the card;
9. the parent slice in `IMPLEMENTATION_SLICES.md`;
10. relevant rows in `TRACEABILITY_MATRIX.md`;
11. `ARCHITECTURE_BASELINE.md`;
12. the current code and existing tests in the affected execution path.

Do not rely only on summaries from prior agents.

## Authority order

When sources conflict, use this order:

1. explicit current user instruction that does not violate repository safety rules;
2. accepted ADRs;
3. approved MVP requirements and explicit release constraints;
4. acceptance criteria and risk controls;
5. the backlog card;
6. current code as evidence of actual behavior;
7. implementation plans and agent notes.

A proposed ADR is not implementation authority.

## Entry gate

Before implementation, prove:

- exactly one card matches the requested ID;
- the card is not `draft`, `blocked`, `verification_failed`, `verified`, or `committed` unless the user requested the relevant transition;
- every dependency is satisfied at the level required by the card;
- every implementation-gating ADR is accepted;
- pre-existing working-tree changes are identified and protected;
- a QA Design Record exists and its verdict permits implementation;
- the approved scope is internally consistent with current code.

If any condition fails, stop before patching and return `BLOCKED` with exact evidence.

## Freshness check

Build a table:

| Contract claim | Current code evidence | Result |
|---|---|---|
| ... | ... | valid / stale fact / decision conflict |

Handle discrepancies:

- `stale fact`: update documentation as part of the task when the approved behavior is unchanged;
- `decision conflict`: stop and require ADR/specification correction;
- `implementation gap`: continue only if it is inside the card scope.

Never rewrite the contract to match accidental current behavior.

## Impact graph

Before patching identify:

- exact symbols and files expected to change;
- direct callers and implementations of changed ports/interfaces;
- migrations and persisted data;
- worker, queue, webhook, runtime, and retry paths;
- external side effects;
- auth, tenant, secret, and input boundaries;
- frontend/OpenAPI consumers when applicable;
- existing tests and fixtures;
- code outside scope that depends on changed contracts.

If a shared contract changes, inspect every consumer. Update compatible consumers when required by the same approved contract. Do not silently expand product scope.

## QA-before-code gate

Spawn `qa_designer` read-only. Store its output at:

`docs/releases/pilot-v0.1/qa/<TASK_ID>.md`

Implementation may proceed only with verdict:

- `READY`; or
- `READY_WITH_CORRECTIONS` after all blocking corrections are incorporated.

`BLOCKED` prohibits implementation.

## Plan

The implementation plan must state:

- exact files and symbols;
- order of changes;
- tests first;
- migration and compatibility strategy;
- failure/retry semantics;
- validation commands;
- rollback/degraded behavior;
- required documentation updates;
- expected staged diff boundaries.

## Tests first

For defects, state machines, persistence, concurrency, retries, recovery, tenant isolation, and migrations, establish failing evidence before implementation whenever the environment permits it.

The failure must be for the missing behavior, not an unrelated setup error.

Never weaken, delete, skip, or broadly mock existing tests to obtain green output.

## Minimal implementation

- follow accepted ADRs;
- preserve architectural boundaries;
- avoid unrelated cleanup;
- avoid duplicate abstractions;
- preserve backward compatibility outside the approved changed contract;
- do not add permissive fallbacks that violate failure semantics;
- do not use sleeps as concurrency correctness;
- do not expose secrets;
- do not describe planned behavior as implemented before validation.

## Validation ladder

Run in this order:

1. new focused tests;
2. existing tests for directly affected components;
3. migration/repository tests when persistence changes;
4. static formatting/lint/type checks;
5. integration and worker/API tests required by the card;
6. card acceptance scenarios;
7. the repository full quality gate required for commit readiness.

Before backend validation run the repository test-env bootstrap required by `AGENTS.md`.

Record exact commands, exit results, and material limitations.

## Independent acceptance

After implementation and validation, spawn `acceptance_reviewer` read-only.

It must review actual code, diff, tests, and evidence independently. It must not accept the implementer's summary as proof.

Allowed verdicts:

- `PASS`;
- `PASS_WITH_RESIDUAL_RISKS` only when residual risks are explicitly allowed by the card and release contract;
- `FAIL`;
- `BLOCKED`.

Only `PASS`, or explicitly permitted `PASS_WITH_RESIDUAL_RISKS`, may proceed to documentation and commit gates.

## Documentation synchronization

After behavior is verified:

- update the card state and completion fields;
- update actual-state architecture documentation only for verified changes;
- update traceability, risk remediation state, acceptance evidence references, and slice progress;
- create/update the evidence record;
- preserve parent requirement state unless the full parent acceptance contract is proven.

Do not mark release acceptance from unit tests alone.

## Commit gate

A card with `commit_policy: on_green` authorizes one local commit only after:

- focused and required regression validation are green;
- acceptance reviewer passes;
- docs and evidence match actual behavior;
- `git diff --check` passes;
- the staged diff contains only task-related files;
- no secrets are present;
- all pre-existing unrelated changes remain unstaged and unmodified.

Before commit show:

- `git status --short`;
- `git diff --stat`;
- `git diff --cached --stat`;
- `git diff --cached --check`;
- staged filename list.

Use one conventional, task-scoped commit. Never push without a separate explicit instruction.

## Final response

Report:

- task ID and final task state;
- requirements, risks, ADRs, and acceptance criteria used;
- files changed;
- tests and validation results;
- QA and reviewer verdicts;
- documentation/evidence updates;
- commit SHA or why no commit was created;
- residual risks and unverified items;
- confirmation that no push occurred.
