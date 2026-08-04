# Pilot v0.1 MVP Specification

Baseline: branch `rescue/0d59-projection-cutover`, commit `0b1da59ab54d4ae8591da1a36f8ac50032fcd147`.

This is a documentation-only release package. It records what can be approved for a managed production pilot and what must still be proven or fixed before release.

## Pilot Goal

Run a managed Telegram-only production pilot for one client on isolated infrastructure. The pilot must prove that Axole can ingest client knowledge, publish a reviewed retrieval surface, answer supported Telegram questions, escalate unsupported or risky questions to managers, close manager-handled tickets, generate a client-safe ticket resolution, and reuse relevant previous resolutions in later conversations.

## Target Buyer And Users

- Buyer: service business, online school, consultant, expert business, support team, or AI automation agency that needs a controlled Telegram support assistant.
- Owner/admin: configures project, uploads and publishes knowledge, connects Telegram bots, reviews pilot health.
- Manager: claims escalated tickets, replies to clients, closes tickets, reviews or edits ticket resolutions.
- Client: asks questions through the client Telegram bot.
- Operator: deploys, configures infrastructure, performs backup/restore, monitors health, and supports rollback.

## Fixed Pilot Scope

- Managed deployment with operator support.
- Separate client infrastructure.
- Telegram-only runtime.
- Client Telegram bot.
- Manager Telegram bot.
- Web panel for owners and managers.
- Knowledge upload, validation, curation, and publication.
- AI answers from published knowledge.
- Manager handoff, claim, reply, and close.
- Ticket resolution generation/edit/regenerate.
- Reuse of relevant client-safe past ticket resolutions.
- Limited client metrics.
- Backup, restore, upgrade, rollback, and smoke-test runbooks.

## Non-Scope

- Website widget.
- WhatsApp, Instagram, and email.
- SaaS billing.
- Self-service deployment without an operator.
- Kubernetes and autoscaling.
- Full CRM replacement.
- Universal integrations.
- OCR as a guaranteed capability.
- Automatic legal, financial, contractual, or binding business decisions.

## Roles

| Role | Capabilities In Pilot | State |
|---|---|---|
| Client | Ask Telegram questions and receive AI or manager replies. | implemented_not_release_verified |
| Manager | Receive handoff, claim, reply, close, and review resolution in web/Telegram surfaces. | partial |
| Owner/admin | Manage project, knowledge, channels, and team. | partial |
| Operator | Deploy, migrate, configure bots, back up, restore, and run smoke checks. | missing |

## Requirement State Vocabulary

- `implemented_and_verified`: implemented and release-evidence exists for this pilot.
- `implemented_not_release_verified`: implemented but lacks release-level E2E, deployment, or acceptance evidence.
- `partial`: part of the flow exists, but a blocker or missing contract prevents release-ready status.
- `missing`: no sufficient repo-backed implementation/runbook/test evidence.
- `out_of_scope`: explicitly not part of this pilot.

## Functional Requirements

