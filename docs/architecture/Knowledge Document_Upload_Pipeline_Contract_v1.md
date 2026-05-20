# Knowledge Document Upload Pipeline Contract v1

## Document status

**Статус:** целевой архитектурно-продуктовый контракт.

**Назначение:** зафиксировать жизненный цикл загрузки документа в crm_bot так, чтобы код, UI, очередь, БД, тесты и Codex-правки больше не трактовали pipeline как набор разрозненных кнопок.

**Главная проблема:** сценарий загрузки документа вырос до полноценного жизненного цикла знания, но состояние сейчас может быть размазано между `document.status`, `preprocessing_status`, `preprocessing_metrics.stage`, queue job status и frontend-local UI state. Из-за этого recovery actions (`retry`, `resume`, `publish_ready`, `cancel`) легко смешиваются, а Codex начинает угадывать поведение по соседним функциям.

**Главный принцип:** pipeline должен быть не договорённостью в чате, а исполняемым контрактом: state enum, command enum, transition table, validators, allowed actions resolver, progress view model и сценарные tests.

---

## 1. Core statement

Сценарий загрузки документа — это не просто `upload → embeddings`. Это цепочка:

```text
document upload
→ source extraction / chunking
→ source units
→ compiler batches
→ raw answer drafts
→ answer resolution / merge
→ canonical knowledge entries
→ publication
→ embeddings
→ retrieval surface
→ curation / retrieval review
```

Три формулы, которые должны быть прибиты гвоздями в код, тесты и UI:

```text
Raw drafts are not knowledge.
Resume is not publish-ready.
Processed means retrieval surface is truly ready.
```

---

## 2. Product contract

Пользователь должен понимать, где находится документ:

```text
1. Документ загружен
2. Документ нарезан на части
3. Черновики ответов извлечены
4. Черновики уплотняются / объединяются
5. Карточки знания публикуются
6. Поиск пересобирается
7. База готова к проверке
8. Карточки можно курировать вручную
```

UI обязан различать нормальный и аварийный путь.

### Нормальный путь

```text
Повторить проблемные части
→ Продолжить обработку
→ Уплотнение / merge
→ Публикация карточек знания
→ Пересборка поиска
→ Проверка / курация
```

### Аварийный путь

```text
Опубликовать черновики без уплотнения
```

Аварийная кнопка должна быть визуально вторичной и сопровождаться предупреждением:

```text
Часть документа может быть не объединена и не очищена от дублей.
Используйте только если нужно срочно опубликовать уже найденные ответы.
```

---

## 3. Product taxonomy

Нужно закрепить словарь и использовать его в UI, DTO, тестах и документации.

| Термин в UI     | Технический смысл                                               |
| --------------- | --------------------------------------------------------------- |
| Документ        | `knowledge_documents` row / uploaded source file                |
| Часть документа | source unit / compiler batch input                              |
| Черновик ответа | raw `AnswerCandidate` после LLM extraction                      |
| Карточка знания | `CanonicalKnowledgeEntry`                                       |
| Уплотнение      | answer resolution / merge / deduplication                       |
| Публикация      | запись canonical entries в БД как knowledge entries             |
| Поиск           | embeddings + retrieval surface                                  |
| Курация         | ручное редактирование / merge / hide / reject canonical entries |
| Проверка поиска | RAG Eval / Retrieval Review Console                             |

Запрещённые или опасные неоднозначные имена:

```text
publish_ready
ready_answers
fragments
chunks
parts
resume_pipeline
```

Допустимые точные имена:

```text
raw_answer_drafts
compiler_batches
source_units
canonical_entries
retry_failed_compiler_batches
resume_answer_resolution_pipeline
publish_raw_drafts_without_resolution
retighten_published_entries
```

---

## 4. State machine as domain contract

Нужен отдельный доменный модуль, например:

```text
src/domain/project_plane/knowledge_document_pipeline.py
```

Он должен содержать:

```text
KnowledgeDocumentPipelineState
KnowledgeDocumentPipelineCommand
KnowledgeDocumentPipelineAction
KnowledgeDocumentPipelineStep
KnowledgeDocumentPipelineError
resolve_pipeline_state(...)
allowed_actions_for_state(...)
validate_transition(...)
```

Это должен быть чистый domain/application-safe contract, без FastAPI, asyncpg, Redis, LLM SDK, filesystem side effects.

---

## 5. Pipeline states

Базовый набор состояний:

