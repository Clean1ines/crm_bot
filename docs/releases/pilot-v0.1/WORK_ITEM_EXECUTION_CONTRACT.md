# Pilot v0.1 Work-Item Execution Contract

## Purpose

This document defines how an agent converts one Pilot backlog item into verified repository changes.

It is mandatory for both human-guided and autonomous Codex implementation.

## Authority hierarchy

1. Explicit current owner instruction.
2. Accepted ADRs.
3. MVP requirements and release constraints.
4. Acceptance criteria and risk controls.
5. Backlog card.
6. Current code as evidence of actual behavior.
7. QA, planning, and implementation notes.

Current code does not silently override an approved requirement. A proposed ADR does not authorize implementation.

## Artifact model

### Release artifacts

- `MVP_SPEC.md`: requirement contract.
- `ACCEPTANCE_TEST_PLAN.md`: release evidence contract.
- `ARCHITECTURE_BASELINE.md`: actual versus target architecture.
- `TRACEABILITY_MATRIX.md`: requirement-to-code/test/release mapping.
- `RISK_REGISTER.md`: known risks and remediation ownership.
- `IMPLEMENTATION_SLICES.md`: release ordering and parent slices.
- accepted ADRs: architecture decisions.

### Work-item artifacts

- `backlog/<ID>-*.md`: direct task contract.
- `qa/<ID>.md`: pre-implementation QA Design Record.
- `evidence/<ID>.md`: post-verification evidence.

## State models

### Backlog item state

```text
draft
ready_for_qa_design
qa_designed
ready
in_progress
implemented
verification_failed
verified
committed
blocked
```

Allowed normal transitions:

```text
draft -> ready_for_qa_design
ready_for_qa_design -> qa_designed | blocked
qa_designed -> ready | blocked
ready -> in_progress
in_progress -> implemented | blocked
implemented -> verified | verification_failed
verification_failed -> in_progress | blocked
verified -> committed
```

A committed task is immutable except through a new backlog item or explicit corrective task.

### Requirement state

```text
missing
partial
implemented_not_release_verified
implemented_and_verified
out_of_scope
```

Task completion does not automatically promote a requirement.

### QA verdict

```text
READY
READY_WITH_CORRECTIONS
BLOCKED
```

### Acceptance verdict

```text
PASS
PASS_WITH_RESIDUAL_RISKS
FAIL
BLOCKED
```

## Definition of ready for implementation

A task is `ready` only when:

- required ADRs are accepted;
- dependencies satisfy the card;
- QA Design Record permits implementation;
- card scope and acceptance criteria are internally consistent;
- current-code freshness review has no unresolved decision conflict;
- migration/rollback requirements are defined where applicable;
- required test levels are identified.

## Definition of implemented

A task is `implemented` when code and task-focused tests exist, but acceptance review and full required validation may still be pending.

## Definition of verified

A task is `verified` only when:

- focused tests pass;
- affected regressions pass;
- required static/integration/full gates pass;
- stack/security review has no blockers;
- acceptance reviewer permits commit;
- documentation and evidence reflect actual behavior;
- residual risks are explicitly allowed.

## Scope expansion rule

A change outside the nominal card is allowed only when it is required to preserve a shared contract changed by the card.

The agent must:

1. identify the dependency;
2. explain why compatibility cannot be preserved locally;
3. include the dependent code in impact analysis and tests;
4. avoid adding unrelated product behavior.

If the expansion changes requirement meaning, architecture, security posture, persistence authority, or release scope, stop for owner/ADR resolution.

## Documentation freshness rule

- Correct stale factual descriptions when accepted behavior is unchanged.
- Do not describe target behavior as current before verification.
- Do not rewrite acceptance criteria to match implementation shortcomings.
- Update parent requirement status only with complete parent evidence.

## Commit policy

`commit_policy: on_green` is repository-level authorization for one local commit after all gates.

It never authorizes push.

A commit is prohibited when any required validation, QA, acceptance, documentation, scope, secret, or staged-diff gate fails.

## Evidence integrity

Every evidence claim must include an exact command, artifact, test name, database assertion, trace, screenshot, or manual runbook result.

“Reviewed”, “looks correct”, and agent summaries are not release evidence by themselves.
