# crm_bot Codex Agent Rules

You are working on `crm_bot`, a production-oriented FastAPI + PostgreSQL/pgvector + Redis/queue + React/Vite/TypeScript project.

Always answer in Russian unless explicitly asked otherwise.


## Codex Cloud validation rules

Codex Cloud auto setup installs Python dependencies from `requirements.txt`.

For Codex Cloud:
- Do not create a nested virtualenv.
- Do not use `venv/bin/...`.
- Do not run extra dependency bootstrap scripts before validation.
- Direct `python -m pytest -q` must work from a fresh Codex workspace; `tests/conftest.py` bootstraps `.env.test` from `.env.test.example` before importing Settings.
- Run backend validation through the current Python interpreter:
  - `python -m ruff format --check src tests`
  - `python -m ruff check src tests`
  - `python -m mypy src`
  - `python -m pytest -q`
  - `bash dev_scripts/codex_extended_quality_gate.sh`, if the gate itself uses `python` by default.

Dependency file contract:
- `requirements-prod.txt` is for Docker/production runtime.
- `requirements-dev.txt` is for local/dev/test tool lists.
- `requirements.txt` is the Codex/test aggregate file and may include both prod and dev requirements.

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

- `python -m ruff format --check src tests`
- `python -m ruff check src tests`
- `python -m mypy src`
- focused `python -m pytest ...`

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

## Environment workflow

Before backend tests, ruff, mypy, or the full quality gate, always run:

```bash
bash dev_scripts/ensure_test_env.sh
```

The canonical test/Codex env surface is `.env.test.example`.

If `.env.test` is missing, create it from `.env.test.example`.

Do not ask for production environment values to run local/Codex checks. Use the placeholder values from `.env.test.example`.

Do not add real deployment values to `.env.example`, `.env.test.example`, docs, reports, or commits.


<!-- BEGIN CRM_BOT MVP WORK ITEM ROUTER -->

## Pilot MVP backlog work-item router

A request that names a Pilot v0.1 backlog ID such as `S1.1`, `S1.2`, or says `backlog item` MUST use:

- `.codex/workflows/mvp-work-item.md`;
- `.agents/skills/crm-bot-mvp-work-item/SKILL.md`;
- `.agents/skills/crm-bot-qa-design/SKILL.md` before implementation;
- `.agents/skills/crm-bot-acceptance-verification/SKILL.md` after implementation.

The task card at `docs/releases/pilot-v0.1/backlog/<ID>-*.md` is the direct execution contract. The agent must also read every requirement, risk, ADR, specification, acceptance test, dependency, and architecture reference linked by that card.

### Mandatory gates

For a Pilot backlog item, the agent MUST NOT patch production code until:

1. the backlog item resolves uniquely;
2. its status permits QA design;
3. all required documents have been checked against current code;
4. every required ADR is `accepted` for implementation;
5. a read-only `qa_designer` has produced a QA Design Record with verdict `READY` or `READY_WITH_CORRECTIONS`;
6. required corrections have been incorporated into the task contract;
7. impact analysis and an implementation plan are complete;
8. tests that prove the missing behavior have been identified and, where practical, shown failing for the expected reason.

### Documentation freshness

Current code is evidence of current implementation, not authority to silently rewrite requirements.

If code and documentation disagree:

- correct stale factual documentation when the approved decision is unchanged;
- stop and require ADR/specification resolution when the disagreement changes architecture, requirement meaning, release scope, security policy, persistence semantics, or acceptance criteria;
- never reinterpret requirements merely to make the current implementation pass.

### QA participation

QA design is mandatory before code. QA must independently cover state transitions, negative behavior, concurrency, retries, restart/recovery, partial failure, migrations, security/tenant boundaries, external dependencies, observability, and regression surfaces relevant to the work item.

After implementation, `acceptance_reviewer` must independently compare the result with the task card, accepted ADRs, requirements, QA Design Record, acceptance criteria, actual diff, and validation evidence.

### Work-item state and commit policy

Work-item state is separate from requirement and release state. Completing one work package must not mark a parent requirement or release as verified unless its full acceptance contract is proven.

For cards containing `commit_policy: on_green`, the card itself is explicit authorization to create one local task-scoped commit, but only after every commit gate in the work-item workflow passes. This authorization does not permit push.

The agent must not commit when:

- required ADRs are not accepted;
- QA or reviewer verdict is failing or blocked;
- focused or affected regression checks fail;
- full required validation was not run without a documented accepted exception;
- documentation/evidence is stale;
- the staged diff contains unrelated changes;
- secrets or real environment values may be present.

One work item produces at most one implementation commit. Do not push unless the user explicitly requests it separately.

### Required completion artifacts

A verified work item must update:

- its backlog card;
- its QA Design Record;
- `TRACEABILITY_MATRIX.md` and other affected release documents;
- a task evidence record under `docs/releases/pilot-v0.1/evidence/`;
- actual architecture documentation only when implementation state truly changed.

The evidence record must contain the result commit SHA. To avoid a second documentation commit, write the evidence record with `result_commit: SELF` before commit; after commit report the actual SHA in the final response. A later release-evidence rollup may replace `SELF` with the immutable SHA.

<!-- END CRM_BOT MVP WORK ITEM ROUTER -->