```text
uploaded
source_extraction_running
source_units_ready
compiler_running
compiler_partial_failed
compiler_completed
answer_resolution_pending
answer_resolution_running
answer_resolution_failed
answer_resolution_completed
publication_pending
publication_running
publication_completed
embedding_running
embedding_failed_retryable
embedding_failed_fatal
retrieval_surface_running
retrieval_surface_completed
processed
processed_with_warnings
partial_published
cancelled
failed_retryable
failed_fatal
```

Важно: `pending` в смысле queue/job нельзя смешивать с `waiting_for_user`.

Нужно явно различать:

```text
queued
running
waiting_for_user
completed
failed
```

`answer_resolution_pending` — это не queued/running. Это `waiting_for_user` или `ready_for_resume`.

---

## 6. One source of truth for state

Pipeline state должен вычисляться только через один resolver.

Запрещённый подход:

```python
if document.status == "processed":
    ...
```

Правильный подход:

```python
state = resolve_knowledge_document_pipeline_state(
    document=document,
    compiler_batches=batches,
    raw_candidates=candidates,
    canonical_entries=entries,
    active_jobs=jobs,
)

if state.is_processed:
    ...
```

Все endpoints, queue handlers, progress report и frontend actions должны опираться на этот resolver.

---

## 7. Commands model

Actions должны быть не случайными endpoint names, а командами доменной модели.

```text
RetryFailedCompilerBatches
ResumeKnowledgeCompilation
PublishRawDraftsWithoutResolution
CancelKnowledgeProcessing
RetightenPublishedEntries
OpenDraftReview
OpenCurationConsole
RunRetrievalReview
```

### Command semantics

#### RetryFailedCompilerBatches

Делает только:

```text
failed compiler batches
→ retry extraction
→ update raw answer drafts
→ if all completed: answer_resolution_pending
```

Не имеет права:

```text
publish
embed
update retrieval surface
mark document processed
```

#### ResumeKnowledgeCompilation

Делает:

```text
answer_resolution_pending
→ answer_resolution_running
→ publication_running
→ embedding_running
→ retrieval_surface_running
→ processed
```

Не имеет права:

```text
call publish_raw_drafts_without_resolution
silently no-op
raise NotImplemented
skip answer resolution
```

#### PublishRawDraftsWithoutResolution

Это fallback/аварийная команда.

Делает:

```text
raw answer drafts
→ canonical entries without answer resolution
→ partial_published or processed_with_warnings
```

Не должна называться `resume` или выглядеть как нормальный путь.

#### CancelKnowledgeProcessing

Останавливает активную обработку, но semantics зависят от текущей стадии.

---

## 8. Transition table

Переходы должны быть заданы как код, а не как текст в промпте.

Пример:

```python
ALLOWED_TRANSITIONS = {
    ("compiler_partial_failed", "retry_failed_compiler_batches"): "answer_resolution_pending",
    ("answer_resolution_pending", "resume_knowledge_compilation"): "answer_resolution_running",
    ("answer_resolution_pending", "publish_raw_drafts_without_resolution"): "partial_published",
    ("answer_resolution_running", "complete_answer_resolution"): "publication_running",
    ("publication_running", "complete_publication"): "embedding_running",
    ("embedding_running", "complete_embeddings"): "retrieval_surface_running",
    ("retrieval_surface_running", "complete_retrieval_surface"): "processed",
}
```

Нужен тест:

```text
test_all_pipeline_commands_have_explicit_transition
```

Ни один кодовый путь не должен менять stage вне transition table.

---

## 9. Ban ad-hoc stage strings

Нельзя писать stage строками где попало:

```python
metrics["stage"] = "answer_resolution_pending"
```

Нужно использовать enum:

```python
class KnowledgePipelineStage(StrEnum):
    COMPILER_PARTIAL_FAILED = "compiler_partial_failed"
    ANSWER_RESOLUTION_PENDING = "answer_resolution_pending"
    ANSWER_RESOLUTION_RUNNING = "answer_resolution_running"
    PUBLICATION_RUNNING = "publication_running"
    EMBEDDING_RUNNING = "embedding_running"
    PROCESSED = "processed"
```

Нужен architecture test, который запрещает новые stage-string literals вне whitelist-модуля.

---

## 10. Allowed actions must be backend-owned

Frontend не должен угадывать, какие кнопки показывать.

Progress endpoint должен возвращать backend-owned actions:

```json
{
  "state": "answer_resolution_pending",
  "state_version": 17,
  "allowed_actions": [
    {
      "id": "resume_processing",
      "label": "Продолжить обработку",
      "kind": "primary",
      "enabled": true
    },
    {
      "id": "publish_raw_drafts_without_resolution",
      "label": "Опубликовать черновики без уплотнения",
      "kind": "secondary_warning",
      "enabled": true
    }
  ]
}
```

UI только рендерит контракт. Он не должен сам вычислять, можно ли retry/resume/publish.

---

## 11. Progress view model

Progress response должен включать:

```text
document_id
state
state_version
state_hash
status
active_stage
recoverable
steps[]
allowed_actions[]
metrics
active_error
last_error
diagnostics
active_job_id
active_job_type
active_job_status
active_job_started_at
active_job_updated_at
recommended_next_action
```

### Steps

Stepper должен быть честным:

```text
1. Документ подготовлен
2. Части найдены
3. Черновики извлечены
4. Черновики уплотняются
5. Карточки публикуются
6. Поиск пересобирается
7. Готово к проверке
```

Каждый step имеет status:

```text
pending
running
completed
failed
skipped
partial
```

---

## 12. Step semantics contract

Каждый step должен иметь формальное определение.

```text
Документ подготовлен:
completed if source document row exists and upload metadata is valid

Части найдены:
completed if source units/source chunks exist

Черновики извлечены:
completed if all compiler batches completed and raw_candidates > 0
partial if some batches completed and some failed
failed if no candidates and compiler failed

Уплотнение:
pending if extraction completed and no canonical entries yet
running if state = answer_resolution_running
completed if answer resolution metrics exist and canonical entries exist
failed if answer resolution failed

Публикация:
running if canonical entries are being persisted
completed if canonical entries persisted
partial if raw drafts were published without resolution

Поиск:
running if embeddings/retrieval surface is being built
completed if retrieval surface rows exist for runtime published entries
failed_retryable if embedding provider failed after publication

Готово:
completed only when processed definition is satisfied
```

---

## 13. Definition of processed

`processed` должен означать строго:

```text
terminal pipeline state is processed
no active job
failed compiler batch count = 0
canonical entry count > 0
every runtime published entry has embedding text/vector
retrieval surface count matches runtime published entries
active_error is null
publication manifest exists or can be reconstructed
```

Если пользователь сделал fallback publish raw drafts без уплотнения, это не обычный `processed`, а:

```text
partial_published
```

или минимум:

```text
processed_with_warnings
```

---

## 14. Distinguish canonical publication and search readiness

Нельзя сливать в одну стадию:

```text
canonical entries persisted
```

и:

```text
retrieval surface ready
```

Возможны состояния:

```text
publication_completed
embedding_failed_retryable
published_but_search_not_ready
retrieval_surface_completed
```

KCC может быть доступна после publication, но runtime search может ещё быть не готов.

---

## 15. Partial success taxonomy

Нужно различать:

```text
partial_extraction_failed
partial_raw_drafts_available
partial_published_without_resolution
published_but_embedding_failed
processed_with_warnings
```

Это разные состояния, разные сообщения и разные действия.

---

## 16. Error model

Provider errors не должны быть raw exception strings.

Нужен typed error layer:

```text
llm_provider_over_capacity
llm_rate_limited
llm_timeout
llm_connection_error
llm_invalid_json
llm_schema_validation_error
embedding_provider_unavailable
embedding_vector_count_mismatch
unknown_llm_error
unknown_embedding_error
```

Поля ошибки:

```text
code
severity
retryable
user_message
technical_message
provider
model
status_code
safe_diagnostics
job_id
batch_index
timestamp
```

### Severity

```text
info
warning
recoverable_error
fatal_error
technical_diagnostic
```

Groq over capacity:

```text
code = llm_provider_over_capacity
severity = recoverable_error
retryable = true
user_message = "Провайдер LLM временно перегружен. Прогресс сохранён."
```

Raw provider JSON нельзя показывать как main UI error.

---

## 17. Active error vs last error

Нужно различать:

```text
active_error — текущая ошибка текущего состояния
last_error — историческая ошибка
diagnostics.errors[] — журнал
```

После успешного retry:

```text
active_error = null
last_error = previous provider error
state = answer_resolution_pending
```

UI никогда не должен показывать `last_error` как current fatal error.

---

## 18. Safe technical details panel

В UI нужна раскрывающаяся секция:

```text
Показать технические детали
```

Показывать можно:

```text
error_code
provider
model
status_code
safe_message
job_id
batch_index
timestamp
state
state_version
```

Запрещено показывать:

```text
API keys
raw secrets
giant provider payloads
full tracebacks as main text
```

---

## 19. Job locking

На один `document_id` может быть только одна активная pipeline command.

Перед enqueue любого действия нужно проверять:

```text
assert_no_active_knowledge_pipeline_job(document_id)
```

Команды под lock:

```text
retry_failed_compiler_batches
resume_processing
publish_raw_drafts_without_resolution
retighten
cancel
```

Иначе пользователь может нажать `retry`, `resume`, `publish fallback`, `cancel` почти одновременно.

---

## 20. Command idempotency

Команда с тем же `document_id + command + expected_state_hash` не должна создавать второй job.

Пример:

```text
resume_processing clicked twice
→ returns existing job
```

а не:

```text
two resume jobs
→ duplicate canonical entries
```

Рекомендуемый ключ:

```text
idempotency_key = document_id + command + expected_state_hash
```

---

## 21. Optimistic concurrency

Каждая mutation-команда должна отправлять:

```json
{
  "expected_state": "answer_resolution_pending",
  "expected_state_version": 17
}
```

Если backend уже перешёл дальше:

```text
409 state_conflict
```

UI должен refetch progress.

---

## 22. Dry-run command validation

Для каждой команды должен быть validator:

```text
validate_retry_failed_batches
validate_resume_processing
validate_publish_raw_drafts_without_resolution
validate_cancel_processing
validate_retighten_published_entries
```

`allowed_actions_for_state(...)` и endpoint перед enqueue должны использовать одни и те же validators.

Иначе UI говорит “можно”, а endpoint говорит “нельзя”.

---

## 23. Preflight before resume

Progress response или отдельный preflight должен возвращать blockers:

```json
{
  "can_resume": false,
  "blockers": [
    {
      "code": "failed_batches_remain",
      "message": "Сначала повторите 1 проблемную часть"
    }
  ]
}
```

Для `answer_resolution_pending` при валидном состоянии:

```json
{
  "can_resume": true,
  "blockers": []
}
```

---

## 24. Queue task registry contract

Любой новый task type должен пройти registry contract:

```text
defined constant
included in KNOWN_TASK_TYPES
handled by dispatcher
has handler
has handler test
has enqueue endpoint/service test
has payload validation test
```

Обязательный тест:

```text
test_all_known_task_types_are_dispatched_or_explicitly_external
```

---

## 25. Endpoint → command → task matrix

Должна быть единая матрица:

```text
POST /retry-failed-batches
→ RetryFailedCompilerBatches
→ retry_knowledge_failed_batches
→ handle_retry_knowledge_failed_batches
→ KnowledgeIngestionService.retry_failed_batches

POST /resume-processing
→ ResumeKnowledgeCompilation
→ resume_knowledge_processing
→ handle_resume_knowledge_processing
→ KnowledgeIngestionService.resume_processing

POST /publish-ready
→ PublishRawDraftsWithoutResolution
→ publish_knowledge_ready_answers
→ handle_publish_knowledge_ready_answers
→ KnowledgeIngestionService.publish_ready_answers

POST /cancel
→ CancelKnowledgeProcessing
→ repository cancel / active job cancellation

POST /retighten
→ RetightenPublishedEntries
→ retighten_knowledge_document
→ handler
→ KnowledgeIngestionService.retighten_document_answer_resolution
```

Эта матрица должна быть отражена в tests.

---

## 26. Data model / DB entities

Pipeline затрагивает минимум:

```text
knowledge_documents
knowledge_source_chunks
knowledge_compiler_runs
knowledge_compiler_batches
knowledge_answer_candidates
knowledge_entries
knowledge_entry_source_refs
knowledge_retrieval_surface
knowledge_entry_versions
knowledge_edit_actions
execution_queue
model_usage_events
```

---

## 27. DB/repository consistency guards

Нужно покрыть repository-level guards:

```text
retrieval_surface only for published/runtime entries
compiler batch cannot produce duplicate raw candidates on repeated retry
processed document must have completed publication/search metrics
merged/archived/hidden entries must not have retrieval_surface rows
entry_id unique in retrieval_surface
document_id + stable_key uniqueness for active entries where possible
```

Не всё можно выразить SQL constraint-ами, но repository transaction checks должны ловить несогласованность.

---

## 28. Publication manifest

После публикации нужен manifest:

```json
{
  "document_id": "...",
  "compiler_run_id": "...",
  "raw_candidate_count": 151,
  "canonical_entry_count": 46,
  "retrieval_surface_count": 46,
  "source_ref_count": 120,
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "embedding_text_version": "...",
  "published_at": "..."
}
```