| ID | Requirement | Acceptance Criterion | State | Release Status |
|---|---|---|---|---|
| FR-01 | Clean deployment starts API, worker/runtime components, Postgres, Redis, and migrations for isolated client infrastructure. | Operator can deploy from this commit, run migrations once, verify health/readiness, and execute smoke FR-02 through FR-12. | partial | blocked_by S8 |
| FR-02 | Owner/admin can create or select a project for the pilot. | Project exists with owner/admin membership and project settings visible in web panel. | implemented_not_release_verified | advisory until E2E |
| FR-03 | Client Telegram bot can be connected for a project. | Token is verified, webhook secret is generated/rotated, Telegram `setWebhook` succeeds, inbound webhook secret verification passes, and channel status reflects real connectivity. | partial | blocked_by R22/S4 |
| FR-04 | Manager Telegram bot can be connected for a project. | Manager bot token is verified, manager webhook secret is generated/rotated, `setWebhook` succeeds, inbound verification passes, channel connectivity is proven, and initial manager identity registration is complete when required by the onboarding path. | partial | blocked_by R22/S4 |
| FR-05 | Owner/admin can upload a supported knowledge document. | Upload creates source document/workflow state and exposes reviewable units without claiming unsupported OCR guarantees. | implemented_not_release_verified | needs acceptance |
| FR-06 | Knowledge can be processed, reviewed, and published to the production retrieval surface. | Reviewed entries are grounded in evidence and become retrievable by the runtime. | implemented_not_release_verified | needs deployed smoke |
| FR-07 | Client receives AI answer for supported Telegram question using published knowledge. | Telegram question with published support evidence returns grounded answer and persists message/state/events only after durable PostgreSQL update acceptance, DB thread lease, and minimal state revision/CAS are in place. | partial | blocked_by R23,R2,R20/S1 |
| FR-08 | Unsupported or risky question is handled safely. | Runtime does not invent unsupported answer and either provides safe unsupported copy or escalates to manager after durable acceptance; LLM/provider failure does not stop Telegram intake. | partial | blocked_by R20,R23/S1 and golden eval/S7 |
| FR-09 | Client question can be handed off to manager. | Handoff creates waiting/manual ticket from durable processing, notifies manager surface, and does not duplicate irreversible side effects on retry. | partial | blocked_by R20,R23/S1 |
| FR-10 | Manager can claim a ticket. | Web and Telegram claim paths authorize manager for target project/thread and record assignment once. | partial | blocked_by R17/S2 |
| FR-11 | Manager can reply to client. | Reply is persisted and delivered through client Telegram bot; Telegram reply session is bound to project/thread. | partial | blocked_by R17/S2 |
| FR-12 | Manager can close a ticket. | Close is idempotent, clears manager/session/analytics correctly, persists event, and tolerates duplicate callbacks. | partial | blocked_by R3,R4/S3 |
| FR-13 | Ticket resolution is generated, viewed, edited, and regenerated. | Closed ticket has `pending -> generated|failed|missing` resolution lifecycle, route-level tenant checks, 409 conflict handling, and browser E2E evidence. | partial | blocked_by R5,R7,R9,R19/S6,S7 |
| FR-14 | Relevant client-safe past resolution can help answer a later related question. | New same-client thread loads only relevant generated/edited client-safe prior resolution as data, not instruction; S1 prevents lost state and S5 hardens ownership. | partial | blocked_by R2/S1,R13,R21/S5,S7 |
| FR-15 | Pilot exposes limited client metrics. | Owner/admin can obtain agreed minimal metrics after close without stale analytics leakage and with clear business-event semantics. | partial | blocked_by R4/S3,S9 |
| FR-16 | Operator can back up, restore, upgrade, and rollback the pilot. | Backup restore drill succeeds on clean DB; migration upgrade and rollback decision points are documented and smoke-tested. | missing | blocked_by R6,R11/S8 |

## Nonfunctional Requirements

| ID | Requirement | Acceptance Criterion | State | Release Status |
|---|---|---|---|---|
| NFR-01 | Tenant isolation and IDOR resistance. | All HTTP and Telegram manager actions mutate only threads belonging to the authorized target project. | partial | blocked_by R17/S2 |
| NFR-02 | Telegram webhook authenticity. | Inbound webhooks require valid Telegram secret token for client and manager surfaces. | implemented_not_release_verified | needs E2E evidence |
| NFR-03 | Telegram idempotency. | Duplicate client, manager, and platform-admin Telegram updates are durably accepted once in PostgreSQL and do not repeat irreversible business side effects; external Telegram `sendMessage` exactly-once is not promised. | partial | blocked_by R20/S1; residual R25 requires explicit disclosure and release acceptance |
| NFR-04 | Same-thread concurrency safety. | Two messages for the same thread arriving before the first completes are coordinated by PostgreSQL thread execution lease and minimal state revision/CAS; stale processors do not send final Telegram responses. | partial | blocked_by R2,R23/S1 |
| NFR-05 | Runtime project limits. | `requests_per_minute` and `max_concurrent_threads` are enforced through Redis-backed accounting or an approved fallback; Redis outage degrades limit guarantees but does not stop durable Telegram intake. | partial | blocked_by R24/S1 |
| NFR-06 | LLM timeout/failure handling. | Ticket resolution generation/regeneration returns bounded controlled outcomes under timeout/quota/invalid JSON. | partial | blocked_by R7,R8,R19/S7 |
| NFR-07 | Prompt-injection resistance for reused resolutions. | Past manager resolutions are treated as untrusted data and adversarial evals pass. | partial | blocked_by R13,R21/S7 |
| NFR-08 | Deployment reproducibility. | Release artifact, env contract, migration command, and smoke command are documented and repeatable. | missing | blocked_by R6/S8 |
| NFR-09 | Backup/restore and rollback readiness. | Restore from backup and post-restore smoke pass before pilot traffic. | missing | blocked_by R6,R11/S8 |
| NFR-10 | OpenAPI/frontend contract integrity. | API schema and frontend generated client drift fail CI or release gate. | partial | blocked_by R16/S6 |

