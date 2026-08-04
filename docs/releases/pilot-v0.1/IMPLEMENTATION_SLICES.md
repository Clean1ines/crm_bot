# Pilot v0.1 Implementation Slices

Baseline: `0b1da59ab54d4ae8591da1a36f8ac50032fcd147`.

The order below follows the managed Telegram-only pilot priority after ADR-0002 and ADR-0003. S1 is intentionally broader than Redis lock wiring because owner constraints require durable Telegram intake, PostgreSQL execution ownership, and minimal state CAS before real pilot traffic.

## S1: Durable Telegram Intake and Conversation Runtime Safety

- Goal: make Telegram update intake and same-thread runtime processing durable and safe before pilot traffic.
- Requirements: FR-07, FR-08, FR-09, NFR-03, NFR-04, NFR-05.
- Risks addressed: R23 fully; R2 minimal silent-overwrite protection; main R20 durable intake/idempotency gap; R24 wiring with conditional guarantee semantics; R25 mitigated and bounded while residual external duplicate risk remains.
- ADR prerequisites: ADR-0002 durable Telegram update processing; ADR-0003 PostgreSQL-owned runtime coordination.
- Subsystems: client/manager/platform Telegram webhook intake, dedicated Telegram inbox worker, durable inbox repository, processing lifecycle, PostgreSQL thread execution lease, runtime state repository, outbound Telegram delivery intent, composition, runtime guards, Redis cache factory, operational metrics/logging.
- Expected files: Telegram webhook handlers/services, new inbox/lease/state revision repositories, `fastapi_lifespan.py`, `conversation_orchestrator.py`, graph persist/load paths, outbound Telegram adapter or side-effect contract, runtime guard wiring, focused tests.
- Migrations: required for PostgreSQL Telegram inbox identity/lifecycle/attempt metadata, PostgreSQL thread execution lease, state revision/CAS, and durable outbound intent.
- Tests first: duplicate update identity including bot account replacement; replay after restart; duplicate completed/processing/failed lifecycle preservation; differing-payload anomaly preservation; Redis down before and after durable acceptance; PostgreSQL down at webhook delivery; worker crash after claim; lease expiration recovery; same-thread concurrency; stale owner renew/release denial; state revision conflict; no Telegram response after conflict; outbound retry/ambiguous-send policy; Redis-degraded runtime limits.
- Focused validation: targeted pytest for inbox, lease, state CAS, webhook acknowledgement, outbound intent, and runtime guard degraded behavior.
- Full validation: backend quality gate plus deployed/fake Telegram smoke for supported, unsupported, handoff, duplicate, restart, Redis outage, and PostgreSQL outage cases.
- Release evidence: AT-FR-07, AT-FR-08, AT-FR-09, AT-NFR-03, AT-NFR-04, AT-NFR-05, AT-S1-01 through AT-S1-20.
- Rollback: disable Redis optimization, reduce worker concurrency, increase latency, disable optional AI features, route risky/retryable work to managers, or temporarily stop only a specific unsafe mutation operation; do not return production traffic to `NullThreadLock`.
- Non-scope: manager tenant IDOR R17, idempotent ticket close R3, analytics reset R4, web token onboarding R22, browser resolution E2E, backup/restore, full LLM provider policy.
- Dependencies: none; this is the first production-safety slice.

### S1 Work Packages

