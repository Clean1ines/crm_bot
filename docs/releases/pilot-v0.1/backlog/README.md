# Pilot v0.1 Executable Backlog

Each file in this directory defines one independently implementable work package.

Read `PRECONDITIONS.md` before changing any S1 card to `ready`.

## Card lookup

A task ID must match exactly one filename:

```bash
find docs/releases/pilot-v0.1/backlog -maxdepth 1 -type f -name 'S1.1-*'
```

Multiple or zero matches block implementation.

## Required front matter

```yaml
id: S1.1
title: ...
status: ready_for_qa_design
release: pilot-v0.1
parent_slice: S1
baseline: 0b1da59ab54d4ae8591da1a36f8ac50032fcd147
implementation_gate: blocked_until_required_adrs_accepted
commit_policy: on_green
required_adrs: [ADR-0002]
requirements: [NFR-03]
risks: [R20]
release_acceptance: [AT-NFR-03]
dependencies: []
qa_record: docs/releases/pilot-v0.1/qa/S1.1.md
evidence_record: docs/releases/pilot-v0.1/evidence/S1.1.md
```

## Status ownership

- `ready_for_qa_design`: QA may design; code may not start.
- `qa_designed`: QA record exists; corrections may remain.
- `ready`: all ADR/dependency/QA gates permit implementation.
- `in_progress`: production patch started.
- `implemented`: patch and focused tests exist.
- `verified`: all required gates and independent acceptance passed.
- `committed`: one task-scoped commit exists.
- `blocked`: task cannot proceed; blocker must be written in the card.

## Card update rules

The implementing agent may update factual execution fields and state after evidence exists.

The agent may not independently change:

- goal;
- requirement meaning;
- accepted ADR decision;
- product scope;
- release-blocking policy;
- residual-risk acceptance policy.

Those require owner/specification/ADR action.

## One card, one commit

Each card with `commit_policy: on_green` creates at most one implementation commit. Follow-up corrections after commit require a new task or explicit corrective card.

## Index

| ID | Title | Initial status | Depends on |
|---|---|---|---|
| S1.1 | Durable Telegram Inbox Schema and Repository | ready_for_qa_design | accepted ADR-0002 |
| S1.2 | Webhook Intake and Inbox Worker | ready_for_qa_design | S1.1 |
| S1.3 | PostgreSQL Thread Execution Lease | ready_for_qa_design | S1.2 |
| S1.4 | Runtime State Revision/CAS | ready_for_qa_design | S1.3 |
| S1.5 | Durable Outbound Intent | ready_for_qa_design | S1.2, S1.4 |
| S1.6 | Redis Runtime Guards and Degraded Mode | ready_for_qa_design | S1.2, S1.3, S1.4 |
| S1.7 | Integrated S1 Acceptance | ready_for_qa_design | S1.1-S1.6 |
