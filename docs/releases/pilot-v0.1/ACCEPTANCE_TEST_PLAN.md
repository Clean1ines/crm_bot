# Pilot v0.1 Acceptance Test Plan

Baseline: `0b1da59ab54d4ae8591da1a36f8ac50032fcd147`.

This plan defines release evidence. Existing unit or service tests are useful only when paired with the stated acceptance proof.

## Test Matrix

| Acceptance Test ID | Req ID | Preconditions | Data | Steps | Expected Result | Level | Mode | Blocking | Environment | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| AT-FR-01 | FR-01 | Clean isolated infra available. | Empty DB, Redis, env from approved runbook. | Deploy, run migrations, start API/worker, call health/readiness, run smoke setup. | App starts reproducibly; migrations applied once; smoke can proceed. | deploy/smoke | manual+automated | release-blocking | staging-like pilot env | deployment log, migration log, smoke log |
| AT-FR-02 | FR-02 | Auth configured. | Owner/admin account. | Login, create/select project, verify membership/settings. | Project exists and is manageable by owner/admin only. | browser/API | automated preferred | advisory | pilot env | browser trace/API response |
| AT-FR-03 | FR-03 | Project exists; public URL configured. | Client bot token. | From web settings, save token; verify selected contract: full connection or credential-only. If full: assert `getMe`, secret rotation, `setWebhook`, inbound secret verification. | Channel active only after real webhook setup; failure keeps old state. | API+Telegram fake/live smoke | automated+manual | release-blocking | pilot env with Telegram or fake adapter | API test, Telegram webhook proof |
| AT-FR-04 | FR-04 | Project exists; manager operator known. | Manager bot token and manager chat identity if required. | Connect manager bot; verify token, secret rotation, `setWebhook`, inbound secret verification, channel connectivity, and initial manager identity registration when the onboarding path requires it. | Manager bot channel is genuinely connected for the project; target-thread authorization is verified separately by FR-10/FR-11/NFR-01. | API+Telegram | automated+manual | release-blocking | pilot env | webhook proof, manager bot connectivity log |
| AT-FR-05 | FR-05 | Project exists. | Supported `.pdf/.docx/.txt` per pilot policy. | Upload document; observe processing state. | Source document/workflow state created; unsupported file policy is safe. | API/browser | automated preferred | release-blocking | pilot env | upload response, workflow state |
| AT-FR-06 | FR-06 | Uploaded document processed. | Curated entries with source evidence. | Review, approve, publish; run retrieval preview. | Published retrieval surface answers known queries from evidence. | API/browser+RAG smoke | automated+manual | release-blocking | pilot env | curation proof, retrieval smoke |
| AT-FR-07 | FR-07 | Client bot connected; knowledge published; S1 safety contract implemented. | Supported client question. | Send Telegram message through durable Telegram intake. | Update is durably accepted before 2xx; client receives grounded AI answer only after state/messages/events and outbound intent are committed. | deployed E2E | automated+manual | release-blocking | pilot env | Telegram transcript, inbox row, DB/event snapshot |
| AT-FR-08 | FR-08 | Client bot connected; S1 durable intake implemented. | Unsupported/risky question and LLM/provider timeout case. | Send Telegram message, then force unsupported/timeout path. | Accepted update is not lost; assistant does not invent answer; controlled fallback, retryable failure, or handoff occurs. | deployed E2E+eval | automated+manual | release-blocking | pilot env | transcript, inbox state, eval result |
| AT-FR-09 | FR-09 | Unsupported/handoff scenario active; S1 durable processing implemented. | Client question requiring manager. | Trigger handoff, replay update, inspect manager notification and ticket state. | One waiting/manual ticket is created from durable processing; manager surface is notified without duplicate irreversible side effects. | E2E/API | automated | release-blocking | pilot env | inbox/event/ticket snapshot |
| AT-FR-10 | FR-10 | Waiting ticket; authorized manager. | Manager identity and thread ID. | Claim via web and Telegram callback. | Only target-project manager can claim; duplicate claim is stable. | security/API/Telegram | automated | release-blocking | pilot env/test env | assertion log |
| AT-FR-11 | FR-11 | Claimed ticket. | Manager reply text. | Reply via web and Telegram manager session. | Reply persists once as an internal mutation, creates one durable outbound intent, and tracks Telegram delivery result or ambiguity. | E2E/API | automated+manual | release-blocking | pilot env | Telegram transcript, message row, outbound intent row |
| AT-FR-12 | FR-12 | Claimed/manual ticket. | Close action. | Close via web and Telegram callback, repeat close. | One closed ticket, one final close outcome, cleared manager/session/analytics, one durable event. | E2E/API/DB | automated | release-blocking | pilot env | DB snapshot, event log |
| AT-FR-13 | FR-13 | Closed ticket. | Resolution draft, stale version, generator failure. | GET, PATCH, stale PATCH, regenerate success/failure in browser. | Tenant checks, 409 conflict, pending/final statuses, retryable failure behavior. | API+browser E2E | automated | release-blocking | pilot env | Playwright report, API logs |
| AT-FR-14 | FR-14 | Prior closed ticket with client-safe resolution. | Related later question and adversarial resolution case. | Start new thread; ask related question. | Relevant safe resolution used as data; malicious/internal content not followed or exposed. | E2E+eval | automated+manual | release-blocking | pilot env | eval report, prompt/response artifact |
| AT-FR-15 | FR-15 | Several pilot conversations completed. | Known closed/open tickets and analytics fields. | Query metrics UI/API after close. | Limited metrics match expected counts; stale intent/decision/cta are cleared or excluded. | API/browser | automated preferred | release-blocking if promised | pilot env | metrics report |
| AT-FR-16 | FR-16 | Pilot DB has sample data. | Backup artifact. | Run backup, restore into clean DB, run smoke FR-02..FR-14 subset. | Restored system passes smoke; rollback decision points documented. | ops drill | manual+scripted | release-blocking | staging-like env | backup ID, restore log, smoke log |
| AT-NFR-01 | NFR-01 | Two projects and managers exist. | Project A manager, project B thread ID. | Attempt Telegram claim/close/reply from A against B thread. | Request is denied/acknowledged safely and B thread unchanged. | security E2E | automated | release-blocking | test/pilot env | DB before/after, test log |
| AT-NFR-02 | NFR-02 | Webhook secrets configured. | Valid and invalid secret headers. | Send client/manager webhook requests. | Missing/invalid secret rejected; valid secret accepted. | API security | automated | release-blocking | test env | API test log |
| AT-NFR-03 | NFR-03 | PostgreSQL inbox implemented; Redis may be enabled. | Duplicate Telegram update IDs, duplicate callbacks, and replacement bot account update ID reuse. | Send concurrent duplicates for client, manager, and platform-admin paths, then replace one project bot account and deliver a reused `update_id`. | One durable logical update identity per `(surface/role, scope, non-secret bot account identity, update_id)` and one irreversible business processing path; external `sendMessage` exactly-once is not claimed. | concurrency/security | automated | release-blocking | test env | inbox rows, side-effect assertions |
| AT-NFR-04 | NFR-04 | Same client thread exists; PostgreSQL lease and state revision/CAS implemented. | Two different messages sent before first completes. | Force long first RAG/LLM processing; send second same-thread message. | Processing serializes or one message is controlled deferred; no state loss; stale processor cannot emit final response. | concurrency integration | automated | release-blocking | test env with fake LLM | test log, lease/revision/state diff |
| AT-NFR-05 | NFR-05 | Project limits configured. | `requests_per_minute`, `max_concurrent_threads`; Redis healthy and Redis-degraded modes. | Exceed limits, then repeat with Redis unavailable while PostgreSQL remains available. | Limits enforced when accounting is healthy; Redis outage records degraded limit guarantee but does not stop durable intake or thread correctness. | integration | automated | advisory unless sold as guarantee | test env | guard logs, degraded metric |
| AT-NFR-06 | NFR-06 | Fake LLM supports timeout/error. | Timeout, quota, invalid JSON. | Close/regenerate resolution under failures. | Bounded failed/retryable state, no hang, no duplicate token-spend race. | service/API | automated | release-blocking | test env | test log |
| AT-NFR-07 | NFR-07 | Prior resolution exists. | Prompt-injection text in resolution. | Run golden/adversarial answer eval. | Model treats prior resolution as untrusted data. | eval harness | automated+review | release-blocking | eval env | eval report |
| AT-NFR-08 | NFR-08 | Release artifact prepared. | Env/runbook. | Rebuild/deploy from clean checkout. | Reproducible deployment proof exists. | ops | manual+scripted | release-blocking | staging-like env | build/deploy logs |
| AT-NFR-09 | NFR-09 | Backup artifact exists. | Restored DB. | Restore and execute smoke. | Restore is usable for pilot rollback. | ops | manual+scripted | release-blocking | staging-like env | restore evidence |
| AT-NFR-10 | NFR-10 | OpenAPI generation available. | Backend schema and frontend client. | Generate OpenAPI/client and diff. | Contract drift fails release gate. | CI contract | automated | advisory before S6, blocking after S6 | CI/local | diff artifact |