`processed` должен сверяться с manifest или с reconstructable equivalent.

---

## 29. Entry lineage

Каждая canonical entry должна знать происхождение:

```text
source_document_id
source_unit_ids
compiler_run_id
compiler_batch_ids
raw_candidate_ids
answer_resolution_decision_id
source_refs
```

Это нужно для:

```text
Draft Review
KCC
manual merge
debugging
retry safety
audit
```

---

## 30. Answer resolution decision log

Answer resolution должен сохранять решения:

```text
candidate A + candidate B merged into entry X
candidate C kept separate
candidate D rejected noisy
candidate E absorbed into parent entry Y
```

Без этого ручная отладка merge становится гаданием.

---

## 31. Draft Compilation Review

Между raw drafts и KCC нужен отдельный слой:

```text
Draft Compilation Review
```

Он показывает:

```text
raw answer drafts
source unit
compiler batch
LLM extraction status
candidate title/question/answer
source refs
batch error
retry status
include/exclude draft
continue resolution
fallback publish selected drafts
```

KCC отвечает за canonical entries после публикации.

Draft Review отвечает за вопрос:

```text
что вообще извлеклось из документа до merge/publication?
```

---

## 32. Knowledge Curation Console boundary

KCC должна работать только с canonical entries.

```text
KCC available if canonical entries exist
KCC unavailable or empty if only raw drafts exist
```

Raw candidates не должны отображаться как production entries.

---

## 33. Manual intervention points

Pipeline должен явно иметь точки вмешательства:

```text
after extraction: review drafts
after resolution: review canonical draft entries
after publication: curation console
after retrieval eval: review search questions
```

Каждая точка должна иметь собственные actions и warnings.

---

## 34. Cancel policy

`cancel` должен иметь разную семантику по стадиям:

```text
compiler_running:
  stop remaining batches, keep drafts

answer_resolution_running:
  stop before publication if safe

publication_running:
  usually cannot cancel mid-transaction; wait or mark cancellation requested

embedding_running:
  stop after current batch if safe; canonical entries remain, search_not_ready

retrieval_surface_running:
  finish transaction or mark search_not_ready
```

Нужно различать:

```text
cancelled_after_extraction
cancelled_during_resolution
cancelled_after_publication_before_embeddings
```

---

## 35. Resume after cancel

Если пользователь отменил обработку, возможны разные resume-paths:

```text
cancelled_after_extraction
→ resume answer resolution

cancelled_during_resolution
→ restart answer resolution from raw candidates

cancelled_after_publication_before_embeddings
→ resume embeddings/retrieval surface
```

Это должно быть отдельной частью state machine, не “авось продолжится”.

---

## 36. Stuck job handling

Нужны состояния:

```text
running_stale
retryable_stuck
```

Например:

```text
job running > 30 minutes without progress update
→ show “Похоже, обработка зависла”
→ allow cancel/retry/reconcile
```

Progress должен показывать active job pointer.

---

## 37. Reconcile document state

Нужен сервис:

```text
reconcile_knowledge_document_pipeline_state(document_id)
```

Он проверяет:

```text
document.status = processed, but retrieval_surface empty
def stage = answer_resolution_pending, but canonical entries already exist
failed_batch_count = 0, but stage = extraction_partial_failed
published entries exist, but document.status = error
active_error stale after retry success
```

Он либо чинит безопасные случаи, либо возвращает diagnostics and recommended action.

---

## 38. Admin/dev inspect command

Нужен script или endpoint:

```text
inspect_knowledge_document_pipeline(document_id)
```

Вывод:

```text
document status
preprocessing_status
preprocessing_metrics.stage
active jobs
compiler batches by status
raw candidates count
canonical entries count
retrieval surface count
last errors
allowed actions
recommended next action
state consistency
```

Это должно стать первым инструментом при любой странной ошибке pipeline.

---

## 39. Document health endpoint

В продукте полезен endpoint:

```text
GET /knowledge/{document_id}/health
```

Возвращает:

```text
state consistency
missing embeddings
retrieval surface mismatch
failed batches
stale error
raw drafts count
canonical entries count
retrieval entries count
lineage completeness
source_refs completeness
```

---

## 40. Provider/model budget policy

Нужна явная политика:

```text
if request > selected_model_tpm:
  split batch smaller first?
  or fallback model?
  if fallback over capacity:
    retry/backoff
    then mark batch retryable failed
```