| Work Package | Goal | Input Dependencies | Non-Scope | Focused Tests | Exit Criterion | Rollback/Degraded Behavior |
|---|---|---|---|---|---|---|
| S1.1: Durable Telegram Inbox Schema and Repository | Add stable identity including Telegram surface/role, project or platform scope, persisted non-secret bot account ID or bot-generation identity, Telegram `update_id`, lifecycle, ownership, attempts, errors, uniqueness, anomaly diagnostics, and repository boundary. | ADR-0002 accepted for implementation; onboarding contract can provide persisted bot account ID/generation. | Handler refactor, thread lease, outbound send, use of token/token hash/webhook secret in identity. | Migration/repository tests for unique identity, bot replacement update ID reuse, no lifecycle reset on duplicate completed/processing/failed rows, owner fields, bounded errors, and differing-payload anomaly. | One update identity cannot create two durable inbox rows; replacement bot account avoids update ID collision; duplicate intake cannot mutate lifecycle; repository exposes claimable lifecycle. | Do not launch S1 traffic; schema can remain unused until S1.2 is ready. |
| S1.2: Webhook Intake and Inbox Worker | Make webhook thin and move processing to dedicated Telegram inbox worker for client, manager, and platform updates. | S1.1. | R17 tenant authorization, close idempotency, runtime CAS internals. | 2xx only after durable acceptance; PostgreSQL outage non-2xx/no side effects; worker claim/retry/stale recovery/restart tests. | Webhook never runs full graph/LLM runtime and worker recovers accepted updates after crash. | Disable webhook traffic or keep operator-held launch; never acknowledge without durable acceptance. |
| S1.3: PostgreSQL Thread Execution Lease | Add project/thread scoped owner-token lease with expiration, renew, release, and recovery. | S1.2 for client-message processing path. | State ownership decomposition, manager tenant R17. | Concurrent same-thread messages, stale owner renew/release denial, lease expiration recovery. | Same-thread processing cannot run concurrently without controlled defer/retry. | Reduce worker concurrency or pause unsafe thread processing; do not return to `NullThreadLock`. |
| S1.4: Runtime State Revision/CAS | Add revision load, expected-revision update, zero-row conflict, and no final response from stale processor. | S1.3. | Full state ownership decomposition and prompt-injection hardening. | Revision repository tests, graph persist conflict, no-send after conflict. | Silent stale overwrite is impossible for pilot runtime state writes. | Keep lease active, retry/defer conflicted work, route risky cases to manager. |
| S1.5: Durable Outbound Intent | Persist outbound intent, attempts, result/ambiguity, and retry policy without repeating internal mutation. | S1.2 and S1.4 for safe commit ordering. | External Telegram exactly-once guarantee. | Send failure retry, network-ambiguous send, no repeated business mutation. | Delivery attempts are auditable and residual duplicate policy is explicit. | Pause outbound worker or route to manager/operator; accepted work remains durable. |
| S1.6: Redis Runtime Guards and Degraded Mode | Wire cache factory, project limit accounting, degraded alert/metrics, and Redis-outage behavior. | S1.2 for durable intake; S1.3/S1.4 for correctness independent of Redis. | Contractual runtime-limit SLA beyond NFR-05. | Healthy Redis accounting, Redis unavailable burst, degraded metric/alert. | Redis outage does not interrupt durable intake or thread correctness; limit guarantee is marked degraded. | Disable limit guarantee, reduce worker concurrency, keep PostgreSQL intake/lease/CAS active. |
| S1.7: Integrated S1 Acceptance | Prove AT-S1-01 through AT-S1-20 with deployed/fake Telegram smoke, restart, outage, bot-replacement, duplicate-lifecycle, and anomaly scenarios. | S1.1 through S1.6. | S2 R17, S3 close idempotency, S4 onboarding, S5 ownership hardening, S7 prompt eval. | Integrated S1 acceptance suite and smoke. | Release evidence links every S1 requirement/risk/test and no planned component is described as merely wired. | Do not launch pilot; retain internal/staging-only acceptance loop. |

## S2: Tenant-Bound Telegram Manager Actions

- Goal: ensure manager Telegram actions are authorized against the target thread project.
- Requirements: FR-10, FR-11, NFR-01.
- Risks closed: R17.
- ADR prerequisites: manager action tenant binding.
- Subsystems: Telegram manager interface, `ManagerBotService`, `ManagerReplyService`, thread lifecycle repository.
- Expected files: manager bot/service/orchestration/repository tests and scoped query changes.
- Migrations: none expected.
- Tests first: project A manager cannot claim/close/reply to project B thread; Redis reply session cannot cross project.
- Focused validation: Telegram manager callback service tests.
- Full validation: security tests plus manager E2E smoke.
- Release evidence: AT-NFR-01.
- Rollback: disable Telegram manager callbacks and require web-only manager actions.
- Non-scope: idempotent close phases, web onboarding.
- Dependencies: completed S1 intake contract, at minimum S1.1 and S1.2. S2 must run through the new Telegram inbox worker path and must not build tenant authorization on the old direct synchronous manager handler.

## S3: Idempotent Ticket Close Lifecycle

