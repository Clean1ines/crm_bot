# FAQ Surface Recon (read-only)

## 1) HTTP upload entry point
- `src/interfaces/http/knowledge.py` endpoint upload uses `upload_knowledge_file(...)` with `preprocessor_factory=make_knowledge_preprocessor`.

## 2) Где вызывается/прокидывается `make_knowledge_preprocessor`
- `src/interfaces/http/knowledge.py`
- `src/interfaces/composition/knowledge_upload.py`

## 3) Вызовы `KnowledgePreprocessorPort.preprocess`
- `src/application/services/knowledge_ingestion_service.py` (batch processing/retry paths)
- `src/infrastructure/llm/knowledge_preprocessor.py` (implementation)

## 4) Выбор old fragments prompt
- `src/infrastructure/llm/knowledge_preprocessor.py` (legacy preprocessing prompt selection)

## 5) Вызовы `parse_preprocessing_payload`
- `src/infrastructure/llm/knowledge_preprocessor.py`
- `tests/domain/test_knowledge_preprocessing.py`

## 6) Где создаются drafts/candidates/canonical entries
- `src/application/services/knowledge_ingestion_service.py` (raw candidates, compilation runs, canonicalization/publish helpers)
- `src/infrastructure/db/repositories/knowledge_repository.py` (persistence)

## 7) Publish-ready path
- `src/application/services/knowledge_service.py` (`publish_document_ready_answers` queue enqueue)
- `src/application/services/knowledge_ingestion_service.py` (publish/apply)

## 8) Queue handler knowledge upload
- `src/infrastructure/queue/handlers/knowledge_upload.py`

## 9) Progress/retry/cancel/report
- HTTP: `src/interfaces/http/knowledge.py` (`/progress`, retry/cancel endpoints)
- Services: `src/application/services/knowledge_service.py`, `src/application/services/knowledge_ingestion_service.py`

## 10) Где frontend вызывает `/fragments`
- `frontend/src/shared/api/modules/knowledge.ts` (`knowledgeApi.fragments`)
- `frontend/src/pages/knowledge/KnowledgePage.tsx`

## 11) Где frontend показывает drafts/fragments
- `frontend/src/pages/knowledge/components/DraftsModal.tsx`
- `frontend/src/pages/knowledge/KnowledgePage.tsx`

## 12) Где retrieval/RAG-eval берёт questions
- Retrieval surface/runtime SQL and mappings in `src/infrastructure/db/repositories/knowledge_repository.py`
- RAG eval document entry loading in `src/infrastructure/db/repositories/rag_eval_repository.py`
