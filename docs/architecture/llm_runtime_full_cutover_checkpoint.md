# LLM Runtime Full Cutover Checkpoint

## 0. Назначение документа

Этот документ фиксирует текущее целевое состояние нового bounded context:

```text
src/contexts/llm_runtime/

Документ нужен, чтобы дальнейшая реализация не скатилась обратно в старую модель:

Prompt A generator
→ Groq-specific fallback
→ keyring/router side effects
→ queue handler status mutation
→ hidden retries
→ leased item stuck until TTL
→ opaque blocked_by_leases

Цель нового llm_runtime:

LlmTask
→ provider-neutral execution policy
→ provider-neutral route planning
→ provider-neutral validation
→ provider-neutral recording/UoW boundary
→ provider-specific thin adapters
→ explicit infrastructure composition

Этот документ не является задачей на массовый rewrite всего проекта.

Он является checkpoint’ом и контрактом для следующих patches.

1. Главный архитектурный сдвиг

Раньше LLM-логика была размазана между:

src/infrastructure/llm/groq_llm_json_invocation.py
src/infrastructure/llm/workbench_qwen_json_invocation.py
src/infrastructure/llm/groq_router.py
src/infrastructure/llm/groq_keyring.py
src/infrastructure/queue/handlers/workbench_parallel_processing.py
Prompt A / Prompt C generators
old application ports
old queue statuses

Новая цель:

src/contexts/llm_runtime/
  domain/
  application/
  infrastructure/
  interfaces/

Где:

domain:
  LlmTask, LlmAttempt, LlmRoute, model/account/quota/value objects, state machine

application:
  use cases, policies, ports, result models

infrastructure:
  Groq seed/config/http/request/response/adapter/composition

interfaces:
  пока пусто; публичные API/HTTP endpoints сюда не переносились

Новый runtime не является “ещё одним Groq client”.

Он является reusable LLM execution runtime для:

Knowledge Workbench Prompt A
Knowledge Workbench Prompt C / consolidation
client answer generation
RAG evaluation
future dialog memory summarization
future tool-result processing
2. Bounded context ownership
2.1. llm_runtime owns

llm_runtime владеет:

LlmTask
LlmAttempt
LlmRoute
ModelProfile
ProviderAccount
RateLimitProfile
TokenPrice
ReasoningProfile
ReasoningEffort
QuotaDecision
TokenUsage
PromptVersion
OutputContractRef
LlmInputRef
LlmErrorKind
LlmTaskStatus
LlmTaskStateMachine
provider-neutral error policy
provider-neutral route planning policy
provider-neutral validation policy
provider-neutral recording policy
provider ports
provider infrastructure adapters
provider infrastructure composition
2.2. llm_runtime does not own

llm_runtime не владеет:

Workbench business meaning
Prompt A semantic extraction rules
Prompt C claim/surface consolidation semantics
SourceUnit / document structure
artifact retention decisions
WorkItem lease lifecycle
StageRun / ProcessingRun orchestration
Telegram delivery
human review
publication decisions
frontend display policy
2.3. Critical boundary

Правило:

LLM Runtime may know that a task has an output contract.
LLM Runtime must not know that the output contract is Prompt A claims.

Правило:

LLM Runtime may know that a route hit MINUTE_LIMIT.
LLM Runtime must not decide Workbench stage transition.

Правило:

LLM Runtime may return SPLIT_REQUIRED.
LLM Runtime must not split documents itself.
3. Current bounded context structure

Актуальная структура:

src/contexts/llm_runtime/
  domain/
    entities/
    events/
    state_machines/
    value_objects/

  application/
    policies/
    ports/
    results/
    use_cases/

  infrastructure/
    config/
    providers/
      groq/

  interfaces/

Запрещено создавать новые dumping-ground файлы:

service.py
services.py
repository.py
repositories.py
dto.py
utils.py
helpers.py

Новые файлы должны называться по роли:

domain/entities/llm_task.py
domain/value_objects/rate_limit_profile.py
application/policies/llm_route_planning_policy.py
application/use_cases/execute_llm_task.py
application/ports/llm_provider_port.py
infrastructure/providers/groq/groq_provider_adapter.py
4. Domain layer: текущее состояние
4.1. Entities

Сейчас в domain есть:

LlmTask
LlmAttempt
ModelProfile
ProviderAccount
LlmTask

Назначение:

domain entity for one LLM execution task

Содержит:

task_id
prompt_id
prompt_version
input_ref
output_contract_ref
status
selected_route
wait_until

Lifecycle управляется через:

LlmTaskStateMachine

Нельзя напрямую менять статус задачи из use case / adapter.

LlmAttempt

Назначение:

domain entity for one provider attempt under an LlmTask

Содержит сведения о:

attempt_id
task_id
attempt_number
route
status/outcome
raw_text
usage
error_kind
started_at
finished_at

Используется recording policy и UoW boundary.

ModelProfile

Назначение:

provider-neutral model catalog profile

Содержит:

provider_id
model_id
lifecycle
context_window_tokens
max_output_tokens
model_rank
rate_limits
token_price
reasoning_profile
supports_json_object
supports_json_schema
enabled

Важно:

max_output_tokens <= context_window_tokens
model_rank >= 0
ProviderAccount

Назначение:

provider-neutral capacity slot / provider account / organization

Содержит:

provider_id
account_ref
account_rank
status

Важно:

account_ref is not raw secret
account_ref is local capacity-slot label
4.2. Value Objects

Сейчас есть:

ModelId
ProviderId
ProviderAccountRef
LlmRoute
PromptVersion
OutputContractRef
LlmInputRef
TokenUsage
QuotaDecision
QuotaDecisionKind
LlmErrorKind
LlmTaskStatus
ModelLifecycle
ProviderAccountStatus
RateLimitProfile
TokenPrice
ReasoningEffort
ReasoningProfile
LlmValidationResult
ReasoningProfile

Особенно важен.

Проблема из практики:

Qwen with reasoning enabled can waste output budget on reasoning tokens.

Поэтому отключение reasoning должно быть частью generic model capability, а не Groq/Qwen hack.

Целевой смысл:

Qwen:
  supports reasoning control
  can disable reasoning
  default effort = none

GPT OSS:
  supports low/medium/high
  cannot disable reasoning with none

Llama:
  no reasoning controls
4.3. Domain events

Сейчас есть LLM task events:

LlmTaskSucceeded
LlmTaskFailed
LlmTaskDeferred
LlmMinuteLimitHit
LlmDailyLimitExhausted

Эти события пока не подключены к transactional outbox.

Они уже есть как domain/application recording output.

4.4. State Machine

Файл:

src/contexts/llm_runtime/domain/state_machines/llm_task_state_machine.py

Назначение:

only legal lifecycle transitions for LlmTask

Правило:

Use cases must call state machine methods.
No direct task.status assignment in application/infrastructure.

Это уже защитило от состояния:

DEFERRED task without wait_until
5. Application layer: текущее состояние
5.1. Ports

Сейчас есть:

LlmProviderPort
LlmOutputValidationPort
LlmTaskUnitOfWorkPort
LlmProviderInput
LlmProviderPort

Файл:

src/contexts/llm_runtime/application/ports/llm_provider_port.py

Контракт:

invoke(task, route, provider_input) -> LlmProviderResult

Возвращает:

LlmProviderSuccess(raw_text, usage)
LlmProviderFailure(error_kind, wait_until)

Provider port не делает persistence.

Provider port не делает workflow transition.

Provider port не делает Workbench decisions.

LlmProviderInput

Файл:

src/contexts/llm_runtime/application/ports/llm_provider_input.py

Назначение:

prepared provider-neutral messages

Содержит:

LlmProviderMessageRole
LlmProviderMessage
LlmProviderInput

Причина появления:

Groq adapter cannot hide input resolving inside itself.
ExecuteLlmTask must receive already prepared input.
LlmOutputValidationPort

Назначение:

validate raw provider output before task success

Возвращает:

LlmOutputValidationSuccess
LlmOutputValidationFailure

Allowed validation failure error kinds:

INVALID_OUTPUT
VALIDATION_FAILED
EMPTY_OUTPUT
LlmTaskUnitOfWorkPort

Назначение:

transaction boundary for saving task, attempt and events

Методы:

save_task
save_attempt
append_event
commit
rollback

Postgres adapter пока не реализован.

5.2. Policies

Сейчас есть:

LlmErrorPolicy
LlmRoutePlanningPolicy
LlmRouteCandidateBuilder
LlmQuotaAvailabilityPolicy
LlmRouteCandidatePreparationPolicy
LlmJsonOutputValidationPolicy
LlmExecutionRecordingPolicy
LlmErrorPolicy

Файл:

src/contexts/llm_runtime/application/policies/llm_error_policy.py

Назначение:

map LlmErrorKind to provider-neutral disposition

Примеры:

REQUEST_TOO_LARGE -> TRY_ALTERNATE_ROUTE
OUTPUT_TOO_LARGE -> TRY_ALTERNATE_ROUTE
MINUTE_LIMIT -> DEFER_UNTIL / route planning
DAILY_LIMIT -> TRY_ALTERNATE_ROUTE / daily exhausted
INVALID_OUTPUT -> VALIDATION_RETRY
VALIDATION_FAILED -> VALIDATION_RETRY
EMPTY_OUTPUT -> CONFIRM_EMPTY_OUTPUT
NETWORK_ERROR -> RETRY_SAME_ROUTE
AUTH_ERROR -> TERMINAL_FAILURE
UNKNOWN -> RETRY_SAME_ROUTE

Важно:

ErrorPolicy does not choose concrete model/account.
LlmRoutePlanningPolicy

Файл:

src/contexts/llm_runtime/application/policies/llm_route_planning_policy.py

Назначение:

choose next route / wait / split / exhaustion from candidates

Поведение:

REQUEST_TOO_LARGE:
  prefer larger context route
  same account first
  if none -> SPLIT_REQUIRED

OUTPUT_TOO_LARGE:
  prefer larger output route
  same account first
  if none -> SPLIT_REQUIRED

MINUTE_LIMIT:
  prefer same model on another available account
  if no available account -> WAIT_UNTIL
  if no wait known -> RETRY_SAME_ROUTE

DAILY_LIMIT:
  prefer same model on another account
  then next model
  if none -> DAILY_EXHAUSTED

AUTH_ERROR:
  TERMINAL_FAILURE

Важно:

RoutePlanningPolicy consumes candidates.
It does not build candidates itself.
LlmRouteCandidateBuilder

Файл:

src/contexts/llm_runtime/application/policies/llm_route_candidate_builder.py

Назначение:

ModelProfile + ProviderAccount + availability snapshot
→ tuple[LlmRouteCandidate, ...]

Сортировка:

model_rank
account_rank
provider_id
model_id
account_ref

Важно:

no Groq hardcode
no Workbench semantics
LlmQuotaAvailabilityPolicy

Файл:

src/contexts/llm_runtime/application/policies/llm_quota_availability_policy.py

Назначение:

quota snapshots + estimated token need
→ route availability

Содержит:

LlmEstimatedTokenNeed
LlmQuotaSnapshot
LlmQuotaAvailabilityPolicy

Учитывает:

remaining_requests_minute
remaining_requests_day
remaining_tokens_minute
remaining_tokens_day
remaining_input_tokens_minute
remaining_output_tokens_minute
unavailable_until

Важно:

output cannot be predicted exactly.
reserved_output_tokens is conservative reservation, not prediction.
LlmRouteCandidatePreparationPolicy

Файл:

src/contexts/llm_runtime/application/policies/llm_route_candidate_preparation_policy.py

Назначение:

catalog + quota snapshots + estimated token need
→ ready-to-plan route candidates

Это composition внутри application policy, но всё ещё provider-neutral.

LlmJsonOutputValidationPolicy

Файл:

src/contexts/llm_runtime/application/policies/llm_json_output_validation_policy.py

Назначение:

generic JSON output validation

Поддерживает:

invalid JSON -> INVALID_OUTPUT
top-level non-object -> VALIDATION_FAILED
unknown output contract -> VALIDATION_FAILED
missing required top-level keys -> VALIDATION_FAILED
empty object -> EMPTY_OUTPUT or allowed by contract

Не знает:

Prompt A fields
Prompt C fields
claim_observations
surfaces
LlmExecutionRecordingPolicy

Файл:

src/contexts/llm_runtime/application/policies/llm_execution_recording_policy.py

Назначение:

ExecuteLlmTaskOutcome
→ RecordLlmTaskExecutionCommand

Создаёт:

LlmAttempt
domain event
recording command
5.3. Use cases

Сейчас есть:

ExecuteLlmTask
RecordLlmTaskExecution
ExecuteAndRecordLlmTask
ExecuteLlmTask

Файл:

src/contexts/llm_runtime/application/use_cases/execute_llm_task.py

Назначение:

execute one LLM task attempt without persistence

Поток:

LlmTask READY/DEFERRED/RETRYABLE_FAILED
→ LlmTaskStateMachine.start_ready
→ provider.invoke(task, route, provider_input)
→ if provider success: validate raw output
→ if validation success: state machine success
→ if validation failure: error policy + route policy
→ if provider failure: error policy + route policy
→ ExecuteLlmTaskOutcome

Важно:

provider success is not task success
RecordLlmTaskExecution

Файл:

src/contexts/llm_runtime/application/use_cases/record_llm_task_execution.py

Назначение:

commit task/attempt/events atomically through UoW

Поток:

save_task
save_attempt if present
append_event(s)
commit
rollback on exception
ExecuteAndRecordLlmTask

Файл:

src/contexts/llm_runtime/application/use_cases/execute_and_record_llm_task.py

Назначение:

execute task + build recording command + persist through UoW

Поток:

ExecuteLlmTask
→ LlmExecutionRecordingPolicy
→ RecordLlmTaskExecution

Не знает:

Groq
Postgres
Workbench
WorkItem
PipelineArtifact
Prompt A
Prompt C
6. Infrastructure layer: Groq provider stack

Groq-specific code расположен здесь:

src/contexts/llm_runtime/infrastructure/providers/groq/

Это infrastructure provider implementation.

Generic domain/application не импортируют Groq.

6.1. Groq model catalog seed

Файл:

groq_model_catalog_seed.py

Назначение:

static seed for Groq free-plan model profiles and provider accounts

Содержит модели:

qwen/qwen3-32b
llama-3.1-8b-instant
openai/gpt-oss-20b
openai/gpt-oss-120b
llama-3.3-70b-versatile

В seed зафиксировано:

context_window_tokens
max_output_tokens
RPM/RPD/TPM/TPD free-plan limits
token prices
lifecycle production/preview
model_rank
reasoning_profile
json support

Важно:

Qwen default reasoning_effort = none

Причина:

reasoning tokens may consume useful output budget
6.2. Groq rate limit headers mapper

Файл:

groq_rate_limit_headers_mapper.py

Назначение:

Groq HTTP headers
→ LlmQuotaSnapshot

Маппинг:

x-ratelimit-remaining-requests -> remaining_requests_day
x-ratelimit-remaining-tokens -> remaining_tokens_minute
x-ratelimit-reset-requests -> unavailable_until candidate
x-ratelimit-reset-tokens -> unavailable_until candidate
retry-after -> unavailable_until candidate

Важно:

mapper does not decide retry/fallback
6.3. Groq provider response mapper

Файл:

groq_provider_response_mapper.py

Назначение:

Groq HTTP response
→ LlmProviderSuccess / LlmProviderFailure
+ quota snapshot

Классифицирует:

2xx -> success, extract chat content and usage
401/403 -> AUTH_ERROR
429 minute/default -> MINUTE_LIMIT
429 daily/RPD/TPD text -> DAILY_LIMIT
413 -> REQUEST_TOO_LARGE
400 context text -> REQUEST_TOO_LARGE
400 max_completion/output text -> OUTPUT_TOO_LARGE
5xx -> NETWORK_ERROR
other -> UNKNOWN

Важно:

mapper does not retry
mapper does not choose fallback
mapper does not mutate task
6.4. Groq chat request builder

Файл:

groq_chat_request_builder.py

Назначение:

LlmRoute + ModelProfile + GroqChatMessage + options
→ Groq Chat Completions payload

Строит:

model
messages
max_completion_tokens
temperature
response_format={"type": "json_object"}
reasoning_effort when supported/defaulted

Важно:

Qwen emits reasoning_effort="none" by default.

Валидации:

route.provider_id == model_profile.provider_id
route.model_id == model_profile.model_id
messages not empty
max_completion_tokens <= model_profile.max_output_tokens
json mode only if model supports json object
reasoning effort only if supported by model
6.5. Groq transport port

Файл:

groq_transport_port.py

Назначение:

transport boundary for posting prepared Groq payload

Содержит:

GroqTransportPort
GroqTransportResponse

Это ещё не httpx.

6.6. Groq provider adapter

Файл:

groq_provider_adapter.py

Назначение:

implements LlmProviderPort

Поток:

LlmProviderInput
→ GroqChatMessage tuple
→ GroqChatRequestBuilder
→ GroqTransportPort.post_chat_completions
→ GroqProviderResponseMapper
→ LlmProviderResult

Важно:

does not own retry/fallback
does not own quota policy
does not read env
does not know Workbench
6.7. Groq HTTP transport

Файл:

groq_http_transport.py

Назначение:

GroqTransportPort implementation over a generic HTTP client port

Содержит:

GroqHttpClientPort
GroqHttpClientResponse
GroqApiKeyRef
GroqHttpTransport

Поток:

payload
→ HTTP POST /chat/completions
→ GroqTransportResponse

Важно:

does not retry
does not rotate keys
does not read env
6.8. Groq httpx client

Файл:

groq_httpx_client.py

Назначение:

httpx implementation of GroqHttpClientPort

Содержит:

GroqHttpxClient
GroqHttpxResponseAdapter

Важно:

single HTTP POST only
no retry
no fallback
no env
no key rotation

httpx.MockTransport поддержан для тестов без monkeypatch/type-ignore.

6.9. Groq env config

Файл:

groq_env_config.py

Назначение:

resolve Groq account slots from provided mapping

Содержит:

GroqEnvAccountSpec
GroqEnvAccountConfig
GroqEnvConfig
GroqEnvConfigLoader

Важно:

env mapping is injected
loader does not import old Settings
loader does not read os.environ directly
6.10. Groq provider composition

Файлы:

groq_provider_composition.py
groq_http_provider_composition.py

Назначение:

explicitly compose provider runtime components

Компоненты:

GroqProviderRuntimeComponents
GroqProviderRuntimeFactory
GroqHttpProviderRuntimeFactory

Важно:

composition receives transport/client/config explicitly
no hidden global state
7. Infrastructure config: LLM Runtime settings

Файл:

src/contexts/llm_runtime/infrastructure/config/llm_runtime_settings.py

Назначение:

LLM Runtime owns its provider settings inside its bounded context.

Содержит:

LlmRuntimeSettings

Поля:

groq_api_key
groq_api_key2
groq_api_key3
groq_api_key4
groq_base_url
groq_timeout_seconds

Важно:

env names remain deployment-compatible:
GROQ_API_KEY
GROQ_API_KEY2
GROQ_API_KEY3
GROQ_API_KEY4

but ownership moved to:
src/contexts/llm_runtime/infrastructure/config/

Специально не импортируется:

src.infrastructure.config.settings.Settings

Причина:

new bounded context must not depend on legacy global app settings as target architecture
8. Why old Settings is not target dependency

Старый settings path:

src/infrastructure/config/settings.py

содержит Groq variables:

GROQ_API_KEY
GROQ_API_KEY2
GROQ_API_KEY3
GROQ_API_KEY4
GROQ_MODEL
GROQ_KNOWLEDGE_PREPROCESSING_MODEL

Но это layer-first global app settings.

Целевое состояние:

llm_runtime owns LLM provider infrastructure settings.

Не делаем:

llm_runtime -> import old Settings

Делаем:

llm_runtime -> LlmRuntimeSettings

При необходимости app composition позже может собрать:

old app Settings
new LlmRuntimeSettings
other bounded context settings

Но сам llm_runtime не должен зависеть от старого Settings.

9. Current end-to-end provider stack

После текущих patches целевая цепочка выглядит так:

LlmRuntimeSettings
→ to_groq_env_config()
→ GroqEnvConfig
→ GroqHttpProviderRuntimeFactory
→ GroqHttpxClient
→ GroqHttpTransport
→ GroqProviderAdapter
→ LlmProviderPort
→ ExecuteLlmTask
→ LlmOutputValidationPort
→ ExecuteLlmTaskOutcome
→ LlmExecutionRecordingPolicy
→ RecordLlmTaskExecution
→ LlmTaskUnitOfWorkPort

Пока отсутствует один optional helper:

LlmRuntimeProviderCompositionFactory

Он должен просто собрать:

LlmRuntimeSettings
+ GroqHttpxClient
→ GroqHttpProviderRuntimeFactory
→ GroqProviderRuntimeComponents

Если он уже добавлен отдельным patch, этот документ можно обновить.

10. Provider success is not task success

Критическое правило:

HTTP 200 from Groq
does not mean LlmTask succeeded

Правильная цепочка:

Groq HTTP 200
→ GroqProviderResponseMapper extracts raw_text
→ LlmProviderSuccess
→ ExecuteLlmTask calls output_validator.validate(...)
→ only validation success leads to LlmTask SUCCEEDED

Если JSON битый:

provider success
→ validation failure
→ retry / route / confirm-empty policy
11. Reasoning policy

Reasoning управляется через:

ReasoningProfile
ReasoningEffort
GroqChatRequestBuilder
ModelProfile

Не через prompt-specific hacks.

Целевые случаи:

qwen/qwen3-32b:
  default reasoning_effort="none"

openai/gpt-oss-20b:
  default reasoning_effort="medium"
  supports low/medium/high
  does not support none

openai/gpt-oss-120b:
  default reasoning_effort="medium"
  supports low/medium/high
  does not support none

llama:
  no reasoning control
  reasoning_effort omitted

Причина:

reasoning output can reduce usable completion budget.
12. Quota/rate-limit policy

Сейчас реализовано:

RateLimitProfile
LlmQuotaSnapshot
LlmQuotaAvailabilityPolicy
GroqRateLimitHeadersMapper

Сейчас ещё не реализовано:

durable quota ledger
per-route rolling windows
header persistence
usage rollups
cost rollups
daily reset scheduler
minute wait scheduler

Важно:

Groq headers mapper only extracts observed snapshot.
It does not maintain long-lived state.

Целевой следующий stateful слой позже:

LlmQuotaLedger / LlmQuotaRepository / LlmUsageRecorder

Но пока преждевременно писать БД adapter до интеграции UoW/outbox.

13. Error and fallback policy

Сейчас реализовано provider-neutral:

LlmErrorPolicy
LlmRoutePlanningPolicy
LlmRouteCandidateBuilder
LlmRouteCandidatePreparationPolicy

Старое Groq-specific поведение из legacy router не переносится напрямую.

Legacy concepts such as:

GroqLimitKind
GroqRouteFailureType
GroqFallbackPolicy
GroqModelRouter
GroqApiKeyRing

не являются целевыми domain/application concepts нового llm_runtime.

Они могут быть reference материалом при cutover, но не source of truth.

14. What is still not implemented

Не реализовано:

Postgres LlmTaskUnitOfWork
transactional outbox
durable LlmAttempt storage
durable LlmTask storage
usage/cost rollups
quota ledger persistence
integration with execution_runtime WorkItem
integration with artifact_runtime PipelineArtifact
Knowledge Workbench Prompt A cutover
Prompt C / consolidation cutover
SourceUnit domain
split policy integration
stage coordinator / saga
frontend-visible processing state
manual user choice for degraded fallback
daily auto-resume

Это нормально.

Мы пока строили provider-neutral and provider-specific foundation.

15. What must not be done next

Нельзя следующим шагом:

patch Prompt A generator directly
patch workbench_parallel_processing queue handler directly
patch old groq_router as new truth
patch old groq_keyring as new truth
add retries inside GroqProviderAdapter
add fallback inside GroqHttpTransport
read env inside GroqProviderAdapter
make LLM Runtime import Workbench
make LLM Runtime import old app Settings
make queue status mean artifact checkpoint
16. Safe next steps
Step 1 — provider composition helper

If not already done:

src/contexts/llm_runtime/infrastructure/config/llm_runtime_provider_composition.py

Purpose:

LlmRuntimeSettings
→ GroqEnvConfig
→ GroqHttpxClient
→ GroqHttpProviderRuntimeFactory
→ GroqProviderRuntimeComponents

No legacy Settings.

Step 2 — checkpoint commit

After provider composition helper:

Document llm runtime provider stack checkpoint
Step 3 — application integration boundary

Start connecting llm_runtime to adjacent contexts by ports, not by direct imports.

Target bridge:

execution_runtime WorkItem
→ application orchestration
→ ExecuteAndRecordLlmTask
→ artifact_runtime PersistArtifact

But do not implement all at once.

Step 4 — Artifact Runtime integration

Need a use case boundary like:

Record LLM task execution
+ Persist raw output / parsed artifact
+ mark WorkItem completed/deferred/failed
+ append outbox event

This needs Unit of Work spanning contexts, but must be designed carefully.

Step 5 — Prompt A cutover

Only after execution/artifact integration exists:

Knowledge Workbench Extraction
→ prepares LlmProviderInput
→ prepares LlmTask
→ calls LLM Runtime
→ persists Prompt A artifact through Artifact Runtime

Prompt A should not own:

model selection
key selection
fallback
retry
quota
split
lease
usage accounting
17. Architectural rules for future agents

Future agents must obey:

1. No generic service.py/repository.py/dto.py dumping grounds.
2. No Workbench terms in LLM Runtime domain/application.
3. No Groq retry/fallback inside Groq provider adapter.
4. No env reading inside provider adapter.
5. No old Settings import inside llm_runtime.
6. No direct task.status mutation outside LlmTaskStateMachine.
7. No provider success accepted without validation.
8. No output prediction pretending to be exact.
9. No Prompt A cutover before artifact/execution boundary is designed.
10. No package-level eager barrel imports causing cycles.
11. No Any/type-ignore in new canonical code.
12. No secrets in logs, tests, reports or committed docs.
18. Current conceptual map
domain:
  LlmTask
  LlmAttempt
  ModelProfile
  ProviderAccount
  LlmTaskStateMachine

application:
  ExecuteLlmTask
  ExecuteAndRecordLlmTask
  RecordLlmTaskExecution
  LlmErrorPolicy
  LlmRoutePlanningPolicy
  LlmRouteCandidateBuilder
  LlmQuotaAvailabilityPolicy
  LlmJsonOutputValidationPolicy
  LlmExecutionRecordingPolicy
  LlmProviderPort
  LlmOutputValidationPort
  LlmTaskUnitOfWorkPort
  LlmProviderInput

infrastructure/config:
  LlmRuntimeSettings

infrastructure/providers/groq:
  Groq model catalog seed
  Groq env config
  Groq rate-limit headers mapper
  Groq response mapper
  Groq chat request builder
  Groq transport port
  Groq provider adapter
  Groq HTTP transport
  Groq httpx client
  Groq provider composition
19. Summary

Мы уже построили не просто “новый Groq клиент”, а полноценный каркас:

model/account catalog
route candidates
quota availability
error policy
route planning
prepared provider input
output validation
task execution
recording policy
unit-of-work boundary
Groq seed
Groq request builder
Groq response mapper
Groq headers mapper
Groq transport
Groq httpx client
Groq env config
LLM Runtime owned settings

Следующий риск — начать смешивать это с Workbench слишком рано.

Правильное продолжение:

finish provider composition
then checkpoint
then design cross-context orchestration:
Execution Runtime + LLM Runtime + Artifact Runtime
then Prompt A cutover