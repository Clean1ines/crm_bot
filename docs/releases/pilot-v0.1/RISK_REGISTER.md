# Pilot v0.1 Risk Register

Severity is relative to the managed Telegram-only pilot scope.

Evidence status values: `confirmed_defect`, `confirmed_missing_behavior`, `probable_race`, `architecture_debt`, `pilot_limitation`, `not_verified`.

## Risk Summary

| Severity | Count |
|---|---:|
| P1 | 10 |
| P2 | 11 |
| P3 | 4 |

## Risks

### R2: Whole `state_json` overwrite can lose continuity

- Evidence status: probable_race.
- Severity: P1.
- Scenario: same-thread concurrent Telegram messages or retries.
- Chain: `ClientMessageService.handle_message` -> graph `load_state` -> graph `persist` -> `ThreadRuntimeStateRepository.save_state_json`; SQL `UPDATE threads SET state_json = $1 WHERE id = $2`.
- Mechanism: two processors load the same state, produce different `question_attempts` or continuity fields, and the later whole-document save erases the earlier update.
- Existing protections: ticket resolution has version CAS; service has lock port call.
- Why insufficient: production lock is `NullThreadLock`; whole runtime state save has no revision/CAS.
- Minimal fix: S1 adds minimal PostgreSQL state revision/CAS so stale whole-document saves cannot silently overwrite; S5 later decomposes state ownership and reduces broad whole-document writes.
- Acceptance test: AT-NFR-04, AT-S1-09, AT-S1-10.
- Regression risk: medium/high.
- Temporary limitation: no, if concurrent same-thread messages are possible.
- Slice: S1 for minimal CAS; S5 for ownership hardening.

### R3: Ticket close lifecycle is not one idempotent contract

- Evidence status: confirmed_defect.
- Severity: P1.
- Scenario: manager closes a ticket and close/resolution/event/analytics partially fail or duplicate.
- Chain: `TicketCommandService.close_ticket` -> `ManagerReplyService.close_thread_for_manager` -> `ThreadLifecycleRepository.close_manager_ticket` -> `TicketResolutionService.generate_after_manager_close`.
- Mechanism: close state, Redis cleanup, resolution generation, analytics reset, and events are split across services without one idempotent phase contract.
- Existing protections: happy/failure service tests.
- Why insufficient: duplicate close and partial failure release semantics are not proven.
- Minimal fix: single idempotent close use case with phases, rowcount/CAS, event semantics, retry policy.
- Acceptance test: AT-FR-12.
- Regression risk: medium.
- Temporary limitation: no for production release.
- Slice: S3.

### R4: Analytics reset after close does not clear fields

- Evidence status: confirmed_defect.
- Severity: P1.
- Scenario: closed ticket analytics leak into later metrics/state.
- Chain: `ManagerReplyService._reset_thread_analytics` -> `ThreadRuntimeStateRepository.update_analytics`; SQL uses `intent = COALESCE($1, intent)`.
- Mechanism: passing `None` preserves old values instead of clearing.
- Existing protections: none proving cleared fields.
- Why insufficient: metrics and repeat context can use stale values.
- Minimal fix: explicit reset method or sentinel clear semantics.
- Acceptance test: AT-FR-12, AT-FR-15.
- Regression risk: low/medium.
- Temporary limitation: only if pilot metrics are not shown; otherwise no.
- Slice: S3, S9.

### R5: No deployed/browser E2E for ticket resolution UI

- Evidence status: confirmed_missing_behavior.
- Severity: P1.
- Scenario: manager close/edit/regenerate breaks in browser despite service tests.
- Chain: `TicketDetailPage.tsx` -> `threadsApi` -> `src/interfaces/http/threads.py`.
- Mechanism: no committed E2E suite for ticket resolution; UI state/conflict/auth behavior unproven.
- Existing protections: service tests and generated schema sentinel.
- Why insufficient: release workflow is browser-mediated for managers.
- Minimal fix: Playwright close -> resolution -> edit -> conflict -> regenerate failure path.
- Acceptance test: AT-FR-13.
- Regression risk: low.
- Temporary limitation: no.
- Slice: S6.

### R6: Backup/restore/upgrade/rollback are not executable gates

