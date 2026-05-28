# FAQ Surface Finish Recon

## Branch

Remote branch: `main`.

## Workspace access note

This report was reconstructed through the GitHub connector. A local clone was attempted from the execution container, but direct network access to GitHub failed with DNS resolution error (`Could not resolve host: github.com`). Because of that, local `git status`, local `git diff`, local test execution, and local frontend build were not available in this run.

## Status / diff constraints

- Direct local `git status --short`: not available from this environment.
- Direct local `git diff --stat`: not available from this environment.
- Direct local `git diff --cached --stat`: not available from this environment.
- Untracked files: not inspectable through the GitHub connector.
- Temporary folder `faq_surface_pipeline_patch/`: not visible in tracked remote files; local workspace state could not be inspected.

## Relevant remote commits created in this pass

- `85670b1` — expose FAQ surface state GET endpoints in `src/interfaces/http/knowledge_surface.py`.
- `38a7521` — align surface endpoint contract test with `knowledge_surface.py`.
- `39526a1` — expose merge decisions/source units/embedded ownership types in frontend surface API module.
- `eac9e28` — render filters, merge decisions, reassignments, rejections and source evidence in `SurfaceCompilationSummary`.
- `8dbcc76` — fix import ordering in the surface router.

## Already green according to prior task context

These checks were reported green before this finishing pass, but were not re-run locally here:

- `ruff check` on previously changed backend files.
- `mypy src` => `Success: no issues found in 307 source files`.
- `pytest tests/application/test_faq_surface_compiler_contracts.py -q` => 8 passed.
- `npm --prefix frontend run type-check`.
- `npm --prefix frontend run build`.
- Bootstrap marker audit for `faq_surface_compiler_bootstrap_v1|model="bootstrap"|metadata={"bootstrap": True}|Bootstrap ownership|Bootstrap:` found no matches.

## Remote recon findings before patches

### FAQ upload / queue path

- `src/interfaces/http/app.py` includes `knowledge_surface_router` before legacy `knowledge_router`, so the surface-aware `POST /api/projects/{project_id}/knowledge` route shadows the legacy upload route for HTTP upload.
- `src/interfaces/http/knowledge_surface.py` routes `preprocessing_mode=faq` to queue payload with `MODE_FAQ`, `queued:GroqKnowledgeSurfaceCompiler`, `bootstrap_fallback=False`, and no preprocessor factory.
- `src/infrastructure/queue/handlers/knowledge_upload.py` branches on `mode == MODE_FAQ`, calls `KnowledgeFaqSurfaceIngestionService(...).process_document(...)` with `GroqKnowledgeSurfaceCompiler`, then returns before the legacy `KnowledgeIngestionService` / `GroqKnowledgePreprocessor` path.

### Legacy FAQ guards

- `make_knowledge_preprocessor(preprocessing_mode=faq)` raises `ValueError` and forbids old FAQ preprocessor usage.
- `parse_preprocessing_payload(..., mode=MODE_FAQ, ...)` raises `KnowledgePreprocessingValidationError` and forbids legacy `fragments[]` parser.
- `GroqKnowledgeSurfaceCompiler.compile_surfaces` is guarded to `mode=faq` and rejects non-FAQ modes.

### Surface persistence

Repository methods already existed for:

- `create_surface_compiler_run`
- `update_surface_compiler_run_status`
- `create_surface_compiler_stage`
- `save_surface_source_units`
- `save_surfaces`
- `save_surface_relations`
- `save_surface_question_ownership`
- `save_surface_question_reassignments`
- `save_surface_merge_decisions`
- read methods by latest run / run id for stages, source units, surfaces, relations, ownership, reassignments, merge decisions.

### API gaps found and patched

Before this pass, frontend called these endpoints but `knowledge_surface.py` only exposed upload override and publish:

- `GET /surface-compilation`
- `GET /surfaces`
- `GET /surface-relations`
- `GET /surface-ownership`

Patched:

- Added `GET /{document_id}/surface-compilation` returning latest run, stages, source units.
- Added `GET /{document_id}/surfaces` returning surfaces enriched with parent/child keys, ownership, rejected questions, reassignments, relations and merge decisions.
- Added `GET /{document_id}/surface-relations`.
- Added `GET /{document_id}/surface-ownership`.
- Added `GET /{document_id}/surface-merge-decisions`.
- Changed published canonical entry creation to preserve `compiler_run_id=surface.run_id` instead of an empty string.

### Frontend gaps found and patched

Before this pass, `SurfaceCompilationSummary` loaded surfaces/relations/ownership but did not expose the mandatory surface filters, merge decisions, reassignments, rejections, or source evidence.

Patched:

- Added filters: All, Umbrella, Child, Document Upload, Curation, Retrieval Quality, Integration, Channel, Handoff / Limits, Other.
- Added merge decisions query/rendering.
- Added rejected question rendering.
- Added reassignment rendering.
- Added source evidence rendering.
- Added frontend API types for source units, merge decisions, embedded ownership/reassignment/relation metadata, source excerpt and source metadata.

## Acceptance items still not fully proven

The following items are improved but not fully proven in this run because local validation could not be executed:

1. Full backend tests pass.
2. Full frontend type-check/build pass.
3. Full quality gate pass.
4. OpenAPI generated schema alignment, if generated client schema is required by the current workflow.
5. Real fixture acceptance test covering the full product/search/short-answer/manual-merge/hide-archive/Telegram/web-widget/negative-tests scenario.
6. Runtime RAG eval proof that eval loads the same production retrieval surface and sees owned questions.
7. Retry semantics for failed FAQ surface runs remain only partially covered. Existing retry endpoint is still oriented around failed legacy batches.
8. Compiler parsing of explicit question reassignments still needs a targeted compiler patch and contract test; persistence/API/frontend can represent reassignments, but current parser needs confirmation or extension.
9. `/fragments` remains reachable as a legacy endpoint. It is no longer the primary FAQ UI path, but a strict clean-break implementation should explicitly return empty/forbid this endpoint for FAQ documents.

## Validation still required after these commits

Run from a real project workspace:

```bash
cat << 'EOF' > /tmp/faq_surface_finish_validate.sh
#!/usr/bin/env bash
set -euo pipefail

cd /home/haku/crm_bot
bash dev_scripts/ensure_test_env.sh
python -m ruff format --check src tests
python -m ruff check src tests
python -m mypy src
python -m pytest tests/application/test_faq_surface_compiler_contracts.py tests/interfaces/http/test_knowledge_surface_endpoints_contract.py tests/domain/project_plane/test_faq_legacy_guards.py -q
npm --prefix frontend run type-check
npm --prefix frontend run build
EOF

bash /tmp/faq_surface_finish_validate.sh
```

For full commit readiness also run:

```bash
cat << 'EOF' > /tmp/faq_surface_finish_full_gate.sh
#!/usr/bin/env bash
set -euo pipefail

cd /home/haku/crm_bot
bash dev_scripts/ensure_test_env.sh
bash dev_scripts/codex_extended_quality_gate.sh
EOF

bash /tmp/faq_surface_finish_full_gate.sh
```
