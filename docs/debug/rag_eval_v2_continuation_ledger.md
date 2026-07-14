# RAG Eval V2 continuation ledger

## Current state

**Date:** 2026-07-14
**Committed base / HEAD:** `82f133bbae5b9c8401184dd5e3d8d26b02ff827f`
(`82f133bb Remove duplicate RAG Eval claim completion`)
**Working tree:** dirty with the uncommitted RAG Eval V2 continuation and
separate hygiene/schema changes described below.

The active RAG Eval V2 implementation in this working tree includes:

- qgen, retrieval, adjudication, promotion review and reversible grouped
  promotion application;
- embedding revision read models, accept and rollback use cases, HTTP routes and
  frontend revision controls;
- bounded durable post-promotion verification: the command handler uses a named
  `batch_limit`, lists only the next pending verification queries, persists only
  the processed batch outcomes, emits `VerificationBatchCompleted`, appends a
  stable continuation command while pending work remains, and emits terminal
  metrics/policy/`VerificationCompleted` only when `remaining == 0`;
- durable verification schema, query planning, before/after outcome pair
  persistence, metrics calculation and conservative regression policy;
- project/workflow frontend-event list and SSE endpoints for documentless RAG
  Eval runs using the existing frontend event repository and transport;
- synthetic RAG Eval projection document ids for runs without
  `source_document_ref`;
- frontend projection reducer/query invalidation for RAG Eval workflow events;
- persisted `available_actions.can_accept` and
  `available_actions.can_rollback`, consumed by the revision panel instead of
  frontend lifecycle guessing;
- verification read/list APIs and frontend metrics UI for persisted
  promoted/holdout/baseline/neighbour metrics, including before/after
  top1/top3/top5, mean rank, mean margin, miss/confusion counts and deltas.

## Commit set plan

The current working tree should be split into three logical commit sets before
committing.

### A. RAG Eval V2 feature

Contains the RAG Eval backend/application/infrastructure/interfaces changes,
RAG Eval frontend page/API/reducer changes, RAG Eval migration, RAG Eval tests,
and this ledger.

Must not include Knowledge UI lint-hygiene files or generated TypeScript schema
refresh.

### B. Knowledge UI lint hygiene

Contains only repository-wide Knowledge UI lint hygiene required for the full
frontend lint gate. These changes are not part of the RAG Eval runtime.

Current hygiene scope:

- `frontend/src/pages/knowledge/KnowledgePage.tsx`
- `frontend/src/pages/knowledge/KnowledgePage.workflowProjection.test.ts`
- `frontend/src/pages/knowledge/curationReadyLiveEvent.ts`
- `frontend/src/pages/knowledge/components/DraftClaimCurationWorkspaceModal.tsx`
- `frontend/src/pages/knowledge/components/DraftClaimCurationWorkspaceModalState.ts`
- `frontend/src/pages/knowledge/components/DraftClaimCurationWorkspaceModalState.test.ts`
- `frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx`
- `frontend/src/pages/knowledge/components/workflow-timer/useWorkflowTimerText.ts`

No `queueMicrotask` remains in the four reviewed Knowledge UI files. The curation
modal lifecycle cleanup is covered by a pure focused regression test.

### C. Generated TypeScript OpenAPI schema refresh

Contains only:

- `frontend/src/shared/api/generated/schema.ts`

Generated OpenAPI JSON files are clean against HEAD after regeneration; the
TypeScript schema refresh must be committed separately or explicitly separated
from the RAG Eval feature commit.

## Validation evidence

Final validation after the current hygiene pass:

```text
bash dev_scripts/ensure_test_env.sh: passed
python -m ruff format --check src tests: passed
python -m ruff check src tests: passed
python -m mypy src: passed
python -m pytest -q: 2782 passed, 2 skipped, 1 warning

cd frontend && npm run lint: passed
cd frontend && npm run type-check: passed
cd frontend && npm run build: passed
cd frontend && npm test -- --run: 60 passed

git diff --check: passed
```

Frontend build still emits the environment warning that local Node.js is
`18.19.1` while Vite requires `20.19+` or `22.12+`; the build nevertheless
completed successfully.

## Historical checkpoints