- Evidence status: confirmed_missing_behavior.
- Severity: P1.
- Scenario: production migration or data issue cannot be safely recovered.
- Chain: `migrations/run_all.py`, README migration notes; no repo-backed backup/restore runbook found.
- Mechanism: operational recovery is not proven.
- Existing protections: migration tracking table and some migration tests.
- Why insufficient: restore drill and rollback smoke are absent.
- Minimal fix: backup/restore/upgrade/rollback runbook plus drill artifacts.
- Acceptance test: AT-FR-16, AT-NFR-09.
- Regression risk: low for docs/scripts, high operational value.
- Temporary limitation: no for production pilot.
- Slice: S8.

### R9: Resolution routes lack release-level auth/tenant/conflict tests

- Evidence status: confirmed_missing_behavior.
- Severity: P1.
- Scenario: future route shortcut bypasses manager authorization or stale-version conflict.
- Chain: `src/interfaces/http/threads.py` -> `ThreadQueryService`/`ThreadCommandService` -> runtime state repo.
- Mechanism: service protections exist, but route-level behavior and error mapping lack acceptance proof.
- Existing protections: service/dependency tests.
- Why insufficient: API is the release boundary.
- Minimal fix: route tests for manager/viewer/foreign/stale/active/pending/missing.
- Acceptance test: AT-FR-13, AT-NFR-01.
- Regression risk: low.
- Temporary limitation: no.
- Slice: S6.

### R17: Cross-project manager IDOR on Telegram manager callbacks

- Evidence status: confirmed_defect.
- Severity: P1.
- Security classification: release-blocking manager-action tenant/IDOR defect.
- Scenario: project A manager callback mutates project B thread ID.
- Chain: `WebhookDispatcher` verifies manager for webhook project -> `manager_bot.py` reads bare `reply:`/`close:` thread ID -> `ManagerBotService` -> `ManagerReplyService.claim_thread_for_manager` -> `ThreadLifecycleRepository.claim_for_manager/close_manager_ticket` updates by `threads.id`.
- Mechanism: target thread project is not bound to callback project before mutation.
- Existing protections: webhook project membership check.
- Why insufficient: membership is checked for webhook project, not target thread project.
- Minimal fix: pass webhook project ID, load target thread, verify project match and manager role, scope SQL by project.
- Acceptance test: AT-NFR-01.
- Regression risk: medium.
- Temporary limitation: no.
- Slice: S2.

### R19: Regenerate spends LLM tokens before claiming version

- Evidence status: confirmed_defect.
- Severity: P1.
- Scenario: two managers click regenerate concurrently.
- Chain: `TicketResolutionService.regenerate` -> LLM generator -> `_compare_and_update`.
- Mechanism: both calls can spend LLM time/tokens before one CAS loses.
- Existing protections: final CAS.
- Why insufficient: CAS occurs too late for cost/latency and pending UX.
- Minimal fix: claim `pending` version before LLM work.
- Acceptance test: AT-NFR-06.
- Regression risk: medium.
- Temporary limitation: possible under very controlled manager ops, but not acceptable for release.
- Slice: S7.

### R22: Web settings Telegram onboarding marks active without webhook setup

- Evidence status: confirmed_missing_behavior.
- Severity: P1.
- Scenario: owner pastes token in web settings and UI says connected, but Telegram webhook is not configured.
- Chain: `ChannelSettingsPage.tsx:59/86` -> `projects.ts:40/51` -> `projects.py:250/264` -> `ProjectCommandService.set_client_bot_token/set_manager_bot_token` -> `ProjectTokenRepository.set_bot_token/set_manager_bot_token`.
- Mechanism: token is saved, `getMe` may be used only for username, channel marked `active`, but no secret rotation or `setWebhook`.
- Existing protections: token normalization, platform-admin token rejection, encrypted persistence, inbound webhook verification when secret exists.
- Why insufficient: active status does not prove connectivity.
- Minimal fix: full atomic connection or explicit credential-only non-active state.
- Acceptance test: AT-FR-03, AT-FR-04.
- Regression risk: medium.
- Temporary limitation: possible only if operator uses platform-admin onboarding exclusively and web path is disabled/labeled non-active.
- Slice: S4.

### R23: Production thread lock is not wired

