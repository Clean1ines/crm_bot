# ADR 0001: Durable capacity-window workflow runtime

- Status: Proposed
- Date: 2026-06-19

## Context

Knowledge extraction previously advanced mainly when an HTTP live-state request
drained pending workflow commands. Capacity admission also lacked an atomic
reservation shared by concurrent workers, expired leases were not reclaimed by
the production runtime, and a confirmed degraded-model choice had no executable
transition.

These gaps could leave durable commands idle, over-admit one provider/account/model
route, strand leased work after worker loss, or leave a workflow permanently
waiting after the user accepted degraded execution.

## Decision

1. Run a background workflow-runtime service from the FastAPI lifespan. Each tick
   reclaims expired leases, discovers due workflows, and drains them outside the
   maintenance transaction.
2. Reserve provider/account/model request and token capacity transactionally when
   an LLM attempt is started. Serialize route admission with a PostgreSQL advisory
   transaction lock, subtract active reservations during admission, and finalize
   reservations after execution.
3. Represent manual degraded fallback as an explicit, idempotent workflow
   transition. Only unresolved `primary_model_daily_capacity_exhausted` events may
   create the degraded prepare command. Project ownership is checked in the same
   transaction, and the decision is recorded in the workflow outbox.
4. Expose the transition through workflow live-state and the Knowledge UI only
   while that exact confirmation remains pending.
5. Preserve the existing evidence contract: `evidence_block` stores the
   `SourceRef`/source-unit identifier. It is not converted back to source text.

## Consequences

- Workflow progress no longer depends on browser polling.
- Concurrent replicas share an atomic capacity budget.
- Worker crashes can no longer leave leases permanently stranded.
- User-confirmed degraded execution has an auditable backend and frontend path.
- Deployment must apply migration `115_create_llm_route_capacity_reservations.sql`.
- The current workflow command runner still contains some transactions spanning
  provider I/O; separating execution from persistence remains follow-up work.

## Rollback

Disable `KNOWLEDGE_WORKFLOW_RUNTIME_ENABLED`, remove the confirmation action from
the UI/API, and revert the reservation-aware admission code. The reservation table
may remain unused during rollback; dropping it is not required for runtime safety.