- Goal: make close deterministic across web, Telegram callback, retry, and process restart.
- Requirements: FR-12, FR-15.
- Risks closed: R3, R4, R12, part of R20.
- ADR prerequisites: ticket close and resolution lifecycle.
- Subsystems: `TicketCommandService`, `ManagerReplyService`, lifecycle repository, runtime state/analytics, events.
- Expected files: close service/repository tests, analytics reset behavior, possibly thread status validation.
- Migrations: optional CHECK constraint only if included; otherwise none.
- Tests first: duplicate close produces one event/resolution outcome; analytics fields clear; status transition rejects invalid states.
- Focused validation: close lifecycle pytest set.
- Full validation: manager close E2E and regression tests.
- Release evidence: AT-FR-12.
- Rollback: feature flag or revert to previous close path with operator monitoring.
- Non-scope: browser resolution E2E, LLM provider policy.
- Dependencies: S2 for Telegram tenant safety.

## S4: Web Settings Telegram Onboarding

- Goal: make web settings token flow truthful and atomic.
- Requirements: FR-03, FR-04, NFR-02.
- Risks closed: R22.
- ADR prerequisites: Telegram onboarding lifecycle.
- Subsystems: frontend channel settings, projects API wrapper, project HTTP routes, `ProjectCommandService`, token repository, Telegram adapter.
- Expected files: channel page text/status, API/service tests, fake Telegram client tests.
- Migrations: none expected.
- Tests first: failed `setWebhook` leaves old active config; success rotates secret and marks active; credential-only mode never marks active.
- Focused validation: project token API/service tests.
- Full validation: client and manager onboarding smoke with Telegram/fake adapter.
- Release evidence: AT-FR-03, AT-FR-04, AT-NFR-02.
- Rollback: disable web token mutation or mark as credential-only.
- Non-scope: platform-admin onboarding rewrite.
- Dependencies: none; should happen before operator uses web settings for pilot bots.

## S5: Runtime State Ownership and Persistence Hardening

- Goal: decompose runtime state ownership after S1 has already added minimal revision/CAS.
- Requirements: FR-14, NFR-04, NFR-07.
- Risks closed: remaining R2 state-ownership debt, R18, part of R21.
- ADR prerequisites: ADR-0003 conversation/runtime state ownership.
- Subsystems: graph load/persist nodes, runtime state repository, ticket resolution state, analytics state, manager assignment/session state, memory/continuity reset semantics.
- Expected files: runtime state repository, graph persist/load tests, service-specific persistence contracts, prompt-state hardening tests.
- Migrations: possible JSONB path updates, state ownership fields, dedicated subdocument contracts, or additional state metadata; minimal state revision/CAS must already exist from S1.
- Tests first: each state owner updates only its owned paths; stale snapshots cannot overwrite ticket resolution/analytics/manager state; reset starts cold continuity state; prior resolutions remain client-safe data.
- Focused validation: runtime state ownership and prompt-state tests.
- Full validation: same-thread concurrency E2E from S1 plus repeat-question and prompt-injection eval.
- Release evidence: AT-FR-14, AT-NFR-04, AT-NFR-07, AT-S1-09 regression evidence.
- Rollback: keep S1 CAS/lease active, disable or revert only the new ownership decomposition path, and retain conservative retry/defer behavior.
- Non-scope: first introduction of CAS, manager tenant binding, close lifecycle phases.
- Dependencies: S1.

## S6: Resolution API and Browser E2E

- Goal: prove resolution HTTP and manager browser flows.
- Requirements: FR-13, NFR-01, NFR-10.
- Risks closed: R5, R9, R10, R15, R16.
- ADR prerequisites: ticket close/resolution lifecycle for statuses and conflict semantics.
- Subsystems: thread HTTP routes, frontend ticket detail page, generated OpenAPI, Playwright.
- Expected files: API tests, frontend E2E tests, `TicketDetailPage` draft handling, E2E script.
- Migrations: none.
- Tests first: API route auth/tenant/409; browser close/edit/conflict/regenerate failure; OpenAPI generation/diff.
- Focused validation: pytest API tests and frontend E2E target.
- Full validation: quality gate plus browser report.
- Release evidence: AT-FR-13, AT-NFR-10.
- Rollback: disable edit/regenerate UI while keeping generated resolution read-only.
- Non-scope: LLM provider capacity.
- Dependencies: S3.

## S7: LLM Timeout, Failure and Capacity Policy