- Evidence status: confirmed_missing_behavior.
- Severity: P1.
- Scenario: any two messages for the same thread arrive before the first completes.
- Chain: `ClientMessageService.handle_message` calls `thread_lock.acquire_thread_lock`; `ConversationOrchestrator.__init__` defaults to `NullThreadLock`; `fastapi_lifespan.build_orchestrator` does not pass `thread_lock`.
- Mechanism: lock call exists but always succeeds in production composition.
- Existing protections: mock-lock unit tests; Redis lock utility exists.
- Why insufficient: not wired to production path.
- Minimal fix: implement PostgreSQL row/table-backed same-thread execution lease with owner token, expiration, atomic claim, owner-guarded renew/release, and recovery; Redis lock may remain acceleration but not authority.
- Acceptance test: AT-NFR-04, AT-S1-07, AT-S1-08.
- Regression risk: medium.
- Temporary limitation: no; rollback to `NullThreadLock` is not acceptable for real parallel pilot traffic.
- Slice: S1.

### R7: Manual regenerate LLM failure surfaces as generic 500

- Evidence status: confirmed_defect.
- Severity: P2.
- Scenario: Groq timeout/invalid JSON during manual regenerate.
- Chain: `TicketResolutionService.regenerate` -> `ResponseCompletionConversationSummaryGenerator.generate_ticket_resolution` -> HTTP global handler.
- Mechanism: automatic close failure has fallback, manual regenerate lacks controlled persisted failed state.
- Existing protections: strict parser and automatic failure handling.
- Why insufficient: manager UI receives generic failure and retry semantics are unclear.
- Minimal fix: catch generator exceptions and persist failed/retryable status.
- Acceptance test: AT-NFR-06.
- Regression risk: low/medium.
- Temporary limitation: yes with operator/manual retry for small pilot, but should be fixed.
- Slice: S7.

### R8: Direct Groq client bypasses generic capacity stack

- Evidence status: architecture_debt.
- Severity: P2.
- Scenario: close storm consumes Groq quota or hangs.
- Chain: `GroqTextCompletionClient.complete` -> summary generator -> composition root.
- Mechanism: direct provider path lacks release-proven retry/circuit/capacity policy.
- Existing protections: fake parser tests.
- Why insufficient: production capacity behavior is not bounded.
- Minimal fix: provider policy ADR and timeout/retry/circuit or generic runtime adapter.
- Acceptance test: AT-NFR-06.
- Regression risk: medium.
- Temporary limitation: yes only with low volume and operator monitoring.
- Slice: S7.

### R10: Ticket resolution CAS is brittle/unscoped at repository boundary

- Evidence status: architecture_debt.
- Severity: P2.
- Scenario: malformed version or internal wrong-project call.
- Chain: `ThreadRuntimeStateRepository.compare_and_update_ticket_resolution` uses `(state_json #>> '{ticket_resolution,version}')::int` and bare thread ID.
- Mechanism: DB cast can error and repository boundary does not carry project scope.
- Existing protections: service-level access checks and version CAS.
- Why insufficient: repo is not self-scoped.
- Minimal fix: safe cast and project-scoped update where applicable.
- Acceptance test: AT-FR-13.
- Regression risk: medium.
- Temporary limitation: yes with service-only access.
- Slice: S6.

### R11: Migration runner can leave partial drift

- Evidence status: not_verified.
- Severity: P2.
- Scenario: crash after DDL before schema marker.
- Chain: `migrations/run_all.py` executes SQL then records marker.
- Mechanism: partial apply/rerun semantics are not proven for older non-idempotent SQL.
- Existing protections: schema marker.
- Why insufficient: marker is not enough after mid-file crash.
- Minimal fix: transaction/advisory lock where possible and restore gate.
- Acceptance test: AT-FR-16.
- Regression risk: medium.
- Temporary limitation: no for upgrade gate; severity is P2 until destructive migration involved.
- Slice: S8.

### R12: Thread statuses are unconstrained free text

- Evidence status: architecture_debt.
- Severity: P2.
- Scenario: typo status hides tickets or changes runtime behavior.
- Chain: `threads.status TEXT DEFAULT 'active'`; lifecycle repository updates status.
- Mechanism: DB accepts invalid statuses.
- Existing protections: domain enum usage.
- Why insufficient: DB is source of truth and can drift.
- Minimal fix: CHECK constraint and repository validation.
- Acceptance test: AT-FR-12.
- Regression risk: medium.
- Temporary limitation: yes with application-only writes in pilot.
- Slice: S3 or post-pilot migration.

### R13: Prompt injection via prior manager resolutions not adversarially tested

