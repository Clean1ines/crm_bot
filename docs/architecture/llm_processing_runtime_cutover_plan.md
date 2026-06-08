# LLM Processing Runtime Cutover Plan

## 0. Назначение документа

Этот документ фиксирует целевой cutover Workbench LLM processing на единый `LLM Processing Runtime`.

Цель — прекратить развитие ad-hoc логики вокруг Prompt A, Groq adapter, fallback chain, lease TTL, split и queue handler как самостоятельных production-механик.

Новый runtime должен стать единственным местом, где решаются:

- выбор модели;
- выбор Groq account/key/organization;
- обработка TPM/RPM/RPD/TPD;
- retry/fallback policy;
- JSON/schema validation;
- empty claims confirmation;
- oversized split;
- lease lifecycle;
- usage/cost accounting;
- stage readiness;
- frontend-visible processing state;
- переиспользование LLM/runtime логики для Workbench и клиентских ответов.

Prompt A, Prompt C, последующие этапы кластеризации/консолидации и ответы клиентам должны использовать один и тот же runtime contract.

---

## 1. Главная проблема текущего состояния

Текущий Workbench processing уже реализует часть правильной архитектуры, но логика распределена неправильно.

Сейчас фактически существует такой path:

```text
section worker
→ Prompt A generator
→ WorkbenchPromptAFallbackLlmJsonInvocationAdapter
→ Groq/Qwen invocation
→ fallback внутри Prompt A generator
→ oversized split внутри queue handler
→ exception bubble-up
→ leased item может остаться в LEASED до TTL
→ верхний execution_queue job видит blocked_by_leases

Это должно быть заменено на:

workflow stage
→ creates LlmTask
→ LLM Processing Runtime
→ RoutePlanner
→ QuotaManager
→ ProviderAdapter
→ Validator
→ SplitPolicy
→ UsageRecorder
→ WorkItemTransitionService
→ stage outcome

LLM provider exception не должен быть нормальным способом управления workflow. Он должен превращаться в LlmTaskOutcome.

Исключения допускаются только для настоящих broken invariants:

отсутствующий документ;
невозможный status transition;
сломанная схема БД;
отсутствующий обязательный prompt contract;
повреждённое состояние workflow, которое нельзя безопасно интерпретировать.
2. Стратегическое решение

Мы не делаем минимальный фикс Prompt A.

Мы выполняем cutover на новый LLM Processing Runtime.

Старый Workbench LLM path не развивается.

Запрещено добавлять новую production-логику в:

Prompt A generator;
Groq/Qwen adapter;
queue handler workbench_parallel_processing.py;
произвольные места, которые напрямую меняют status queue item;
frontend как способ скрыть backend lifecycle bug.

Старый код может временно использоваться только как adapter/reference во время cutover.

Старый код не должен остаться равноправным production path.

3. Output size policy

Мы не пытаемся точно предсказывать размер LLM output.

Точное определение будущего output невозможно.

Runtime может оценивать input size.

Для output используется только консервативное правило:

Без специальных доказательств считаем,
что output может быть не меньше размера source section без system prompt.

Это не prediction, а conservative assumption.

Разрешено использовать:

input token estimate;
char count;
source section size;
known model context window;
known model output limits;
historical failure signals.

Запрещено строить архитектуру на предположении, что output можно точно оценить заранее.

Запрещено проектировать policy так, будто output гарантированно будет маленьким.

4. Render/free-tier CPU/RAM как проектное ограничение

Текущий deployment/resource context ограничен. Известный ориентир пользователя: free-tier лимит около 512 МБ.

Пользователь пока не знает, к чему именно относится этот лимит в конкретной инфраструктуре и как правильно проектировать под него.

Поэтому этот документ не утверждает конкретную готовую реализацию resource scheduler.

Но архитектура обязана учитывать, что память и CPU не бесконечны.

4.1. Что может потреблять память

Даже если LLM работает снаружи через Groq API, локальный backend всё равно потребляет память.

В один process/service могут попасть:

Python runtime;
импортированные backend-модули;
FastAPI приложение;
queue worker, если он запущен в том же процессе/сервисе;
async event loop;
HTTP clients;
DB/Redis connection pools;
загруженный документ;
source units/sections;
prompt strings;
raw LLM outputs;
parsed JSON payloads;
validation errors;
embedding arrays;
cluster candidates;
временные списки задач;
runtime metrics;
logging buffers;
frontend state/read-side payloads.

Главный риск:

Система может упасть не потому, что LLM считается локально,
а потому что backend держит слишком много промежуточных данных в памяти.
4.2. Что может потреблять CPU

CPU-bound операции:

парсинг документов;
markdown/pdf/excel preprocessing;
механический split;
JSON validation;
дедупликация;
hashing;
embedding preparation;
clustering;
сортировки больших списков;
построение preview/read-side state;
подготовка frontend processing state.

Если эти операции выполняются внутри web process без ограничений, они могут:

блокировать HTTP-запросы;
замедлять frontend polling;
вызывать timeout;
увеличивать память;
ломать UX обработки документа;
приводить к worker crash.
4.3. Архитектурные запреты под ограниченные ресурсы

Нельзя:

держать весь pipeline state только в памяти;
загружать все секции документа без batch limit;
делать unbounded asyncio.gather по всем задачам;
хранить все raw LLM outputs в process memory;
строить все embeddings/cluster candidates одним большим списком без лимита;
пересчитывать frontend processing state дорогим обходом всего workflow на каждый запрос;
запускать тяжёлую document processing операцию внутри request/response handler;
смешивать HTTP responsiveness и тяжёлую background work без явного контроля;
полагаться на долгоживущие in-memory состояния как на источник истины.
4.4. Целевые правила проектирования

Правила:

1. Persist early, resume often.
2. Любая стадия должна быть возобновляемой из БД.
3. Batch size должен быть ограничен конфигом.
4. Parallelism должен быть ограничен конфигом.
5. Queue polling должен иметь лимит.
6. Embedding batch должен иметь лимит.
7. Cluster fan-in должен иметь лимит.
8. Raw output должен сохраняться/сбрасываться, а не жить в памяти.
9. Frontend state должен читаться из read-side/агрегатов, а не пересчитываться дорого.
10. Runtime должен быть устойчивым к worker restart.
4.5. Нужные runtime-настройки

Целевые настройки:

WORKBENCH_MAX_PARALLEL_LLM_TASKS_PER_PROCESS
WORKBENCH_MAX_SECTIONS_LOADED_PER_BATCH
WORKBENCH_MAX_SOURCE_UNIT_CHARS_IN_MEMORY
WORKBENCH_MAX_RAW_OUTPUT_BYTES_IN_MEMORY
WORKBENCH_MAX_EMBEDDING_BATCH_SIZE
WORKBENCH_MAX_CLUSTER_ITEMS_IN_MEMORY
WORKBENCH_MAX_TREE_REDUCE_FANIN
WORKBENCH_DB_POOL_SIZE
WORKBENCH_QUEUE_POLL_BATCH_SIZE
WORKBENCH_FRONTEND_STATE_CACHE_SECONDS

Эти значения не должны быть захардкожены в бизнес-логике.

Они должны быть частью runtime config.

4.6. Минимальная observability по ресурсам

Желательные метрики:

process RSS memory, если доступно;
active LLM task count;
active document processing count;
loaded source unit count per operation;
embedding batch size;
cluster size;
queue backlog counts;
duration per stage;
worker crash / timeout / memory pressure, если detectable.

Этот раздел не требует немедленно идеально реализовать resource scheduler.

Но он запрещает проектировать новый runtime так, будто память, CPU и длительность процесса бесконечны.

5. Source Unit / Document Split Domain

Split становится доменной подсистемой, а не helper-функцией внутри queue handler.

Целевая модель:

Document
→ SourceUnit
→ Section
→ Subsection
→ Split lineage

Markdown — только один из input adapters.

Будущие форматы:

Markdown;
PDF;
Excel/table documents;
HTML;
Plain text;
CRM/live data.

Целевая сущность:

SourceUnit
- source_unit_id
- project_id
- document_id
- parent_source_unit_id
- source_format
- unit_kind
- ordinal
- heading_path
- title
- raw_text
- normalized_text
- source_refs
- split_level
- split_reason
- char_count
- estimated_input_tokens
- status
- created_at
- updated_at

Split должен работать в двух местах.

5.1. Initial document segmentation

На этапе загрузки документа parser/splitter обязан нарезать документ на source units/sections так, чтобы они были пригодны для LLM processing с учётом известных лимитов.

Это не “preflight before request”, а именно часть document ingestion / segmentation.

5.2. Runtime oversized fallback

Если уже во время LLM execution все допустимые модели/маршруты упёрлись в REQUEST_TOO_LARGE или OUTPUT_TOO_LARGE, runtime создаёт дочерние source units.

parent source unit
→ SPLIT_SUPERSEDED
→ child source units
→ child work items READY for same stage/task kind

Split parent не должен записываться как successful empty claims.

Нужен отдельный outcome:

SPLIT_CREATED
6. Prompt A Contract

Prompt A — deliberately shallow extraction stage.

Он не обязан строить онтологию, triples и canonical registry.

Prompt A извлекает локальные evidence-grounded claim observations из одной source unit / section.

Выход Prompt A:

claim_observations:
  - claim
  - granularity
  - evidence_block
  - possible_questions
  - exclusion_scope

Допустимые дополнительные technical fields:

warnings
metrics

Prompt A должен:

извлекать claims;
сохранять связь с exact evidence block;
предлагать possible user questions;
указывать exclusion scope;
не перегружаться онтологическими задачами.

Prompt A не должен:

выбирать модель;
выбирать API key;
решать fallback;
делать split;
управлять lease;
считать quota;
выполнять Prompt C merge;
строить полноценный canonical registry.
7. Prompt C Contract

Prompt C — это intent-centered claim/surface consolidation.

Prompt C не является отдельной сущностью рядом с cluster consolidation.

Prompt C и есть смысловой механизм merge/consolidation claims/surfaces вокруг одинаковых пользовательских intent’ов.

Его задача:

Найти facts/claims/surfaces, которые отвечают на один и тот же user intent,
даже если они пришли из разных Prompt A outputs и разных source sections.

Prompt C получает набор локальных claims/observations, обычно из разных секций, и решает:

какие claims отвечают на один и тот же пользовательский intent;
какие claims являются дублями;
какие claims являются уточнениями друг друга;
какие claims конфликтуют;
какие claims нужно объединить;
какие claims достаточно самодостаточны и остаются без изменений;
какие possible_questions нужно объединить/очистить;
какой exclusion_scope нужно сохранить, сузить или расширить;
какой evidence_block или набор evidence references должен поддерживать итоговый claim/surface.

Prompt C на выходе возвращает не “абстрактную онтологию поверх Prompt A”, а обновлённые самодостаточные claims/surfaces.

Выход Prompt C включает поля Prompt A:

claim
granularity
evidence_block / evidence_refs
possible_questions
exclusion_scope

И добавляет/уточняет richer semantic fields:

canonical_intent
surface_kind
scope
relations
triples / semantic_edges
merge_decision
merged_from_claim_refs
conflict_notes
confidence
review_flags

Prompt C может оставить claim без изменений, если он уже самодостаточен.

Prompt C может вернуть один consolidated claim/surface на несколько локальных Prompt A observations, если они отвечают на один user intent.

Prompt C обязан оставлять claims раздельно, если intents отличаются.

Prompt C — основной этап, где локальные observations превращаются в production-ready или review-ready semantic surfaces.

Важно:

Prompt C не просто создаёт metadata поверх Prompt A.
Prompt C возвращает обновлённые self-contained claims/surfaces.
8. LLM Task Runtime

Все LLM-вызовы должны идти через LlmTaskExecutor.

Целевая сущность:

LlmTask
- task_id
- task_kind
- project_id
- document_id
- source_unit_id
- section_id
- cluster_id
- client_id
- prompt_id
- prompt_version
- input_payload
- output_contract
- candidate_model_policy
- candidate_account_policy
- retry_policy
- validation_policy
- split_policy
- idempotency_key
- status
- created_at
- updated_at

Целевые task kinds:

CLAIM_OBSERVATIONS
CLAIM_SURFACE_CONSOLIDATION
CLIENT_ANSWER_GENERATION
RAG_EVALUATION

Целевой outcome:

LlmTaskOutcome
- status
- parsed_payload
- raw_text
- route_attempts
- usage
- error_kind
- wait_until
- split_request
- validation_errors
- metrics

Статусы outcome:

SUCCESS
SUCCESS_EMPTY_CONFIRMED
WAITING_FOR_MINUTE_LIMIT
WAITING_FOR_DAILY_RESET
RETRYABLE_FAILED
VALIDATION_RETRY_REQUIRED
SPLIT_REQUIRED
SPLIT_CREATED
TERMINAL_FAILED
CANCELLED

Provider/API failures должны быть результатами, а не необработанными workflow exceptions.

9. Model / Account Catalog

Модели и аккаунты должны быть описаны явно.

Целевая модель профиля:

LlmModelProfile
- provider
- model_id
- quality_tier
- context_window_tokens
- max_output_tokens
- rpm_limit
- tpm_limit
- rpd_limit
- tpd_limit
- supports_json_mode
- supports_reasoning_off
- enabled
- fallback_rank
- notes

Целевая модель account/key slot:

LlmProviderAccount
- provider_account_id
- provider
- organization_label
- api_key_ref
- enabled
- priority
- daily_reset_policy

Даже если физические ключи пока живут в env, runtime должен мыслить ими как capacity slots.

10. Quota Manager / Limit Ledger

Нужен runtime-сервис:

LlmQuotaManager

Он отвечает на вопрос:

Можно ли сейчас выполнить task X моделью M через account A?

Решения:

ALLOW
WAIT_UNTIL
TRY_OTHER_ACCOUNT
TRY_OTHER_MODEL
DAILY_EXHAUSTED
CAPACITY_UNKNOWN

Целевая quota state:

LlmQuotaWindow
- provider_account_id
- model_id
- minute_window_started_at
- requests_used_this_minute
- tokens_used_this_minute
- day_window_started_at
- requests_used_today
- tokens_used_today
- unavailable_until
- unavailable_reason
- last_limit_error_kind
- updated_at

Политика лимитов:

TPM/RPM → wait 60s or route another available account
RPD/TPD → mark route unavailable until reset, try another account/model
REQUEST_TOO_LARGE → larger model or split
OUTPUT_TOO_LARGE → fallback or split
INVALID_JSON → retry policy
SCHEMA_INVALID → retry policy
EMPTY_CLAIMS → secondary model once, then confirmed empty
NETWORK_ERROR → retry/reroute policy
AUTH_ERROR → disable account/key and surface operational alert
11. Daily limit exhaustion user-choice flow

Когда все основные routes для текущей стадии заблокированы дневными лимитами, workflow не должен молча падать, бесконечно ретраиться или создавать иллюзию обычной обработки.

Дневные лимиты:

RPD
TPD
provider/account/model daily exhaustion

Обязательное поведение:

1. Пометить исчерпанные provider account/model routes как unavailable until reset.
2. Сохранить незавершённые work items как deferred/pending, а не failed.
3. Перевести processing state в:
   REQUIRES_USER_CHOICE_DAILY_LIMIT_EXHAUSTED
4. Показать на фронтенде:
   - affected stage;
   - сколько work items осталось;
   - какие группы routes исчерпаны;
   - когда возможно auto-resume, если это известно.
5. Предложить пользователю два явных выбора:
   A. Продолжить на низкокачественной fallback-модели, например llama-3.1-8b-instant.
   B. Ждать восстановления дневных лимитов и автоматически продолжить завтра.

Если пользователь выбирает низкокачественную fallback-модель:

- сохранить user decision;
- пометить stage как degraded_quality_continuation;
- показать предупреждение, что качество извлечения знаний может быть ниже;
- предупредить, что следующие этапы не рекомендуется продолжать без review;
- записать это решение в processing metadata.

Если пользователь выбирает auto-resume:

- оставить работу deferred до reset;
- не жечь attempts;
- не делать бессмысленные retry;
- frontend показывает waiting_for_daily_reset и resume target, если он известен.

Это обязательная часть runtime, потому что free-tier daily limits являются нормальным рабочим условием системы.

12. Minute limits: TPM/RPM

Минутные лимиты не равны дневным.

Для TPM/RPM:

TPM/RPM → ждать около 60 секунд ИЛИ перекинуть задачу на другой доступный account/key.

Минутный лимит не должен автоматически запускать fallback на другую модель, если это не разрешено отдельной политикой.

Причина:

Fallback-модели могут иметь более жёсткие дневные лимиты.
Их нужно беречь для request-too-large/output-too-large/model-capacity ситуаций,
а не тратить на минутный cooldown.

Незавершённая работа при минутном лимите должна оставаться доступной для перераспределения:

на другие accounts/keys сразу;
на тот же account/key после cooldown;
без terminal failure;
без потери lease visibility.
13. Переход от четырёх фиксированных очередей к capacity pool

Текущая ментальная модель:

lane 1 → Groq account/org/key 1
lane 2 → Groq account/org/key 2
lane 3 → Groq account/org/key 3
lane 4 → Groq account/org/key 4

Целевая модель runtime:

pending LLM tasks
+ provider account capacity pool
+ model capacity pool
+ quota manager
→ route planner выбирает лучший доступный route

Work item не должен навсегда быть прибит к одному lane/account, если другой route может безопасно выполнить задачу.

Инварианты:

- одна task не может выполняться конкурентно несколькими accounts;
- task_id + attempt_id + lease_token защищают idempotency;
- запись результата разрешена только если lease/attempt всё ещё актуален;
- daily-limited routes исключаются из выбора до reset;
- minute-limited routes возвращаются в выбор после cooldown;
- worker affinity может быть временной оптимизацией, но не canonical scheduling model.

Старая модель четырёх lane может временно оставаться implementation detail во время cutover.

Она не должна остаться целевой моделью планировщика.

14. Empty Claims Policy

Empty claims не должны молча считаться успешной обработкой с первой попытки.

Prompt A policy:

primary model returned empty claim_observations
→ run secondary model once
→ if secondary also returns empty claim_observations:
     SUCCESS_EMPTY_CONFIRMED
     persist valid empty artifact
     metric empty_claims_confirmed=true
→ if secondary returns non-empty:
     SUCCESS

Это должно быть доказано тестом.

Если локальная разведка покажет, что это уже реализовано, нужно проверить, что реализация находится в правильном runtime/policy слое, а не случайно спрятана в Prompt A parser.

15. Validation Runtime

Валидация должна быть отдельным runtime layer.

LlmOutputValidationService

Контракты:

PromptAClaimObservationsContract
PromptCClaimSurfaceConsolidationContract
ClientAnswerContract

Prompt A validation:

JSON object;
allowed payload keys;
claim_observations list;
each observation object;
required non-empty claim;
required granularity;
required exact evidence_block;
possible_questions list of strings;
optional exclusion_scope;
source-language sanity checks where applicable.

Prompt C validation:

JSON object;
consolidated surfaces list;
each surface includes Prompt A fields on output;
each surface has canonical intent;
merge lineage;
evidence refs;
possible questions;
exclusion scope;
semantic relations/triples where required;
review flags;
confidence.
16. Network/provider error taxonomy

Network/provider failures должны классифицироваться точнее, чем generic provider error.

Обязательная taxonomy:

NETWORK_REQUEST_NOT_SENT
NETWORK_TIMEOUT
NETWORK_NO_RESPONSE
NETWORK_CONNECTION_ERROR
PROVIDER_5XX
PROVIDER_429_UNKNOWN
PROVIDER_AUTH_ERROR
PROVIDER_BAD_REQUEST
PROVIDER_RESPONSE_MALFORMED
PROVIDER_UNKNOWN_ERROR

Обязательное поведение:

NETWORK_REQUEST_NOT_SENT → retry без списания quota, если provider usage отсутствует
NETWORK_TIMEOUT → retry/reroute с учётом idempotency и lease state
NETWORK_NO_RESPONSE → retry/reroute, сохранить attempt metadata
NETWORK_CONNECTION_ERROR → retry with backoff или route another account
PROVIDER_5XX → retry/backoff/reroute
PROVIDER_429_UNKNOWN → уточнить classification, иначе conservative cooldown
PROVIDER_AUTH_ERROR → disable account/key и surface operational alert
PROVIDER_BAD_REQUEST → usually terminal, если это не size/contract case
PROVIDER_RESPONSE_MALFORMED → validation retry policy
PROVIDER_UNKNOWN_ERROR → limited retry, затем recoverable failure

Каждый failed attempt должен записывать:

error_kind;
provider;
model;
account/key slot if known;
started_at;
finished_at;
duration_ms;
retry_after/cooldown if known;
whether provider usage was reported.
17. Lease / Work Item State Machine

Lease lifecycle must be strict.

Allowed work item statuses:

READY
LEASED
DEFERRED
COMPLETED
SPLIT_SUPERSEDED
RETRYABLE_FAILED
TERMINAL_FAILED
CANCELLED

Invariant:

Worker must not exit while leaving item LEASED unless work is still actively running and lease has not expired.

Allowed transition methods:

lease_ready_item(...)
complete_leased_item(...)
defer_leased_item(...)
release_leased_item(...)
fail_leased_item(...)
mark_split_superseded(...)
cancel_active_items_for_run(...)
reclaim_expired_leases(...)

Запрещено:

direct item.status mutation
ad-hoc update_section_batch_queue_item from business code
exception bubble-up that leaves LEASED item without observable state

Prompt A section lease must not default to 300 seconds.

Lease duration must be stage-specific:

claim_observations lease: 30-60s
claim_surface_consolidation lease: separate policy
embedding/clustering lease: separate policy
client answer generation lease: separate policy

blocked_by_leases is not a job error.

It must become visible wait-state:

WAITING_FOR_ACTIVE_LEASES
active_lease_count
nearest_lease_expires_at
18. Workflow Stage Coordinator

The stage coordinator does not know Groq details.

It knows only task/work outcomes.

Stages:

STAGE_1_CLAIM_OBSERVATIONS
STAGE_2_PRE_CLUSTERING_CLEANUP
STAGE_3_EMBEDDING_CLUSTERING
STAGE_4_CLAIM_SURFACE_CONSOLIDATION
STAGE_5_CLUSTER_TREE_REDUCE
STAGE_6_REVIEW_READY
STAGE_7_PUBLISHED

Stage state contains:

pending_count
leased_count
deferred_count
completed_count
split_superseded_count
retryable_failed_count
terminal_failed_count
cancelled_count
waiting_until
blocker_kind

Stage can advance only if:

current stage terminal success
AND pending_count = 0
AND leased_count = 0
AND no deferred item ready before now
AND no unresolved terminal failures

Frontend-visible states:

processing
waiting_for_minute_limit
waiting_for_daily_reset
waiting_for_active_leases
requires_user_choice_daily_limit_exhausted
recoverable_validation_failures
recoverable_network_failures
failed_recoverable
failed_terminal
cancelled
review_ready
published
19. Проверка завершения после обработки всех секций

После того как все section work items выглядят обработанными, система обязана явно проверить завершение stage перед переходом дальше.

Проверка должна учитывать:

all expected source units/sections accounted for
no READY items left
no LEASED items left
no DEFERRED items ready before now
no RETRYABLE_FAILED unresolved
no TERMINAL_FAILED unresolved
no split parent counted as successful extraction
all split children accounted for
usage rollups updated

Только после этого workflow может перейти к cleanup/embedding/clustering.

20. Детерминированная cleanup-стадия после Stage 1

После завершения Stage 1 claim observations, но до embeddings и semantic clustering, workflow должен выполнить deterministic cleanup/preparation step.

Цель:

Очистить очевидные локальные дубли и шумные поля до embedding/clustering.

Минимальные cleanup targets:

duplicate possible_questions внутри одного draft claim/surface;
duplicate или near-identical exclusion_scope внутри одного draft;
пустые строки;
повторяющиеся whitespace;
повторяющиеся идентичные варианты вопросов;
очевидные duplicate local refs, если безопасно;
invalid/orphaned evidence refs, если обнаружены.

Эта стадия не делает semantic merge.

Это не Prompt C.

Это deterministic preprocessing перед embedding/clustering.

Результат — более чистые draft surfaces для генерации embeddings.

21. Embedding и clustering stage

После Stage 1 cleanup:

draft claim/surface outputs
→ embeddings
→ semantic clusters

Embeddings для intermediate drafts являются временными.

После публикации они могут быть удалены, если для final production surfaces создаются новые production embeddings.

Embedding/clustering stage обязан сохранять lineage:

draft surface id
source unit id
document id
processing run id
evidence refs
cluster id
22. Cluster / Tree Reduce Processing

Prompt C / consolidation processing may need tree-reduce.

Если кластер малый:

cluster → Prompt C → consolidated surfaces

Если кластер большой:

cluster
→ subcluster tasks
→ subcluster consolidated results
→ merge task
→ final consolidated surfaces

Default heuristic:

cluster with 1-3 facts/surfaces → можно обрабатывать одним Prompt C task
cluster with more than 3 facts/surfaces → нужно рассмотреть split на subclusters

Это policy default, а не вечная математическая истина.

Rules:

merge task cannot start until all child subcluster tasks are terminal success;
late results must not corrupt already finalized parent merge;
each merge output preserves lineage;
final surfaces must be self-contained and production/review-ready.
23. Client answer generation reuse, including no-LLM paths

LLM Processing Runtime и usage/statistics layer должны поддерживать runtime client answering.

Каналы:

Telegram bot
web widget
future channels

Usage/statistics model должен учитывать оба типа ответов:

- LLM-generated answers;
- non-LLM answers, где code/retrieval/rules дают ответ без generation.

Для non-LLM paths записывать:

runtime_operation
channel
client_id/thread_id where applicable
project_id
document/retrieval surface refs where applicable
used_llm=false
duration_ms
result_status

Для LLM paths дополнительно:

provider
model
account/key slot
prompt tokens
completion tokens
total tokens
estimated cost

Причина:

Бизнесовая статистика должна показывать, сколько стоит и как работает ассистент,
даже если часть ответов обходится без LLM generation.
24. Usage / Cost / Statistics

There are two classes of data.

24.1. Ephemeral processing artifacts

May be deleted after publication:

llm_task_attempts
llm_raw_outputs
llm_validation_failures
intermediate_embeddings
cluster_drafts
temporary route events
24.2. Durable rollups

Must remain after publication:

llm_usage_rollups_document
llm_usage_rollups_project_daily
llm_usage_rollups_project_total
llm_usage_rollups_client_daily
llm_usage_rollups_channel_daily

Tracked dimensions:

project_id
document_id
client_id
channel
provider
provider_account_id
model_id
task_kind
date

Tracked metrics:

request_count
success_count
failure_count
failure_kind_counts
prompt_tokens
completion_tokens
total_tokens
duration_ms
estimated_cost
free_tier_saved_cost

Free-tier usage must still be priced as hypothetical cost.

25. Publication Cleanup

After user review and publish:

Keep:

original document;
source references needed for citation;
final production search surfaces;
final embeddings for production surfaces;
durable usage rollups;
publication metadata.

Delete or archive:

intermediate Prompt A artifacts;
intermediate Prompt C artifacts;
temporary cluster drafts;
temporary embeddings;
raw LLM outputs if retention policy allows;
temporary task attempts if rollups are already persisted.

Publication must not delete data required for audit/source references.

26. Frontend-visible processing state должен объяснять ожидание

Пользователь не должен видеть opaque processing, если backend на самом деле ждёт.

Frontend-visible blockers:

waiting_for_minute_limit
waiting_for_daily_reset
waiting_for_active_leases
requires_user_choice_daily_limit_exhausted
recoverable_validation_failures
recoverable_network_failures
terminal_failure
cancelled

Для active leases показывать:

active_lease_count
nearest_lease_expires_at
affected_stage
affected_work_item_count

Для quota waits показывать:

limit_kind
provider/model/account if safe to show
waiting_until
affected_work_item_count

Это не только UX.

Это обязательная observability для безопасной эксплуатации.

27. Cutover Rules
Rule 1

No new production behavior goes into old Prompt A/Groq/queue handler path.

Rule 2

Old code may be used only as adapter/reference during cutover.

Rule 3

No two production truths.

If LlmTask becomes canonical, Prompt A artifacts must not be the only source of invocation status.

If SourceUnit becomes canonical, DocumentSection must become projection/compatibility view or be retired.

If WorkflowStageRun becomes canonical, document processing status must be derived from stage/work item state, not scattered flags.

Rule 4

No fake success for split parent.

Split parent is not empty success.

Split parent is SPLIT_SUPERSEDED / SPLIT_CREATED.

Rule 5

No frontend patch before backend state model for lifecycle bugs.

Frontend must display real backend state, not hide runtime confusion.

28. Required Recon Before Patching

Before implementation, run read-only reconnaissance and produce:

reports/llm_processing_runtime_cutover_recon.md

Recon must identify:

All Groq / LlmJsonInvocationPort call sites.
All Prompt A generator call sites.
All fallback model logic.
All places where SectionBatchQueueItem.status changes.
All uses of lease_seconds=300.
All places returning/raising blocked_by_leases.
All document section creation/update paths.
All oversized split helpers.
All processing state endpoints used by frontend.
Whether empty claims secondary-model confirmation exists.
All usage/token/cost persistence points.
All Workbench queue tables and migrations.
All tests enforcing old Prompt A/Groq/queue assumptions.
All places that assume four fixed lanes/accounts.
All frontend states related to processing/waiting/failure.
All places that may load whole documents/sections/clusters into memory.
All embedding/clustering batch paths.

No patching before this recon is complete.

29. Implementation Order
Phase A — Recon and architecture freeze

Create recon report.

Freeze old path.

Add architectural guard tests preventing new behavior in retired locations.

Phase B — Target domain and database model

Add canonical models/tables for:

source_units
llm_tasks
llm_task_attempts
llm_task_artifacts
workflow_stage_runs
workflow_work_items
llm_quota_windows
llm_usage_rollups_*
Phase C — LLM Processing Runtime

Implement:

LlmTaskExecutor
LlmRoutePlanner
LlmQuotaManager
LlmProviderAdapterPort
LlmOutputValidationService
LlmUsageRecorder

Groq becomes provider adapter.

Phase D — Source Unit Split Runtime

Move split logic out of queue handler.

Implement format-aware and capacity-aware split services.

Phase E — Prompt A cutover

Prompt A becomes first consumer of new runtime.

Prompt A generator becomes prompt/parse/validate adapter only.

Fallback, retry, split, lease, quota and usage accounting move out.

Phase F — Stage coordinator cutover

Replace blocked_by_leases as transient job error with observable wait-state.

Add stage readiness and frontend-visible states.

Phase G — Prompt C / consolidation cutover

Implement Prompt C as claim/surface consolidation around user intents.

Prompt C output includes Prompt A fields and richer semantic fields.

Phase H — Embedding, clustering, tree-reduce, review, publish

Implement cluster processing, review-ready state, publish and cleanup.

30. Immediate Non-Negotiables

The first implementation wave must eliminate these blockers:

LEASED item left behind after worker exception must be impossible.
300s Prompt A lease must not remain default behavior.
blocked_by_leases must become observable wait-state, not opaque transient job error.
Split parent must not be persisted as fake empty success.
Prompt A fallback/retry policy must move out of generator.
Empty claims must require explicit secondary-model confirmation policy.
Usage accounting must not be trapped only in ephemeral Prompt A artifacts.
Daily limit exhaustion must surface explicit user choice.
Pre-clustering deterministic cleanup must happen after Stage 1.
Prompt C must be intent-centered claim/surface consolidation.
Large clusters must use subcluster/tree-reduce policy.
Client answer generation and non-LLM answer paths must share usage/statistics accounting.
Network/provider errors must use precise taxonomy.
Новый runtime должен быть bounded по памяти/concurrency/batch sizes.
Старые production paths не должны развиваться параллельно новому runtime.
31. Summary

The target system is not a bigger Prompt A patch.

It is a cutover from ad-hoc LLM calls to a reusable LLM Processing Runtime.

Prompt A extracts local evidence-grounded claims.

Prompt C consolidates claims/surfaces around user intents, deduplicates, enriches, merges and returns self-contained output that includes Prompt A fields plus richer semantic fields.

The runtime owns model/key routing, quota, retries, validation, split, lease lifecycle, resource boundaries and usage accounting.

Workbench owns document-to-knowledge workflow stages.

Frontend displays real workflow state.

Old production paths are retired, adapted or deleted.

They are not developed in parallel.