- Goal: bound ticket resolution generation/regeneration and prompt reuse safety.
- Requirements: FR-08, FR-13, FR-14, NFR-06, NFR-07.
- Risks closed: R7, R8, R13, R14, R19, R21.
- ADR prerequisites: LLM completion policy; conversation/runtime state ownership for prior resolution prompt semantics.
- Subsystems: summary generator, ticket resolution service, LLM provider adapter, eval harness, prompts.
- Expected files: generator/service tests, timeout configuration, eval definitions/report.
- Migrations: optional client-safe resolution fields if ADR chooses structural split.
- Tests first: timeout/invalid JSON/quota; concurrent regenerate claims pending before LLM; adversarial prior resolution eval.
- Focused validation: LLM service tests and eval harness.
- Full validation: golden answer evaluation and close/regenerate E2E.
- Release evidence: AT-NFR-06, AT-NFR-07, golden eval report.
- Rollback: turn off regenerate and prior-resolution prompt block for pilot.
- Non-scope: switching all runtime LLM traffic to new provider architecture.
- Dependencies: S3 and S5.

## S8: Deployment, Migration, Backup and Restore Gate

- Goal: make pilot operations executable and auditable.
- Requirements: FR-01, FR-16, NFR-08, NFR-09.
- Risks closed: R6, R11.
- ADR prerequisites: migration/backup/rollback policy.
- Subsystems: Docker/deploy docs, migration runner behavior, backup/restore runbooks, smoke scripts.
- Expected files: release runbook/docs/scripts as approved; no production code unless needed by runbook.
- Migrations: none for this slice unless adding migration locks requires schema/state.
- Tests first: restore drill script/checklist; partial migration rerun simulation if in scope.
- Focused validation: runbook dry run on staging-like env.
- Full validation: restore backup into clean DB and run smoke FR-02..FR-14 subset.
- Release evidence: AT-FR-01, AT-FR-16, AT-NFR-08, AT-NFR-09.
- Rollback: promote previous artifact and restore pre-upgrade backup.
- Non-scope: Kubernetes/autoscaling.
- Dependencies: S1-S7 for full smoke.

## S9: Pilot Business Events and Minimal Analytics

- Goal: define and prove limited pilot metrics without stale analytics.
- Requirements: FR-15.
- Risks closed: remaining R4 analytics reset evidence, business-event ambiguity, and minimal client metrics accuracy.
- ADR prerequisites: business events and case identity.
- Subsystems: event names, metrics repo/API/UI, analytics reset.
- Expected files: metrics acceptance tests, docs, possible dashboard/API adjustments.
- Migrations: possible event/metric additions depending ADR.
- Tests first: known scenario counts, closed-ticket analytics reset, project isolation.
- Focused validation: metrics tests.
- Full validation: pilot metrics report after smoke.
- Release evidence: AT-FR-15.
- Rollback: hide metrics UI and provide operator-generated report only.
- Non-scope: full CRM analytics.
- Dependencies: S3 and S8.

## S10: Final Production Acceptance

- Goal: collect evidence and approve/reject pilot release.
- Requirements: all FR/NFR requirements.
- Risks closed: residual release-evidence gaps.
- ADR prerequisites: all ADRs required by previous slices accepted or explicitly deferred.
- Subsystems: docs/releases, acceptance report, operator checklist.
- Expected files: release evidence index and final acceptance notes.
- Migrations: none.
- Tests first: no new code tests; execute acceptance plan.
- Focused validation: ID consistency across release docs.
- Full validation: full quality gate, browser E2E, deployed smoke, backup/restore drill, golden eval.
- Release evidence: signed Definition of MVP Done.
- Rollback: do not launch or revert to supervised internal test.
- Non-scope: new feature work.
- Dependencies: S1-S9.

## Ordering Rationale

S1 comes first because Telegram runtime evidence is not trustworthy until update acceptance, processing ownership, same-thread execution, minimal state CAS, outbound intent, and Redis-degraded behavior are PostgreSQL-owned. S2 then secures manager tenant authorization on top of the S1 inbox worker contract and does not fix R17 inside S1. S3 makes close lifecycle idempotent. S4 follows because onboarding must be truthful before live bot connection is delegated to owners. S5 hardens state ownership beyond S1's minimal CAS; S6-S7 prove resolution and LLM quality. S8-S10 turn the implementation into an operable release.