- Evidence status: confirmed_missing_behavior.
- Severity: P2.
- Scenario: prior resolution contains instruction-like text.
- Chain: `ThreadReadRepository.list_recent_closed_ticket_resolutions` -> `load_state` -> prompt builder.
- Mechanism: resolution text is model-facing and not fully proven as untrusted data.
- Existing protections: same project/client scope, count/length limits, prompt wording.
- Why insufficient: no adversarial eval.
- Minimal fix: eval harness and stronger data delimiters.
- Acceptance test: AT-NFR-07.
- Regression risk: low.
- Temporary limitation: yes with manual review of resolutions.
- Slice: S7.

### R18: `/reset_dialog` leaves continuity memory

- Evidence status: confirmed_missing_behavior.
- Severity: P2.
- Scenario: admin reset test conversation, next thread inherits stale `dialog_state`.
- Chain: `ThreadCommandService.reset_dialog_by_telegram_admin` -> new thread -> `create_load_state_node` -> memory `dialog_state`.
- Mechanism: reset closes active thread but does not clear continuity-scoped memory.
- Existing protections: reset auth checks.
- Why insufficient: cold-start behavior not proven.
- Minimal fix: clear continuity-scoped memory or exclude reset/test closures.
- Acceptance test: AT-FR-14.
- Regression risk: medium.
- Temporary limitation: yes if `/reset_dialog` is operator-only and not used in production flows.
- Slice: S5/S7.

### R20: Telegram duplicate/replay handling incomplete

- Evidence status: confirmed_missing_behavior.
- Severity: P2.
- Scenario: duplicate update IDs, concurrent duplicate callbacks, Redis outage, replacement bot account reusing an old `update_id`, or duplicate delivery after processing has already moved to completed/processing/failed.
- Chain: `client_bot._is_duplicate_update` uses global `processed_update:{update_id}` exists/setex; manager/platform handlers lack same guard.
- Mechanism: non-atomic key, missing surface/project/bot-account scope, and any broad lifecycle upsert would risk resetting status, owner, lease, attempts, error, completion, payload, or outbound state on duplicate delivery.
- Existing protections: client TTL dedupe.
- Why insufficient: race, cross-project suppression, bot-replacement update ID collision, and lifecycle reset risks remain.
- Minimal fix: PostgreSQL durable Telegram inbox keyed by surface/role, project or platform scope, persisted non-secret Telegram bot account ID or bot-generation identity, and Telegram `update_id`; initial intake uses atomic INSERT semantics such as `INSERT ... ON CONFLICT DO NOTHING` then reads the existing row; duplicates never reset lifecycle, ownership, attempts, error, payload, completion, or outbound state; differing payload for the same identity records an anomaly; Redis `SET NX EX` may remain only as acceleration.
- Acceptance test: AT-NFR-03, AT-S1-01, AT-S1-02, AT-S1-03, AT-S1-11, AT-S1-16, AT-S1-17, AT-S1-18, AT-S1-19, AT-S1-20.
- Regression risk: low/medium.
- Temporary limitation: no for S1 durable intake; some downstream close idempotency remains in S3.
- Slice: S1 for durable inbox; S3 for close-specific idempotency.

### R21: Prior manager resolutions may expose manager-only content

- Evidence status: pilot_limitation.
- Severity: P2.
- Scenario: internal manager decision appears in future client prompt.
- Chain: recent resolution read -> prompt builder -> response generator.
- Mechanism: no distinct client-safe field at baseline.
- Existing protections: same project/client scope and prompt relevance rule.
- Why insufficient: client-safe boundary is not structural.
- Minimal fix: client-safe summary/visibility fields and eval.
- Acceptance test: AT-FR-14, AT-NFR-07.
- Regression risk: medium.
- Temporary limitation: yes with manager review policy for small pilot.
- Slice: S7.

### R24: Production runtime guards are not wired

