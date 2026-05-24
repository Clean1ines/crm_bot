# crm_bot Codex Agent Rules

You are working on `crm_bot`, a production-oriented FastAPI + PostgreSQL/pgvector + Redis/queue + React/Vite/TypeScript project.

Always answer in Russian unless explicitly asked otherwise.

## Mandatory Codex environment invariant

Codex must never classify backend test failures as product failures until environment invariant is satisfied.

Required invariant:

- Python must be 3.12.x.
- Backend checks must run through `venv/bin/python` locally or `.codex_venv/bin/python` in Codex/cloud.
- `pytest_asyncio` and `pytest_env` must be importable before any pytest run.
- If invariant is broken, classify as `ENV_FAIL`, not as failed product tests.

Canonical commands:

```bash
bash dev_scripts/bootstrap_codex_env.sh
PYTHON_BIN=.codex_venv/bin/python AUTO_BOOTSTRAP_ENV=0 bash dev_scripts/codex_extended_quality_gate.sh
```

## Non-negotiable workflow

Before changing code:

1. Run read-only reconnaissance.
2. Inspect current files, errors, tests, and existing architecture first.
3. Do not patch blindly.
4. Do not use nano/vim or interactive editors.
5. Use `cat << 'EOF' > file` style commands when giving shell instructions.
6. Do not print secrets. Mask env values as SET/NOT SET or partially masked.
7. Do not commit or push unless explicitly asked.
8. Do not remove existing Telegram `chat_id` manager flows when adding email/link invite flows.

## Project architecture constraints

- `src/domain`: pure domain only. No FastAPI, asyncpg, Redis, Telegram, HTTP frameworks, LLM clients, or infrastructure imports.
- `src/application`: use cases, ports, DTOs, orchestration.
- `src/infrastructure`: DB repositories, queue handlers, external adapters, LLM/embedding implementations.
- `src/interfaces`: FastAPI routes, Telegram entrypoints, auth and DTO boundaries.
- `src/agent`: runtime graphs, prompts, tools, typed agent contracts.
- `frontend`: React/Vite/TypeScript. API contracts must align with backend/OpenAPI.

Frontend/backend contract drift is a bug.

## Knowledge Compilation Domain target

For knowledge/RAG/eval/refactor work, use this target vocabulary:

SourceDocument → SourceChunk → SourceRef → CompilerRun → AnswerCandidate → CandidateCluster → CanonicalKnowledgeEntry → KnowledgeEnrichment → EmbeddingText → EmbeddingVector → RetrievalSurface → EvalCase/RagEval → KnowledgeEditAction.

Non-negotiables:

- `chunk` is not a sufficient production concept.
- `preprocessing_mode` is a compiler selector, not a production entry kind.
- Every published CanonicalKnowledgeEntry must be grounded in source evidence.
- EvalCase is not knowledge.
- RetrievalGuideline is not production knowledge.
- KnowledgeEnrichment is non-authoritative.
- EmbeddingText is not the user-facing answer.
- RetrievalSurface is the production retrieval contract, not just a persistence table.
- RAG eval must test the production RetrievalSurface.

## Installed repo skills

Use these repo-local skills from `.agents/skills` when relevant:

### Local crm_bot skill

- `crm-bot-architecture-governance`

### ECC skills

- `architecture-decision-records`
- `search-first`
- `iterative-retrieval`
- `tdd-workflow`
- `security-review`
- `security-scan`
- `verification-loop`
- `eval-harness`
- `api-design`
- `backend-patterns`
- `frontend-patterns`
- `postgres-patterns`
- `database-migrations`
- `deployment-patterns`
- `docker-patterns`
- `e2e-testing`
- `python-patterns`
- `python-testing`
- `cost-aware-llm-pipeline`
- `regex-vs-llm-structured-text`
- `content-hash-cache-pattern`
- `workspace-surface-audit`
- `skill-stocktake`

## Codex project agents

Project-local Codex subagents live in `.codex/agents/`.

Most project agents are thin Codex wrappers around exact upstream ECC agent prompts downloaded into `.codex/upstream/ecc-agents/`.
Do not edit `.codex/upstream/ecc-agents/*.md` manually; resync from ECC instead.

Use project agents for all serious work, not only architecture.

### Core planning and architecture

- `planner`: wrapper for ECC `agents/planner.md`.
- `architect`: wrapper for ECC `agents/architect.md`.
- `backend_mapper`: local crm_bot backend path mapper.
- `frontend_mapper`: local crm_bot frontend path mapper.

### Implementation and debugging

- `implementer`: local crm_bot targeted patch agent.
- `build_error_resolver`: wrapper for ECC `agents/build-error-resolver.md`.
- `refactor_cleaner`: wrapper for ECC `agents/refactor-cleaner.md`.

### Stack reviewers

- `typescript_reviewer`: wrapper for ECC `agents/typescript-reviewer.md`.
- `python_reviewer`: wrapper for ECC `agents/python-reviewer.md`.
- `database_reviewer`: wrapper for ECC `agents/database-reviewer.md`.

### Quality, tests, security, docs