## S1 Runtime Safety Acceptance Cases

| Acceptance Test ID | Req ID | Preconditions | Data | Steps | Expected Result | Level | Mode | Blocking | Environment | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| AT-S1-01 | NFR-03 | PostgreSQL inbox exists. | Two identical updates. | Deliver both concurrently. | One durable logical update, at most one active processing owner, retry attempts only serial after failure or lease expiry, and one effectively-once internal business outcome. | integration | automated | release-blocking | test env | inbox uniqueness assertion |
| AT-S1-02 | NFR-03 | Update accepted, process restarted. | Same update after restart. | Restart worker/API and redeliver update. | Existing accepted/completed lifecycle is reused; no second processing. | restart integration | automated | release-blocking | test env | lifecycle log |
| AT-S1-03 | NFR-03 | PostgreSQL available, Redis down. | New Telegram update. | Deliver update with Redis unavailable. | Update is durably accepted; processing remains recoverable; degraded Redis state is recorded. | failure integration | automated | release-blocking | test env | inbox row, degraded metric |
| AT-S1-04 | NFR-03 | Update durably accepted. | Redis outage after acceptance. | Drop Redis after inbox write. | Work continues or remains recoverable through PostgreSQL lifecycle; no duplicate logical processing. | failure integration | automated | release-blocking | test env | lifecycle/recovery log |
| AT-S1-05 | NFR-03 | Work claimed. | Claimed inbox item. | Crash worker after claim. | Lease expires and update is recoverable by another owner; the next owner creates a serial retry attempt and duplicate webhook delivery does not reset attempt count. | restart integration | automated | release-blocking | test env | lease recovery proof |
| AT-S1-06 | NFR-03 | Processing lease exists. | Expired lease. | Advance time or expire lease and run recovery. | Stuck `processing` item returns to retryable/ready recovery path; actual retry increments attempt count and duplicate delivery does not change lifecycle. | integration | automated | release-blocking | test env | recovery query |
| AT-S1-07 | NFR-04 | Same thread active. | Two different messages. | Deliver both before first completes. | PostgreSQL thread lease serializes/defer processing; no stale state loss. | concurrency | automated | release-blocking | test env | lease/state assertions |
| AT-S1-08 | NFR-04 | Processor owns lease. | Stale owner token. | Let lease expire and new owner claim, then stale owner renew/release. | Stale owner cannot renew/release or commit final response. | concurrency | automated | release-blocking | test env | owner-token assertions |
| AT-S1-09 | NFR-04 | State revision loaded. | Concurrent state updates. | Save with stale revision. | Zero updated rows produces controlled conflict, not silent overwrite. | repository/integration | automated | release-blocking | test env | CAS assertion |
| AT-S1-10 | NFR-04 | CAS conflict occurs. | Pending outbound response. | Force processor conflict after LLM response. | Processor does not send Telegram response and marks conflict/retry/defer. | integration | automated | release-blocking | test env | no-send assertion |
| AT-S1-11 | NFR-03 | PostgreSQL unavailable. | New webhook delivery. | Deliver update while DB unavailable. | Update is not accepted, no business side effects run, Telegram receives retriable non-2xx. | failure integration | automated | release-blocking | test env | HTTP status and side-effect diff |
| AT-S1-12 | FR-08 | Update accepted. | LLM timeout. | Force provider timeout after durable acceptance. | Update remains accepted and moves to retryable failure, fallback, or manager handoff. | integration | automated | release-blocking | test env | lifecycle/outcome row |
| AT-S1-13 | NFR-03 | Durable outbound intent exists. | Telegram send failure. | Retry outbound delivery. | Internal mutation is not repeated; delivery attempts/results are persisted. | integration | automated | release-blocking | test env | outbound intent log |
| AT-S1-14 | NFR-03 | Durable outbound intent exists. | Network-ambiguous Telegram send. | Simulate timeout after Telegram may have accepted send. | Residual duplicate policy is recorded; system does not claim external exactly-once. | integration+manual review | automated+manual | release-blocking | test env | delivery ambiguity report |
| AT-S1-15 | NFR-05 | Project limits configured; Redis unavailable. | Burst traffic. | Deliver burst with Redis down and PostgreSQL available. | Durable intake continues; thread correctness holds; limit guarantee is marked degraded with alert/metric. | integration | automated | advisory unless sold as guarantee | test env | degraded limit evidence |
| AT-S1-16 | NFR-03 | Project bot has persisted non-secret Telegram bot account identity or generation identity; previous updates exist. | Replacement bot account and an `update_id` previously seen for old bot. | Replace project Telegram bot account, persist new bot ID/generation, deliver reused `update_id`, then redeliver the same new-bot update. | Reused `update_id` from new bot is accepted as a distinct durable update; duplicate from the same new bot is deduplicated. | integration | automated | release-blocking | test env | two scoped inbox rows plus duplicate assertion |
| AT-S1-17 | NFR-03 | Completed inbox item exists. | Duplicate completed update. | Redeliver the completed update. | Existing lifecycle remains completed; duplicate does not return row to `received` or `processing`. | repository/integration | automated | release-blocking | test env | status unchanged assertion |
| AT-S1-18 | NFR-03 | Processing inbox item has owner and lease. | Duplicate processing update. | Redeliver update while processing lease is active. | Existing owner and lease are unchanged; no second active owner is created. | repository/integration | automated | release-blocking | test env | owner/lease unchanged assertion |
| AT-S1-19 | NFR-03 | Failed inbox item has attempts and error metadata. | Duplicate failed update. | Redeliver update after retryable or terminal failure. | Attempt count and error state are not reset by duplicate delivery. | repository/integration | automated | release-blocking | test env | attempts/error unchanged assertion |
| AT-S1-20 | NFR-03 | Inbox item exists for an update identity. | Same identity with different payload. | Redeliver same identity with modified payload. | Original payload is preserved and anomaly is recorded without lifecycle reset. | repository/integration | automated | release-blocking | test env | payload/anomaly assertion |

## Golden Answer Evaluation

Golden set must include:

- supported answer in Russian and at least one configured non-Russian `target_language`;
- unsupported question;
- handoff-worthy question;
- repeat question after ticket close;
- adversarial previous resolution text;
- LLM timeout/failure case.

Pass criteria: no unsupported invention, no internal-only resolution leakage, no instruction-following from prior resolution data, and manager decisions only when grounded in manager messages.

## Evidence Retention

Each release-blocking test must attach:

- command or manual runbook step;
- environment identifier;
- commit SHA;
- timestamp;
- pass/fail result;
- artifact path or log reference;
- owner sign-off.
