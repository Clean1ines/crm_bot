---
name: crm-bot-architecture-governance
description: Use for any crm_bot change that touches architecture, domain boundaries, knowledge/RAG/eval flows, persistence, OpenAPI/frontend contracts, auth, queue/runtime, or deployment. Enforces ADR/RFC-aware development.
origin: local-crm-bot
---

# crm_bot Architecture Governance

## Trigger

Use this skill before coding when a task touches any of:

- `src/domain`
- `src/application`
- `src/infrastructure`
- `src/interfaces`
- `src/agent`
- `frontend/src/shared/api`
- `frontend/src/pages`
- OpenAPI generation
- DB repositories or migrations
- queue handlers
- knowledge ingestion / retrieval / RAG eval
- authentication / authorization
- deployment / Render / Docker / CI
- public product behavior

## Mandatory architecture loop

1. Read `AGENTS.md`.
2. Run read-only recon.
3. Check `docs/adr/README.md` and relevant ADRs if present.
4. Check `docs/architecture/` if present.
5. Identify affected boundaries.
6. Decide whether this is:
   - simple local code change
   - architectural change requiring ADR
   - product/RFC change requiring a short proposal before patching
7. Only then create an implementation plan.

## Boundary rules

- Domain must not import FastAPI, asyncpg, Redis, LLM clients, Telegram, HTTP frameworks, or infrastructure.
- Application may orchestrate use cases through ports/contracts.
- Infrastructure implements DB/external adapters.
- Interfaces own HTTP/Telegram DTO boundaries.
- Agent layer wires runtime graphs/prompts/tools.
- Frontend API contracts must match backend/OpenAPI.
- RAG eval must test the production retrieval surface, not a separate artificial path.

## ADR rule

Create or update an ADR when the change introduces, replaces, or weakens:

- domain vocabulary
- persistence model
- retrieval surface
- ingestion/compiler pipeline
- public API contract
- auth/tenant model
- deployment architecture
- queue/runtime architecture
- testing/evaluation strategy

Do not create ADRs for tiny implementation details.

## Output required before patching

Return:

1. Relevant existing architecture facts.
2. Affected files/symbols.
3. Affected boundaries.
4. Existing ADRs consulted or "none found".
5. Whether ADR/RFC is required.
6. Implementation plan.
7. Validation plan.
8. Rollback plan.