- `tdd_guide`: wrapper for ECC `agents/tdd-guide.md`.
- `e2e_runner`: wrapper for ECC `agents/e2e-runner.md`.
- `security_reviewer`: wrapper for ECC `agents/security-reviewer.md`.
- `reviewer`: wrapper for ECC `agents/code-reviewer.md`.
- `doc_updater`: wrapper for ECC `agents/doc-updater.md`.
- `docs_lookup`: wrapper for ECC `agents/docs-lookup.md`.

### Workflows

Use `.codex/workflows/audit.md` for audit-only work.
Use `.codex/workflows/implementation.md` for non-trivial implementation work.
Use `.codex/workflows/build-fix.md` when lint/type/build/tests fail.
Use `.codex/workflows/docs-adr.md` for ADR/docs work.

## Intent router

For common user requests, choose the workflow automatically. Do not require the user to manually list skills or agents.

- If the user says “проведи аудит”, “audit project”, “architecture review”, “pre-PR review”, or asks to find project risks:
  use `.codex/workflows/audit.md`.

- If the user says “исправь ошибку”, “fix failing check”, “type-check fails”, “build fails”, “lint fails”, “tests fail”, or provides failing command output:
  use `.codex/workflows/build-fix.md`.

- If the user says “реализуй”, “добавь фичу”, “почини баг”, “refactor”, or asks for a non-trivial code change:
  use `.codex/workflows/implementation.md`.

- If the user says “оформи ADR”, “задокументируй решение”, “обнови docs”, or the task changes architecture/public contracts/deployment/RAG/eval:
  use `.codex/workflows/docs-adr.md` together with `architecture-decision-records`.

Default rule:
For non-trivial work, select relevant repo skills and project agents automatically from `AGENTS.md`, `.agents/skills`, and `.codex/agents`.
Do not ask the user to manually enumerate skills or agents.
Always report which workflow, skills, and agents you selected.

## Required task flow

For every non-trivial code task:

### 1. Recon

Run or request targeted read-only recon:

- `pwd`
- `git status --short`
- `git diff --stat`
- targeted `rg`
- targeted `nl -ba ... | sed -n`
- inspect existing tests before adding new ones

Do not dump huge files. Use focused ranges.

### 2. Skill selection

Before planning, name the skills you are applying.

Default sequence for architectural/codebase tasks:

1. `search-first`
2. `iterative-retrieval`
3. `crm-bot-architecture-governance`
4. `architecture-decision-records`, only if ADR conditions are met
5. `tdd-workflow` or `verification-loop`
6. `security-review`, when auth, tenant isolation, secrets, external inputs, LLM/tooling, shell, or deployment are touched
7. stack-specific skills: `api-design`, `backend-patterns`, `frontend-patterns`, `postgres-patterns`, `database-migrations`, `deployment-patterns`, etc.

### 3. Architecture check

Before patching, identify:

- existing behavior
- affected files/symbols
- affected architectural boundaries
- relevant docs/ADRs
- whether ADR/RFC is required
- validation gates

Use `architecture-decision-records` when a decision changes or introduces:

- domain model
- persistence model
- retrieval/RAG/eval architecture
- public API contract
- auth/tenant model
- queue/runtime behavior
- deployment architecture
- testing/evaluation strategy

ADRs live in `docs/adr/`.

Do not write ADRs for trivial local implementation details.

### 4. Plan

Produce a short implementation plan:

- exact files to change
- exact order of changes
- expected tests/gates
- risks
- rollback

### 5. Patch

Patch minimally:

- no broad rewrites unless explicitly requested
- no duplicate helpers/constants
- no new `Any` or `ignore` without reason
- no architecture boundary drift
- no unrelated formatting churn

### 6. Validate

Run focused validation when possible.

Backend examples:

- `venv/bin/ruff format --check src tests`
- `venv/bin/ruff check src tests`
- `venv/bin/mypy src`
- focused `venv/bin/pytest ...`

Frontend examples:

- `npm run lint`
- `npm run type-check`
- `npm run build`

For full commit readiness, run the project quality gate if available:

- `bash dev_scripts/codex_extended_quality_gate.sh`

### 7. Review

Before final answer, review for:

- correctness
- architecture boundary drift
- missing ADR/RFC
- security/auth/tenant risks
- OpenAPI/frontend contract drift
- test coverage gaps
- rollback clarity

## Audit mode

When asked to audit the project, do not patch by default.

Use this audit sequence:

1. `search-first`
2. `iterative-retrieval`
3. `crm-bot-architecture-governance`
4. `architecture-decision-records`
5. `security-review`
6. `verification-loop`
7. stack-specific skills as needed

Audit output must include:

- executive summary
- architecture map
- boundary violations or risks
- missing/obsolete ADRs
- product-critical risks
- security risks
- test/validation gaps
- prioritized remediation plan
- suggested first 3 patches
- what was not verified

## Completion rule

Do not mark a task complete until validation evidence is shown.

Final response must include:

- what changed
- why it changed
- files changed
- validation commands and results
- remaining risks
- rollback plan

If validation cannot be run, state exactly why and what remains unverified.
