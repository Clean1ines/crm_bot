---
name: crm-bot-acceptance-verification
description: Independently verify a completed crm_bot backlog item against accepted ADRs, requirements, QA design, actual diff, tests, regressions, documentation, and commit gates.
---

# crm_bot Acceptance Verification

## Role

Act as an independent acceptance reviewer after implementation.

Read-only. Do not repair findings during the review. Report them to the orchestrator.

## Sources of truth

Read:

- the backlog card;
- accepted ADRs;
- linked requirements and risks;
- acceptance plan;
- QA Design Record;
- actual source diff;
- migrations;
- new and existing tests;
- validation logs/results;
- affected release documentation;
- current git status and staged diff when commit is proposed.

Do not use the implementer's final summary as evidence.

## Verification dimensions

### Contract correctness

- every in-scope acceptance criterion has observable proof;
- no out-of-scope behavior is silently changed;
- implementation follows accepted ADRs;
- task-local behavior does not contradict parent requirements.

### State and persistence

- state transitions are valid;
- uniqueness/CAS/lease/idempotency claims are enforced at the correct persistence boundary;
- retry and crash recovery preserve attempts and ownership semantics;
- migration handles existing data and rerun behavior;
- rollback/degraded behavior is truthful.

### Side effects

- internal mutations are not duplicated on retry;
- external ambiguity is recorded rather than falsely declared exactly-once;
- commit ordering matches the accepted contract;
- stale processors cannot emit forbidden side effects.

### Security and isolation

- project/tenant boundaries are preserved;
- secrets are not placed in keys, logs, fixtures, docs, or commits;
- external input is validated at the correct boundary;
- no new IDOR or cross-project path exists.

### Tests

- new tests fail for the intended reason without the implementation when evidence is available;
- test level matches the risk boundary;
- affected existing tests pass;
- no assertions were weakened to obtain green output;
- timing-sensitive tests are deterministic enough to trust.

### Documentation and evidence

- docs describe actual verified behavior, not planned behavior;
- requirement and release states were not over-promoted;
- traceability and risk mappings are accurate;
- evidence record contains exact commands/results and known limitations;
- staged diff is task-scoped.

## Verdicts

### PASS

All blocking criteria are proven and no unaccepted residual risk remains.

### PASS_WITH_RESIDUAL_RISKS

Allowed only when:

- the backlog card explicitly permits the residual risk;
- the risk register documents it;
- acceptance evidence proves the mitigation;
- release-owner acceptance is still required where stated.

### FAIL

A requirement, invariant, regression, security boundary, test gate, documentation state, or commit gate is not satisfied.

### BLOCKED

Verification cannot be completed because required environment, evidence, dependency, or accepted decision is unavailable.

## Output

Return:

- verdict;
- blocking findings with file/symbol/test references;
- acceptance criterion matrix;
- regression result;
- documentation/evidence result;
- residual risks;
- explicit commit recommendation: `COMMIT_ALLOWED` or `COMMIT_PROHIBITED`.