## User Scenarios

1. Operator deploys isolated pilot infrastructure and verifies readiness.
2. Owner creates project and connects client/manager Telegram bots.
3. Owner uploads, reviews, and publishes knowledge.
4. Client asks supported question and receives grounded AI answer.
5. Client asks unsupported question and receives safe handling or escalation.
6. Manager claims, replies, and closes ticket.
7. System generates ticket resolution; manager edits or regenerates when needed.
8. Same client asks a related question later; AI can use relevant client-safe prior resolution.
9. Owner reviews limited pilot metrics.
10. Operator performs backup, restore, upgrade, rollback, and final acceptance checks.

## Critical Invariants

- A manager Telegram callback must be authorized against the project of the target thread, not only the webhook bot project.
- A channel must not be reported as active unless its configured path can receive verified Telegram webhook traffic.
- Telegram update acceptance is durable only after PostgreSQL inbox persistence; if PostgreSQL is unavailable, no business side effects run and Telegram receives a retriable non-2xx.
- Redis outage must not stop Telegram intake when PostgreSQL is available; Redis is acceleration/accounting, not the authoritative inbox or execution owner.
- Same-thread processing requires PostgreSQL execution lease before production pilot traffic.
- Runtime state persistence requires DB-level revision/CAS in S1; Redis lock alone is not sufficient.
- Two concurrent messages for one thread must not both write stale whole `state_json` snapshots or emit two final responses.
- Ticket close must be idempotent across HTTP, Telegram callback, retry, and process restart.
- Prior ticket resolution context injected into prompts must be client-safe data, not instructions.
- Outbound Telegram delivery is best-effort around durable intent; external exactly-once `sendMessage` is not guaranteed by this release contract.
- Internal business processing is effectively-once logical processing.
- Pilot metrics must not reuse stale analytics fields after ticket close.
- Backup and restore must be proven before real pilot traffic.

## Release Blockers

- R17: Manager Telegram callback tenant binding is not scoped to target thread project.
- R22: Web settings bot-token paths can mark channels active without webhook setup.
- R23: Production thread lock is not wired.
- R2/R20: Telegram updates and runtime state need PostgreSQL durable inbox, DB thread lease, and minimal state revision/CAS in S1 before pilot release.
- R3/R4: Ticket close lifecycle and analytics reset are not release-ready.
- R5/R9/R19: Resolution API/browser E2E release evidence and regenerate version-claim order are not release-ready.
- R6/R11: Backup/restore/upgrade/rollback are not executable release gates.

## Constraints And Explicit Limitations

- This pilot is Telegram-only; website widget and future channels remain out of scope.
- Cross-channel `(project_id, chat_id)` collision is architecture debt before future channel enablement, not a current Telegram-only runtime blocker.
- Runtime guard R24 may be accepted only as a controlled-pilot limitation if project limits are not promised as production guarantees.
- Redis outage can degrade throughput, wakeups, and runtime-limit accounting, but must not be treated as accepted update loss.
- PostgreSQL outage means Telegram updates are not durably accepted and must receive retriable non-2xx.
- Generated ticket resolutions are assistant summaries, not legal, financial, contractual, or binding decisions.
- OCR is not guaranteed.

## Definition Of MVP Done

MVP is done when:

- All `release-blocking` acceptance tests in `ACCEPTANCE_TEST_PLAN.md` pass in the pilot environment.
- Every P1 risk in `RISK_REGISTER.md` is remediated or explicitly downgraded by evidence accepted by release owner.
- Slices S1 through S10 in `IMPLEMENTATION_SLICES.md` have release evidence or documented non-applicability.
- Traceability matrix has no release-blocking requirement without entrypoint, owner, persistence, test evidence, and release status.
- Operator runbooks for deployment, migration, backup, restore, upgrade, rollback, and smoke are approved.
- ADR-0002 and ADR-0003, plus other proposed ADRs that gate slices, are accepted before those slices are released.
- S1 release evidence proves PostgreSQL durable inbox, PostgreSQL thread execution lease, minimal state revision/CAS, Redis-degraded behavior, and no rollback to `NullThreadLock`.
