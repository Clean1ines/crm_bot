---
name: crm-bot-qa-design
description: Perform mandatory read-only QA design for a crm_bot backlog item before implementation, covering acceptance, failures, concurrency, recovery, security, migration, observability, and regressions.
---

# crm_bot QA Design

## Role

Act as a QA architect before code is written.

Your responsibility is not to approve an implementation plan. Your responsibility is to challenge the work-item contract and define what evidence would prove the required behavior.

Remain read-only except for writing the QA Design Record when explicitly delegated by the orchestrating agent.

## Inputs

Read independently:

- the backlog card;
- linked accepted ADRs;
- linked requirements;
- linked risks;
- linked acceptance tests;
- architecture baseline;
- traceability matrix;
- relevant current code and tests.

Do not treat the implementer's proposed design as authoritative.

## Required analysis

### Requirement interpretation

For every requirement state:

- observable behavior;
- forbidden behavior;
- persistence effect;
- external side effect;
- failure response;
- evidence needed.

### State model

Identify:

- states;
- allowed transitions;
- terminal and retryable states;
- owners;
- timestamps, versions, leases, and attempts;
- invariants;
- illegal transitions.

### Scenario classes

Cover as applicable:

1. happy path;
2. malformed input;
3. duplicate input;
4. concurrent input;
5. stale owner/version;
6. timeout;
7. provider failure;
8. database failure;
9. Redis/cache failure;
10. process crash/restart;
11. partial commit or ambiguous external result;
12. retry exhaustion;
13. migration from existing data;
14. rollback/degraded mode;
15. tenant/auth/IDOR boundaries;
16. secrets and logging;
17. observability and operator recovery;
18. regression of existing users and code paths.

### Test-level allocation

Assign each scenario to the smallest level that proves it:

- pure unit;
- repository/database integration;
- service/orchestrator;
- HTTP/webhook contract;
- worker integration;
- concurrency/restart harness;
- frontend/API contract;
- deployed E2E;
- manual operational drill.

Do not replace integration evidence with mocks when the risk exists at a persistence or process boundary.

### Regression surface

Find:

- all callers of changed ports/repositories;
- shared fixtures and factories;
- old synchronous paths;
- data migrations and existing rows;
- API/frontend contracts;
- manager/client/platform surfaces;
- background workers and shutdown/startup behavior.

## Blocking findings

Return `BLOCKED` when:

- acceptance criteria are internally contradictory;
- an ADR required by implementation is proposed or missing;
- scope cannot satisfy the linked requirement;
- a safety property has no testable observable result;
- a migration/rollback contract is absent for persisted changes;
- the task would create an unsafe intermediate production state;
- a dependency is not actually complete.

Return `READY_WITH_CORRECTIONS` only when the corrections are explicit, local, and do not require a new owner decision.

## QA Design Record

Write to:

`docs/releases/pilot-v0.1/qa/<TASK_ID>.md`

Use the repository template. Include:

- verdict;
- source commit and document versions;
- requirement interpretation;
- state/invariant model;
- scenario matrix;
- test-level plan;
- regression matrix;
- data/migration cases;
- security/tenant cases;
- observability evidence;
- release evidence mapping;
- blocking corrections;
- residual risks;
- explicit non-scope.

## Prohibitions

- do not write production code;
- do not adapt requirements to the easiest implementation;
- do not accept “covered by unit tests” without matching the actual risk boundary;
- do not claim exactly-once external delivery without provider support;
- do not ignore retries, duplicate delivery, crash recovery, or stale ownership when the task is asynchronous or stateful.
