# ADR-0003: PostgreSQL-Owned Conversation Runtime Coordination and State Consistency

Date: 2026-08-04
Status: proposed
Deciders: crm_bot maintainers; project owner approval pending

## Context

At baseline, `ClientMessageService` calls a thread lock port, but production composition does not inject a concrete lock, so `ConversationOrchestrator` defaults to `NullThreadLock`. The available Redis lock has a TTL and simple delete release, while `ThreadRuntimeStateRepository.save_state_json` writes the whole `state_json` document without revision conflict protection. Owner constraints require PostgreSQL to own correctness for same-thread execution and runtime state, with Redis allowed only as acceleration or accounting.

## Decision

Use PostgreSQL execution lease plus PostgreSQL state revision/CAS as the production correctness boundary for conversation runtime coordination. Redis may remain an optional fast coordination and runtime accounting layer, but it must not be the only mechanism preventing duplicate processing, parallel same-thread writes, or state loss.

Same-thread processing must claim a PostgreSQL row/table-backed execution lease scoped to project/thread. The lease has a random owner token, expiration, atomic claim, owner-guarded renew, owner-guarded release, and recovery after expiration, without holding one pooled DB connection during long graph or LLM processing.

Runtime state saves must use optimistic conflict protection: processors load state with a revision, save only when the expected revision matches, increment revision on success, and treat zero updated rows as a controlled conflict/retry/defer condition. Whole-document `state_json` may remain the physical storage format only while revision/CAS prevents silent stale overwrite.

## Alternatives Considered

### `NullThreadLock`

- Advantages: no runtime dependency and easiest rollback.
- Disadvantages: allows real parallel processing for the same thread and provides no ownership or recovery.
- Why not: returning production traffic to this mode is not an acceptable rollback for pilot traffic.

### Redis lock only

- Advantages: simple, fast, and already partially available.
- Disadvantages: Redis outage weakens correctness, TTL expiration can allow overlap, and simple delete release lacks owner safety.
- Why not: owner constraints reject Redis as the sole state correctness authority.

### PostgreSQL advisory lock

- Advantages: native Postgres coordination primitive.
- Disadvantages: a long graph/LLM run would either hold a pooled connection or require a more complex transaction boundary.
- Why not: it is rejected if it requires holding one DB connection throughout LLM processing.

### PostgreSQL row/table-backed execution lease

- Advantages: durable, inspectable, recoverable after expiration, owner-token guarded, and connection-pool friendly.
- Disadvantages: needs schema/repository work and lease renewal/recovery tests.
- Why selected: it is the minimal pilot-compatible correctness mechanism.

### Optimistic CAS only

- Advantages: prevents silent state overwrite and is easy to reason about.
- Disadvantages: does not by itself serialize expensive LLM/RAG processing or prevent duplicated side-effect attempts.
- Why not alone: it is required, but insufficient without execution ownership.

### Redis lock plus PostgreSQL CAS

- Advantages: improves current design while adding state conflict protection.
- Disadvantages: Redis remains the execution owner and Redis outage semantics remain unsafe unless a DB lease also exists.
- Why not as final target: acceptable only as a temporary acceleration layer on top of PostgreSQL ownership.

### PostgreSQL lease plus PostgreSQL CAS with optional Redis acceleration

- Advantages: durable ownership, no silent overwrite, Redis-degraded correctness, and clear conflict behavior.
- Disadvantages: S1 becomes larger than simple wiring and requires migrations.
- Why selected: it is the pilot target.

### Full event sourcing

- Advantages: strongest auditability and replay semantics.
- Disadvantages: broad architecture change across runtime, lifecycle, metrics, and prompts.
- Why not: too large for the managed Telegram-only pilot MVP.

## Consequences

### Positive

- Same-thread execution remains safe across duplicate updates, multiple processes, Redis outage, and process restart.
- Runtime state conflicts are explicit instead of last-write-wins.
- Outbound responses can be blocked when a processor loses lease or CAS ownership.
- S1 becomes a real production-safety slice, not only Redis wiring.

### Negative

- S1 requires DB migration work for execution lease and state revision/CAS.
- Graph persistence must report and handle conflicts instead of blindly saving snapshots.
- Some state ownership cleanup remains for S5 after minimal CAS is in place.

### Risks

- Lease duration and renewal policy must account for long LLM/RAG processing.
- CAS conflicts need controlled retry/defer behavior that does not spam Telegram.
- Runtime project limit accounting can still degrade if Redis is unavailable unless a separate approved fallback is added.

## Implementation Boundaries

- PostgreSQL is authoritative for conversation runtime state, thread execution ownership, message/event persistence, state revision, and recoverable processing progress.
- A processor must acquire PostgreSQL thread execution lease before same-thread graph work.
- A stale processor must not save state, create final outbound response, or mark update completed.
- Conversation graph owns continuity state; thread lifecycle service owns status/lifecycle transitions; ticket resolution service owns `ticket_resolution`; analytics service owns analytics fields and explicit clear semantics; manager flow owns assignment/session contract.
- S1 must include minimal revision/CAS to prevent silent stale overwrite.
- S5 hardens state ownership by reducing broad whole-document writes and decomposing persistence contracts.

## Failure And Recovery Semantics

- Logical processing order is: durable update accepted; processing work claimed; PostgreSQL thread lease acquired; state and revision loaded; runtime/LLM processing performed; state/messages/events and durable outbound intent committed; work marked completed or advanced; outbound Telegram delivery executed from durable intent; delivery result persisted.
- Final Telegram response must not be sent before successful state/business commit.
- If a processor loses lease or revision ownership, it records controlled conflict/retry/defer behavior and does not emit a final response.
- Redis outage does not return runtime to `NullThreadLock` and does not permit unrestricted unsafe parallel state writes.
- Runtime project limits may use Redis accounting; during Redis outage, durable intake and thread correctness continue while limit guarantee is degraded and operator-visible.
- Acceptable rollback disables Redis optimization, reduces worker concurrency, increases latency, disables optional AI features, or routes risky messages to managers.
- Unacceptable rollback returns production traffic to `NullThreadLock`.
- Telegram intake stops only when PostgreSQL durable acceptance is unavailable.

## Validation

- Two different messages for one thread arriving concurrently are serialized or one is safely deferred.
- A stale owner cannot renew/release another owner lease.
- State revision conflict produces zero-row conflict handling and no final Telegram response.
- Redis outage still allows durable intake, DB lease, and CAS protection.
- Worker crash after lease/inbox claim recovers after expiration.
- Runtime limits in Redis-degraded mode produce operational alert/metric and do not lose accepted updates.

## References

- `src/application/orchestration/client_message_service.py`
- `src/application/orchestration/conversation_orchestrator.py`
- `src/application/ports/lock_port.py`
- `src/infrastructure/redis/lock.py`
- `src/infrastructure/db/repositories/thread/runtime_state.py`
- `src/application/services/project_runtime_guards.py`
- `docs/releases/pilot-v0.1/IMPLEMENTATION_SLICES.md`