- Evidence status: confirmed_missing_behavior.
- Severity: P2.
- Conditional escalation: P1 if project limits are promised as a production guarantee.
- Scenario: project settings declare `requests_per_minute` or `max_concurrent_threads`.
- Chain: `fastapi_lifespan.build_orchestrator` does not pass `cache_factory`; `ConversationOrchestrator` passes absent factory into `ProjectRuntimeGuards`; `_cache()` returns `NullCache`; `NullCache.incr/sadd/scard` do not enforce Redis-backed accounting.
- Mechanism: guard code exists but production composition does not wire Redis runtime cache.
- Existing protections: guard code fails closed on cache exceptions.
- Why insufficient: no exception is raised with `NullCache`; limits are effectively not production-backed.
- Minimal fix: inject Redis cache factory for runtime accounting or define an approved fallback; Redis outage must not stop durable intake, but project limit guarantee is degraded and operator-visible.
- Acceptance test: AT-NFR-05, AT-S1-15.
- Regression risk: medium.
- Temporary limitation: yes only if limits are not sold as guarantee and traffic is operator-controlled.
- Slice: S1.

### R25: Network-ambiguous outbound Telegram delivery can duplicate external message

- Evidence status: pilot_limitation.
- Severity: P2.
- Scenario: Telegram `sendMessage` succeeds externally but the network/client times out before the app records success, then delivery is retried.
- Chain: outbound send paths call Telegram `sendMessage`; ADR-0002 requires durable outbound intent/result but does not claim Telegram API idempotency key support.
- Mechanism: internal business processing can be effectively-once, but external Telegram delivery can be ambiguous when the provider response is lost.
- Existing protections: planned durable outbound intent and delivery result tracking; current code has direct send paths.
- Why insufficient: Telegram external exactly-once cannot be guaranteed without provider-supported idempotency.
- Minimal fix: S1 mitigates and bounds R25 by recording durable outbound intent, attempts, provider result when known, ambiguity state, retry policy, duplicate detection metadata, and operator-visible residual duplicate policy; residual external duplicate risk remains after S1.
- Acceptance test: AT-S1-13, AT-S1-14.
- Regression risk: medium.
- Temporary limitation: yes, accepted only with explicit release disclosure, release-owner acceptance based on AT-S1-13/AT-S1-14, and evidence that internal mutations are not repeated.
- Slice: S1.

### R1: Cross-channel client/thread collision

- Evidence status: architecture_debt.
- Severity: P3.
- Scenario: future website widget or other channel shares numeric `chat_id`.
- Chain: `clients` unique key `(project_id, chat_id)`; `clients.source` exists but is not part of uniqueness/upsert.
- Mechanism: future channel can reuse wrong client/thread history.
- Existing protections: Telegram-only pilot scope.
- Why insufficient: future channels would break isolation.
- Minimal fix: before enabling non-Telegram channels, migrate to `(project_id, source, chat_id)`.
- Acceptance test: future channel identity test.
- Regression risk: medium.
- Temporary limitation: yes; out of current runtime.
- Slice: post-pilot/S8 optional precondition before channels.

### R14: `target_language` unconstrained text

- Evidence status: architecture_debt.
- Severity: P3.
- Scenario: invalid language silently falls back.
- Chain: `project_settings.target_language`; `TicketResolutionService._resolve_target_language`.
- Mechanism: DB/API accept unsupported text.
- Existing protections: runtime fallback.
- Why insufficient: configuration drift is silent.
- Minimal fix: API validation and DB CHECK.
- Acceptance test: invalid language rejected.
- Regression risk: low.
- Temporary limitation: yes with operator-managed config.
- Slice: S7 or post-pilot.

### R15: `TicketDetailPage` mutates state during render

- Evidence status: confirmed_defect.
- Severity: P3.
- Scenario: background refetch wipes unsaved draft or causes React warning.
- Chain: `TicketDetailPage.tsx` render-time `setResolutionDraft`.
- Mechanism: state update during render.
- Existing protections: none.
- Why insufficient: UI polish/reliability issue.
- Minimal fix: move to effect with dirty-state handling.
- Acceptance test: component/E2E draft preservation.
- Regression risk: low.
- Temporary limitation: yes if browser E2E covers manager workflow.
- Slice: S6.

### R16: OpenAPI JSON source artifacts are ignored

- Evidence status: architecture_debt.
- Severity: P3.
- Scenario: backend/frontend schema drift.
- Chain: `.gitignore` ignores `openapi.json` and `frontend/openapi.json`; generated TS schema tracked.
- Mechanism: source schema artifact not versioned.
- Existing protections: generated schema sentinel and quality gate when run.
- Why insufficient: shape drift can bypass string sentinel.
- Minimal fix: generation/diff CI gate or tracked canonical artifacts.
- Acceptance test: AT-NFR-10.
- Regression risk: low.
- Temporary limitation: yes until S6.
- Slice: S6.
