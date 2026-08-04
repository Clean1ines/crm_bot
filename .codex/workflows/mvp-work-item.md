# crm_bot Pilot MVP Work-Item Workflow

Use for every implementation request that names a Pilot backlog ID.

## Non-negotiable outcome

One backlog item may produce one local commit only after all gates are green. Never push without a separate explicit instruction.

## Phase 0 — Resolve task and protect working tree

1. Read `AGENTS.md` and the three crm_bot work-item skills.
2. Run:

```bash
pwd
git branch --show-current
git rev-parse HEAD
git status --short
git diff --stat
```

3. Resolve exactly one card in `docs/releases/pilot-v0.1/backlog/`.
4. Record pre-existing modified/untracked files.
5. Never reset, clean, checkout, stash, overwrite, stage, or commit unrelated existing work.
6. If pre-existing changes overlap required task files, inspect and preserve them; block when ownership cannot be separated safely.

## Phase 1 — Load execution contract

Read:

- `WORK_ITEM_EXECUTION_CONTRACT.md`;
- backlog README and card;
- linked accepted ADRs;
- MVP requirements;
- acceptance tests;
- risks;
- parent slice;
- traceability rows;
- architecture baseline;
- relevant code and existing tests.

Produce a compact contract digest:

- goal;
- in scope;
- out of scope;
- required behavior;
- prohibited behavior;
- dependencies;
- required tests/evidence;
- commit policy.

## Phase 2 — Freshness and architecture gate

Perform targeted read-only recon.

Build:

1. document-vs-code freshness table;
2. affected symbols/files;
3. caller/consumer map;
4. persistence/migration impact;
5. external-side-effect map;
6. security/tenant boundary map;
7. validation gate list.

If the task changes an unaccepted architecture decision, public contract, tenant model, persistence authority, queue/runtime semantics, or acceptance strategy, stop and route to docs/ADR workflow.

## Phase 3 — Mandatory QA design

Spawn `qa_designer` read-only.

Input it the task ID and require independent reading of all sources.

Write or update:

`docs/releases/pilot-v0.1/qa/<TASK_ID>.md`

Gate:

- `READY`: continue;
- `READY_WITH_CORRECTIONS`: apply corrections to task/docs, then recheck;
- `BLOCKED`: stop with no production patch.

## Phase 4 — Implementation plan

Use planner/architect and stack-specific reviewers as required by `AGENTS.md`.

Plan must include:

- files and symbols;
- order;
- tests first;
- compatibility and migration;
- failure/retry behavior;
- rollback/degraded behavior;
- documentation/evidence changes;
- full validation commands.

Do not start patching until the plan covers every blocking QA scenario owned by this work item.

## Phase 5 — Establish failing evidence

Add or identify focused tests that prove the missing behavior.

Run them before implementation when practical. Record:

- command;
- expected failure;
- actual failure;
- why the failure is the required missing behavior.

Setup failures are not red-phase evidence.

## Phase 6 — Minimal patch

Use implementer only after all prior gates.

Rules:

- minimal approved scope;
- preserve architecture boundaries;
- inspect all consumers of changed shared contracts;
- update dependent code only when required for compatibility;
- no unrelated refactor;
- no test weakening;
- no secret logging;
- no undocumented fail-open behavior;
- no production traffic intermediate state that violates the task card.

## Phase 7 — Validation ladder

Run:

1. focused new tests;
2. directly affected regression tests;
3. persistence/migration tests;
4. test environment bootstrap required by `AGENTS.md`;
5. ruff format/check;
6. mypy;
7. broader pytest required by impact map;
8. frontend checks when affected;
9. full project quality gate for commit readiness;
10. task acceptance scenarios possible in the current environment.

Record every command and result for evidence. Never summarize a command as passed if it was not run.

## Phase 8 — Stack and security review

Run relevant read-only reviewers:

- architect when boundaries changed;
- database reviewer for schema/SQL/lease/CAS;
- Python/TypeScript reviewer for changed stack;
- security reviewer for external input, tenant/auth, secrets, webhook, or provider paths;
- generic reviewer for final diff.

Resolve blocking findings and re-run affected validation.

## Phase 9 — Independent acceptance

Spawn `acceptance_reviewer` read-only.

It must independently inspect actual implementation and return a verdict plus commit recommendation.

Do not proceed on `FAIL`, `BLOCKED`, or `COMMIT_PROHIBITED`.

## Phase 10 — Synchronize documentation and evidence

Only after verified behavior:

1. update backlog card fields and state;
2. update factual architecture baseline;
3. update traceability and risk remediation state;
4. update acceptance references/evidence status;
5. avoid over-promoting parent requirements or release state;
6. create `docs/releases/pilot-v0.1/evidence/<TASK_ID>.md` from template;
7. set `result_commit: SELF` before the single commit.

Re-run documentation consistency and `git diff --check`.

## Phase 11 — Stage and commit gate

Only when card says `commit_policy: on_green` and every gate passed:

1. stage only task-related files explicitly;
2. inspect:

```bash
git status --short
git diff --cached --name-only
git diff --cached --stat
git diff --cached --check
git diff --cached
```

3. verify no unrelated file or secret is staged;
4. create one conventional task-scoped commit;
5. capture commit SHA;
6. do not push.

If the environment or policy prevents commit, leave a cleanly reviewable unstaged/staged patch and report why.

## Phase 12 — Final response

Include:

- task ID and state;
- baseline and result commit;
- requirements/risks/ADRs;
- changed files;
- tests and exact results;
- reviewer verdicts;
- docs/evidence updates;
- residual risks;
- unverified items;
- confirmation of no push.
