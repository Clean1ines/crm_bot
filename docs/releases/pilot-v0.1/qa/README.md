# Pilot v0.1 QA Design Records

A QA Design Record is mandatory before production implementation for every backlog work item.

The record is owned by the read-only `qa_designer` role and reviewed by the orchestrating agent.

## Naming

```text
docs/releases/pilot-v0.1/qa/<TASK_ID>.md
```

## Verdict meaning

- `READY`: task is testable and implementation may proceed when all other gates pass.
- `READY_WITH_CORRECTIONS`: local explicit corrections must be incorporated before code.
- `BLOCKED`: implementation is prohibited pending owner/ADR/dependency/evidence resolution.

## Independence

QA must read requirements and current code independently. It must not merely convert the implementation plan into tests.
