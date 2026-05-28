# Follow-up task: complete FAQ Retrieval Surface Compilation acceptance

## Context

The current commit replaces the primary FAQ bootstrap/flat preprocessing path with the new FAQ Retrieval Surface Compilation core:

- FAQ queue/upload path uses `GroqKnowledgeSurfaceCompiler`.
- Legacy FAQ preprocessor/fragments path is guarded/fail-fast.
- Surface compiler stages, source units, surfaces, relations, ownership, reassignments and merge decisions have persistence/read surfaces.
- Surface API and frontend surface panel exist.
- Surface publication creates/links runtime entries.
- Anti-bootstrap contract tests pass.

## Remaining acceptance gaps to close before claiming full original mega-spec completion

### Recon / audit artifact

- [ ] Add or reconstruct `reports/faq_surface_recon.md` with:
  - HTTP upload entry point.
  - `make_knowledge_preprocessor` wiring.
  - all old `preprocess(...)` call sites.
  - old prompt/parser call sites.
  - answer draft/candidate/canonical entry creation.
  - publish-ready path.
  - queue upload handler path.
  - progress/retry/cancel/report paths.
  - frontend `/fragments` callers/renderers.
  - retrieval/RAG-eval question source.

### DB / migrations

- [ ] Verify normalized surface tables and required indexes are present in migrations:
  - `knowledge_surface_compiler_runs`
  - `knowledge_surface_compiler_stages`
  - `knowledge_surface_source_units`
  - `knowledge_surfaces`
  - `knowledge_surface_relations`
  - `knowledge_surface_question_ownership`
  - `knowledge_surface_question_reassignments`
  - `knowledge_surface_merge_decisions`
- [ ] Add missing migration/indexes if any are absent.
- [ ] Add migration-level tests or SQL contract tests for required columns/indexes.

### Application ports completeness

- [ ] Verify/add all required bounded surface ports and methods:
  - `mark_previous_surface_runs_superseded_if_needed`
  - `update_surface_compiler_stage_status`
  - `update_surface_answer`
  - `list_surfaces_for_document`
  - `link_surface_to_answer_candidate`
  - `link_surface_to_canonical_entry`
  - `publish_surface`
  - `create_runtime_entry_from_surface`
  - `link_surface_publication`

### API / DTO completeness

- [ ] Expose merge decisions through API or embedded DTOs.
- [ ] Ensure `RetrievalSurfaceDto` contains:
  - parent/child keys
  - owned questions
  - reassigned questions
  - rejected questions
  - source refs/excerpts
  - source chunk indexes
  - linked runtime/canonical/candidate ids
- [ ] Regenerate/update OpenAPI generated schema if project workflow requires generated client schema.

### Frontend completeness

- [ ] Ensure FAQ UI uses surface API as primary result and never `/fragments` as primary FAQ result.
- [ ] Add/verify required filters:
  - All
  - Umbrella
  - Child
  - Document Upload
  - Curation
  - Retrieval Quality
  - Integration
  - Channel
  - Handoff / Limits
  - Other
- [ ] Render merge decisions and question reassignments/rejections explicitly.
- [ ] Add frontend tests for surface panel, filters, publish action, refresh persistence.

### Progress / retry / cancel

- [ ] Ensure progress/report includes latest surface run and stages.
- [ ] Ensure cancel marks active surface run/stages cancelled.
- [ ] Ensure retry creates a new run or retries failed stage without stale run mixing.
- [ ] Add tests for progress/retry/cancel surface lifecycle.

### Retrieval / RAG eval

- [ ] Prove runtime retrieval uses surface-owned questions as enrichment/question variants.
- [ ] Prove RAG eval loads the same production retrieval surface and sees owned questions.
- [ ] Add tests preventing umbrella from regaining child-specific owned questions.

### Real regression fixture

- [ ] Add full fixture containing:
  - Что это за продукт
  - Поисковая поверхность
  - Короткий ответ клиенту
  - Ручное слияние фрагментов
  - Скрытие, отклонение и архивирование
  - Telegram-ассистент
  - Клиентский web-widget
  - Негативные тесты
  - Ожидаемая тема
- [ ] Assert:
  - no standalone `Короткий ответ клиенту`
  - product overview is umbrella
  - search surface is separate
  - merge and hide/archive are separate
  - Telegram and web-widget are separate
  - negative tests split into useful surfaces
  - persisted surfaces/relations/ownership exist
  - API returns them
  - frontend renders them
  - publication preserves metadata

### Validation target

- [ ] Run full quality gate:
  - `ruff format --check src tests`
  - `ruff check src tests`
  - `mypy src`
  - full or focused backend pytest suite for knowledge/surface/upload/retrieval
  - `npm --prefix frontend run type-check`
  - `npm --prefix frontend run build`