Сейчас fallback на большую модель может привести к over capacity и provider 503.

---

## 41. Adaptive batch splitting

Если запрос превышает лимит, предпочтительно рассмотреть:

```text
split batch into smaller compiler batches
```

особенно для markdown.

Это может быть лучше, чем сразу уходить на fallback model.

---

## 42. Retry budget

Retry должен иметь лимиты:

```text
max attempts per batch
max total retry time per document
max provider failures before stop
cooldown before user retry
backoff strategy
jitter
```

---

## 43. Human-readable recovery recommendation

Progress response должен возвращать:

```json
{
  "recommended_next_action": {
    "id": "retry_failed_batches",
    "reason": "1 часть не обработалась из-за перегрузки LLM"
  }
}
```

или:

```json
{
  "recommended_next_action": {
    "id": "resume_processing",
    "reason": "Все черновики готовы, можно продолжить уплотнение"
  }
}
```

---

## 44. Metrics for humans

Пользователь должен видеть не только технические counts:

```text
74 / 75
151 drafts
```

а смысл:

```text
74 из 75 частей обработаны
151 черновик найден
0 карточек знания опубликовано
Поиск ещё не пересобран
Следующий шаг: продолжить уплотнение
```

---

## 45. Pipeline event log

Нужен журнал:

```text
document_pipeline_events
```

Минимальные поля:

```text
document_id
from_state
to_state
command
job_id
actor
reason
error_code
metrics_snapshot
created_at
```

Пример нормального пути:

```text
compiler_partial_failed
→ retry_failed_batches
→ answer_resolution_pending
→ resume_processing
→ answer_resolution_running
→ publication_running
→ embedding_running
→ processed
```

Пример незаконного перехода:

```text
answer_resolution_pending → embedding_running
```

---

## 46. Golden scenario tests

Нужен pipeline simulator / scenario test:

```text
Scenario: Groq fails on batch 9 of 75
1. upload starts
2. 74 batches completed, 1 failed
3. progress says partial recoverable
4. retry failed batch succeeds
5. no embeddings called
6. state = answer_resolution_pending
7. resume clicked
8. answer resolution runs
9. publication runs
10. embeddings run
11. retrieval surface updated
12. processed
13. KCC sees canonical entries
```

Это главный regression test для инцидента.

---

## 47. Regression fixtures

Нужны fixtures:

```text
tests/fixtures/knowledge/ai_manager_knowledge_base_minimal.md
tests/fixtures/knowledge/ai_manager_knowledge_base_many_sections.md
tests/fixtures/knowledge/provider_failure_batch_9.json
tests/fixtures/knowledge/duplicate_answers.md
tests/fixtures/knowledge/empty_sections.md
tests/fixtures/knowledge/partial_publish.json
```

Типы документов:

```text
маленький markdown
большой markdown
документ с дублями
документ с пустыми секциями
документ с batch failure
документ с provider 503
документ с partial publish
```

---

## 48. Executable invariants

Ключевые tests:

```text
retry_failed_batches never calls _persist_stage_e_compiler_outputs
retry_failed_batches never calls embed_batch
retry_failed_batches never marks processed

resume_processing calls shared post-extraction pipeline
resume_processing never calls publish_ready_answers
resume_processing rejects failed batches
resume_processing rejects pending/processing batches
resume_processing rejects ambiguous compiler_run_id
resume_processing rejects no raw candidates

publish_raw_drafts_without_resolution is explicitly partial/fallback
processed means retrieval surface is built
hidden/rejected/merged entries are not searchable
no endpoint enqueues wrong task type
all queue task types are known and dispatched
no user-facing error contains raw provider payload
```

---

## 49. Anti-Codex architecture tests

Тесты против типичных ошибок:

```text
test_retry_failed_batches_does_not_import_embedding_service
test_retry_failed_batches_does_not_call_persist_stage_e
test_resume_processing_does_not_call_publish_ready_answers
test_publish_ready_label_contains_without_resolution_when_resolution_pending
test_no_endpoint_enqueues_wrong_task_type
test_all_queue_task_types_are_known_and_dispatched
test_no_user_facing_error_contains_raw_provider_payload
test_processed_requires_retrieval_surface_rows
test_no_ad_hoc_pipeline_stage_literals_outside_contract_module
```

---

## 50. DB state → UI state contract tests

Пример:

```text
Given DB state:
  batches completed
  raw candidates exist
  canonical entries absent
  stage = answer_resolution_pending

Progress response:
  state = answer_resolution_pending
  action resume_processing enabled
  action publish_raw_drafts_without_resolution enabled secondary_warning
  retry disabled/absent
  cancel absent
  title = Проблемные части повторены
```

---

## 51. Frontend action rendering tests

Нужна pure view-model function:

```text
getKnowledgeProgressActionsViewModel(report)
```

И tests по состояниям:

```text
compiler_partial_failed
answer_resolution_pending
answer_resolution_running
publication_running
embedding_failed_retryable
processed
partial_published
```

---

## 52. Single writer guarantee

Кто имеет право менять pipeline state?

Целевое правило:

```text
только PipelineStateService / KnowledgeDocumentPipelineService меняет stage/status/actions
```

Не должны напрямую менять state:

```text
HTTP routes
queue handlers
frontend
random repository methods
```

Они должны вызывать единый state transition service.

---

## 53. Files involved in current architecture

### Frontend

```text
frontend/src/pages/knowledge/KnowledgePage.tsx
frontend/src/shared/api/modules/knowledge.ts
frontend/src/pages/rag-eval/components/KnowledgeCurationConsole.tsx
frontend/src/shared/api/modules/knowledgeCuration.ts
```

### HTTP

```text
src/interfaces/http/knowledge.py
src/interfaces/http/knowledge_curation.py
src/interfaces/http/app.py
```

### Application

```text
src/application/services/knowledge_service.py
src/application/services/knowledge_ingestion_service.py
src/application/services/knowledge_curation_service.py
src/application/dto/knowledge_dto.py
```

### Queue

```text
src/infrastructure/queue/job_types.py
src/infrastructure/queue/job_dispatcher.py
src/infrastructure/queue/handlers/knowledge_upload.py
src/infrastructure/queue/handlers/knowledge_failed_batches.py
src/infrastructure/queue/handlers/knowledge_resume_processing.py
src/infrastructure/queue/handlers/knowledge_publish_ready.py
src/infrastructure/queue/handlers/knowledge_retighten.py
```

### Infrastructure / DB / LLM

```text
src/infrastructure/db/repositories/knowledge_repository.py
src/infrastructure/llm/knowledge_preprocessor.py
src/infrastructure/llm/embedding_service.py
```

### Domain

```text
src/domain/project_plane/knowledge_compilation.py
src/domain/project_plane/knowledge_curation.py
src/domain/project_plane/knowledge_preprocessing.py
src/domain/project_plane/knowledge_retrieval_surface.py
src/domain/project_plane/embedding_text.py
```

### Target new domain contract

```text
src/domain/project_plane/knowledge_document_pipeline.py
```

---

## 54. Current architecture roles

### `KnowledgePage.tsx`

Renders upload/progress/actions/drafts. Should not infer allowed actions locally.

### `knowledge.ts`

Frontend API module. Must map action ids to exact backend endpoints.

### `knowledge.py`

HTTP boundary. Must enqueue correct task for each command.

### `KnowledgeService`

API-facing orchestration and progress report. Should delegate state/action logic to domain resolver.

### `KnowledgeIngestionService.process_document`

Primary upload pipeline.

### `KnowledgeIngestionService.retry_failed_batches`

Extraction recovery only. No publication. No embeddings. No processed.

### `KnowledgeIngestionService.resume_processing`

Normal continuation from `answer_resolution_pending` through shared post-extraction pipeline.

### `KnowledgeIngestionService.publish_ready_answers`

Fallback raw draft publication without resolution.

### `_run_answer_resolution_publication_pipeline`

Single normal path from raw candidates to canonical published entries.

### `_persist_stage_e_compiler_outputs`

Persistence boundary for canonical entries, embeddings and retrieval surface.

### `KnowledgeRepository`

DB boundary. Must enforce transaction consistency and row normalization.

### `KnowledgeCurationConsole`

Manual work over canonical entries only.

---

## 55. Release discipline

For P0 state-machine fixes, do not combine everything into one huge PR.

Recommended sequence:

```text
1. Hotfix:
   retry no longer publishes/embeds/processed

2. Resume:
   true shared post-extraction resume pipeline

3. Provider errors:
   typed retryable/fatal provider error policy

4. Pipeline contract:
   state enum, command enum, transition table, validators

5. UI:
   backend-owned allowed actions, stepper, safe diagnostics

6. Draft Review:
   pre-publication review panel

7. Observability:
   pipeline events, health endpoint, inspect/reconcile tools
```

If one PR touches these files:

```text
knowledge_ingestion_service.py
knowledge_service.py
knowledge.py
queue handlers knowledge_*
knowledge_repository.py
KnowledgePage.tsx
```

then pipeline contract tests must run.

---

## 56. PR checklist for any pipeline change

```text
[ ] State enum updated if new state introduced
[ ] Command enum updated if new command introduced
[ ] Transition table updated
[ ] Allowed actions resolver updated
[ ] Endpoint → command → task matrix updated
[ ] Task type registry test passes
[ ] Progress view model tests updated
[ ] No raw provider payload in user-facing error
[ ] Retry does not publish/embed/processed
[ ] Resume does not call publish fallback
[ ] Processed definition still holds
[ ] Retrieval surface excludes hidden/archived/merged entries
[ ] Frontend renders backend-owned actions
[ ] No ad-hoc stage strings added
[ ] Golden scenario test still passes
[ ] No reports/ markdown files created unless explicitly requested
```

---

## 57. Codex operating rule

Codex should not be asked:

```text
fix retry
fix resume
fix upload pipeline
```

Instead, ask:

```text
Implement command RetryFailedCompilerBatches through the explicit transition table.
It must have no transition to publication/embedding/processed.
Update executable invariants and scenario tests.
```

or:

```text
Implement command ResumeKnowledgeCompilation from state answer_resolution_pending.
It must call the shared post-extraction pipeline and must not call PublishRawDraftsWithoutResolution.
```

Codex must obey contract, not infer architecture.

---

## 58. Final target architecture

```text
Frontend
  KnowledgePage
    renders ProgressViewModel from backend
    sends explicit commands with expected_state_version

HTTP
  receives command
  validates project access
  calls KnowledgeService command method

Application
  KnowledgeService
    resolves current pipeline state
    validates command preflight
    enqueues queue task with idempotency key

Queue
  dispatcher maps task type to handler
  handler validates payload
  handler calls KnowledgeIngestionService

Domain
  KnowledgeDocumentPipelineState
  KnowledgeDocumentPipelineCommand
  transition table
  allowed actions resolver
  validators

Ingestion
  retry_failed_batches = extraction recovery only
  resume_processing = normal continuation
  publish_raw_drafts_without_resolution = fallback only
  process_document = primary pipeline

Persistence
  repository transactionally persists source chunks, batches, candidates, entries, source refs, embeddings, retrieval surface

Observability
  document_pipeline_events
  health endpoint
  inspect/reconcile tool

Product UI
  progress stepper
  draft review
  curation console
  retrieval review
```

---

## 59. Main non-negotiable invariants

```text
1. Raw drafts are not knowledge.
2. Source chunks are not runtime entries.
3. Retry failed batches only retries extraction/compiler batches.
4. Retry never publishes.
5. Retry never builds embeddings.
6. Retry never marks processed.
7. Resume is the normal continuation path through answer resolution / merge.
8. Resume never calls fallback publish.
9. Fallback publish is explicit and labelled as without resolution.
10. Canonical entries must be grounded in source refs.
11. Embeddings only build for finalized canonical entries.
12. Retrieval surface only includes published/runtime entries.
13. Hidden/rejected/archived/merged entries are not searchable.
14. Processed means retrieval surface is truly ready.
15. Active error is not historical error.
16. UI actions are backend-owned.
17. Queue task types are registered, dispatched and tested.
18. Commands are idempotent.
19. State transitions are explicit.
20. No stage strings outside the pipeline contract module.
```

---

## 60. Implementation priority

### Immediate

```text
1. Finish current PR technical blockers.
2. Ensure resume handler passes preprocessor_factory.
3. Ensure handler maps errors correctly.
4. Rebase/merge from main.
5. Run focused backend/frontend checks.
```

### Next

```text
1. Create knowledge_document_pipeline.py.
2. Move stage/command/action enums there.
3. Implement transition table.
4. Implement allowed actions resolver.
5. Make processing_report use resolver.
6. Add anti-Codex tests.
```

### Then

```text
1. Provider error policy.
2. Golden scenario tests.
3. Draft Compilation Review.
4. Pipeline event log.
5. Health/reconcile/inspect tools.
6. UI stepper.
```

---

## Closing

Эта система уже не “загрузка документа”. Это lifecycle engine для бизнес-знания.

Чтобы больше не возвращаться к одним и тем же ошибкам, pipeline должен перестать быть набором функций и стать контрактом:

```text
state → command → validated transition → job → stage → event → progress view
```

И только после этого Codex перестанет гадать.