### 2026-07-14 post-promotion verification foundation

This historical checkpoint was recorded before the read APIs, full metrics UI
and project/workflow SSE work were completed.

Implemented at that point:

- verification domain models, durable metrics and conservative regression
  policy;
- migration `129_create_workbench_rag_eval_post_promotion_verifications.sql`
  for verification headers, dataset queries and before/after outcome pairs;
- grouped promotion application enqueued `RUN_POST_PROMOTION_VERIFICATION` with
  a stable idempotency key;
- workflow dispatcher/drain could call a registered post-promotion verification
  executor and mark the command complete;
- production workflow runtime composition wired the real post-promotion
  verification executor;
- repository methods created durable promoted/baseline/holdout/neighbour
  verification query plans, ranked before/after observations and persisted
  outcome pairs/final verification state;
- explicit embedding revision accept/rollback use cases, repository methods and
  HTTP routes;
- rollback restored previous aliases, embedding text and embedding vector
  atomically when the current runtime hash matched the revision's
  `new_runtime_hash`;
- accept required a passed/acceptable persisted verification row;
- frontend API/query keys and minimal revision panel controls existed for
  accept/rollback.

Historical gaps from that checkpoint, now resolved in the current working tree:

- verification read models and HTTP detail/list endpoints;
- full frontend verification metrics/regression reasons and SSE invalidation;
- frontend lint blockers in the reviewed Knowledge UI files.

Historical focused validation from that checkpoint:

```text
python -m pytest tests/architecture/test_workbench_rag_eval_post_promotion_verification_boundary.py tests/contexts/knowledge_workbench/rag_eval/application/policies/test_workbench_rag_eval_promotion_verification_policy.py tests/contexts/knowledge_workbench/rag_eval/application/use_cases/test_workbench_rag_eval_embedding_revision_actions.py tests/interfaces/http/test_workbench_rag_eval_embedding_revisions.py tests/contexts/knowledge_workbench/rag_eval/application/workflows/test_workbench_rag_eval_adjudication_workflow.py::test_dispatch_post_promotion_verification_uses_registered_handler tests/architecture/test_workbench_rag_eval_promotion_application_claim_boundary.py -q: 28 passed
python -m pytest tests/architecture/test_workbench_rag_eval_post_promotion_verification_boundary.py tests/contexts/knowledge_workbench/rag_eval/application/use_cases/test_run_workbench_rag_eval_post_promotion_verification.py tests/contexts/knowledge_workbench/rag_eval/application/policies/test_workbench_rag_eval_promotion_verification_policy.py tests/contexts/knowledge_workbench/rag_eval/application/workflows/test_workbench_rag_eval_adjudication_workflow.py tests/interfaces/http/test_workbench_rag_eval_embedding_revisions.py -q: 32 passed
python -m pytest -q: 2777 passed, 2 skipped
```

## Canonical contracts

### Question roles

The valid question roles are:

```text
BASELINE
PROMOTION_POOL
HOLDOUT
```

Semantics:

- existing published possible questions become `BASELINE`;
- generated questions are deterministically divided into `PROMOTION_POOL` and
  `HOLDOUT`;
- each generated set contains at least two holdout questions;
- `BASELINE` and `HOLDOUT` are never promotion-eligible;
- `HOLDOUT` questions participate in post-promotion verification and must never
  be promoted in the same cycle.

### Retrieval classifications

The canonical retrieval classifications are:

```text
PASS_STRONG
PASS_WEAK
CONFUSION
MISS
EXISTING_ALIAS_RETRIEVAL_FAILURE
```

The previous temporary vocabulary is invalid and must not be reintroduced:

```text
TOP1
TOP3
TOP5
CONFUSED_WITHIN_DOCUMENT
```

### Retrieval outcome identity

A canonical retrieval outcome is scoped by:

```text
outcome_id
run_id
question_id
project_id
evaluation_stage
```

The supported stages are:

```text
initial
verification_before
verification_after
```

The uniqueness boundary is:

```text
(run_id, question_id, evaluation_stage)
```

A retrieval outcome contains:

- expected runtime entry and fact;
- expected rank and score;
- best competitor runtime entry and fact;
- best competitor score;
- score margin;
- canonical classification.
