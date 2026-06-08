# Pattern-Based Architecture Contract

## 0. Назначение документа

Этот документ фиксирует архитектурный каркас `crm_bot` в терминах bounded contexts и архитектурных паттернов.

Он заменяет подход:

```text
добавим ещё один service
добавим ещё один repository method
протащим ещё один DTO
потом вырежем старое
потом рядом появится новый почти такой же path

на подход:

сначала определить bounded context
потом определить паттерн
потом определить canonical vocabulary
потом определить место в проекте
потом писать код

Документ не является задачей на немедленный rewrite.

Документ является контрактом, который должен предотвращать:

дублирование сущностей;
хаотическое именование;
расширение legacy paths;
смешивание queue lifecycle и pipeline checkpoint;
смешивание LLM provider adapter и LLM workflow policy;
смешивание artifact persistence и work item status;
превращение generic services/repositories/DTO в место для всей бизнес-логики.
1. Главный диагноз

Текущая архитектура имеет layer-first структуру:

src/domain/
src/application/
src/infrastructure/
src/interfaces/
src/agent/

Это формально похоже на DDD/clean architecture, но на практике многие bounded contexts размазаны по слоям.

Из-за этого смысловые объекты живут не как entities/value objects/use cases/state machines, а как смесь:

services
repositories
DTO
queue payloads
status strings
handler helpers
tests around accidental behavior

Главная проблема:

Сервисы стали носителями слишком большого количества ответственности.

Сейчас один service может одновременно быть:

use case;
process manager;
state machine;
policy;
transaction script;
adapter coordinator;
queue worker helper;
persistence orchestration;
error handler;
implicit domain model.

Цель нового каркаса — раздать ответственность правильным архитектурным объектам.

2. Целевая структурная позиция

Целевая архитектура должна двигаться от layer-first к bounded-context-first.

Не так:

src/
  domain/
  application/
  infrastructure/
  interfaces/

А так:

src/
  contexts/
    execution_runtime/
      domain/
      application/
      infrastructure/
      interfaces/

    llm_runtime/
      domain/
      application/
      infrastructure/
      interfaces/

    artifact_runtime/
      domain/
      application/
      infrastructure/
      interfaces/

    knowledge_workbench/
      domain/
      application/
      infrastructure/
      interfaces/

    conversation_runtime/
      domain/
      application/
      infrastructure/
      interfaces/

Физический перенос старого кода не должен быть первым шагом.

Первый шаг — logical bounded context map и canonical vocabulary.

Новый canonical код должен писаться уже в bounded-context-first структуре.

Старый код получает один из статусов:

CANONICAL
ADAPTER
LEGACY
RETIRED
3. Обязательное правило перед созданием нового кода

Перед созданием нового класса, функции, таблицы, DTO или сервиса нужно ответить:

1. В каком bounded context это живёт?
2. Это Entity, Value Object, Use Case, Domain Service, Application Service, Port, Adapter, Event, Read Model или Policy?
3. Какое canonical имя уже существует?
4. Это не дубликат старого понятия?
5. Старый код мы развиваем, адаптируем или retired?
6. Нужна ли State Machine?
7. Нужен ли Unit of Work?
8. Нужен ли Domain Event / Outbox?
9. Это command-side или read-side?

Если ответы не ясны — код не писать.

4. Canonical bounded contexts
4.1. Execution Runtime
Назначение

Абстрактный runtime выполнения работы.

Ему безразлично, что выполняется:

обработка секции документа;
LLM-задача;
Telegram-ответ;
обработка webhook;
пересчёт embedding;
обновление памяти диалога;
публикация знаний.

Execution Runtime знает только:

work item
queue
lease
attempt
retry
defer
cancel
worker capacity
wait state
idempotency
Владение

Execution Runtime владеет:

WorkItem;
WorkItemAttempt;
Lease;
LeaseToken;
RetryPolicy;
DeferPolicy;
WorkerRef;
WorkItemStateMachine;
execution wait states;
concurrency/batch limits.
Не владеет

Execution Runtime не владеет:

Prompt A;
Prompt C;
Groq;
claims;
source units;
retrieval surfaces;
Telegram messages;
business policies;
artifacts payload semantics.
Паттерны

Обязательные паттерны:

Entity:
  WorkItem
  WorkItemAttempt

Value Object:
  LeaseToken
  RetryPolicy
  DeferPolicy
  WaitUntil
  WorkerRef
  WorkKind

State Machine:
  WorkItemStateMachine

Use Cases:
  LeaseWorkItem
  CompleteWorkItem
  DeferWorkItem
  FailWorkItem
  CancelWorkItem
  ReclaimExpiredLeases

Unit of Work:
  required when work item transition is committed together with artifact/task/event changes

Domain Events:
  WorkItemLeased
  WorkItemCompleted
  WorkItemDeferred
  WorkItemFailed
  WorkItemCancelled
  WorkItemLeaseExpired
Canonical statuses
READY
LEASED
DEFERRED
COMPLETED
RETRYABLE_FAILED
TERMINAL_FAILED
CANCELLED
SPLIT_SUPERSEDED
Legacy warning

SectionBatchQueueItem is not canonical WorkItem.

It is a legacy/adapter hybrid because it currently mixes:

queue lifecycle;
lease;
pipeline checkpoint;
artifact marker;
Workbench stage progress.
4.2. LLM Runtime
Назначение

Runtime выполнения LLM-задач.

Ему безразлично:

это Groq или другой provider;
это Prompt A или Prompt C;
это Workbench или клиентский ответ;
это документ или диалог.

LLM Runtime знает:

LLM task
prompt
model route
provider account
quota
token usage
validation
retry/fallback
provider adapter
Владение

LLM Runtime владеет:

LlmTask;
LlmAttempt;
LlmRoute;
ModelProfile;
ProviderAccount;
QuotaDecision;
TokenUsage;
LlmOutputContract;
LlmValidationResult;
LlmErrorKind;
LlmTaskStateMachine;
LlmUsageRecorder.
Не владеет

LLM Runtime не владеет:

Workbench business meaning;
source document structure;
claims semantics;
final answer policy;
Telegram delivery;
human review;
publication decisions.
Паттерны
Entity:
  LlmTask
  LlmAttempt

Value Object:
  ModelId
  ProviderId
  ProviderAccountRef
  TokenUsage
  QuotaDecision
  PromptVersion
  OutputContractRef
  LlmErrorKind

State Machine:
  LlmTaskStateMachine

Use Case:
  ExecuteLlmTask

Domain Service:
  RoutePlanner
  QuotaManager
  OutputValidationService
  UsageRecorder

Port:
  LlmProviderPort

Adapter:
  GroqProviderAdapter
  FutureProviderAdapter

Domain Events:
  LlmTaskSucceeded
  LlmTaskDeferred
  LlmTaskFailed
  LlmDailyLimitExhausted
  LlmMinuteLimitHit
Provider rule

Provider adapter does not own workflow policy.

Provider adapter may:

send request;
parse provider response;
classify provider-specific error;
return raw usage if available.

Provider adapter must not:

decide Workbench stage transition;
decide Prompt A fallback policy;
decide artifact persistence;
directly mutate queue item status.
4.3. Artifact Runtime
Назначение

Generic persistence runtime для промежуточных и финальных результатов pipeline/workflow.

Ему безразлично, что именно сохраняется:

Prompt A claim observations;
Prompt C consolidated surfaces;
raw LLM output;
validation errors;
dialog memory snapshot;
retrieval trace;
cluster draft;
tool result.

Artifact Runtime знает:

artifact
artifact kind
lineage
parent/child links
stage checkpoint
retention policy
resume policy
temporary vs durable results
Владение

Artifact Runtime владеет:

PipelineArtifact;
ArtifactKind;
ArtifactRef;
ArtifactLineage;
RetentionPolicy;
StageCheckpoint;
ResumePolicy.
Не владеет

Artifact Runtime не владеет:

semantic meaning of claim;
retrieval quality;
business answer correctness;
LLM model selection;
work item leasing;
frontend display policy.
Паттерны
Entity:
  PipelineArtifact

Value Object:
  ArtifactKind
  ArtifactRef
  RetentionPolicy
  ArtifactVisibility
  ArtifactStatus

Use Case:
  PersistArtifact
  SupersedeArtifact
  LoadArtifactsForResume
  ApplyRetentionPolicy

Unit of Work:
  required when artifact persistence is committed with work item completion

Domain Events:
  ArtifactPersisted
  ArtifactSuperseded
  ArtifactRejected
  ArtifactPublished
  ArtifactExpired
Critical rule

Artifact existence is the checkpoint.

Queue status is not the artifact.

Old statuses such as:

CLAIM_OBSERVATIONS_PERSISTED
REGISTRY_APPLICATION_QUEUED
REGISTRY_APPLICATION_APPLIED

are legacy status/checkpoint hybrids.

They must not become canonical lifecycle states.

4.4. Knowledge Workbench
Назначение

Quality-control panel and lifecycle manager for knowledge engineering.

Knowledge Workbench is not the generic execution runtime.

Knowledge Workbench is not the LLM runtime.

Knowledge Workbench is not the artifact store.

Knowledge Workbench owns the meaning of knowledge surfaces and the quality workflow.

Subdomains

Knowledge Workbench contains these subdomains:

Source Management
Knowledge Extraction
Surface Consolidation
RAG Enrichment
Retrieval Evaluation
Manual Curation
Publication
5. Knowledge Workbench subdomains
5.1. Source Management
Назначение

Загрузка, нормализация и структурирование источников.

Владение
SourceDocument;
SourceUnit;
SourceRef;
document format adapters;
sectioning/splitting policy;
source lineage.
Паттерны
Entity:
  SourceDocument
  SourceUnit

Value Object:
  SourceRef
  SourceFormat
  SourceUnitKind
  SplitReason
  HeadingPath

Use Cases:
  UploadSourceDocument
  NormalizeSourceDocument
  SplitSourceDocument
  CreateSourceUnits

Ports:
  SourceParserPort

Adapters:
  MarkdownSourceParser
  PdfSourceParser
  ExcelSourceParser
  HtmlSourceParser
Rule

Markdown is an adapter, not the domain.

5.2. Knowledge Extraction
Назначение

Извлечение чернового знания из source units.

Prompt A belongs here as one extraction adapter/use case, not as LLM runtime.

Владение
ClaimObservation;
DraftSurface;
evidence refs;
possible questions;
exclusion scope;
extraction confidence/review flags.
Паттерны
Entity:
  ClaimObservation
  DraftSurface

Value Object:
  EvidenceRef
  PossibleQuestion
  ExclusionScope
  Granularity
  ExtractionConfidence

Use Case:
  ExtractKnowledgeFromSourceUnit

Port:
  ClaimExtractionPort

Adapter:
  PromptAClaimExtractionAdapter

State Machine:
  DraftSurfaceReviewStateMachine if review lifecycle is needed
Rule

Prompt A does not own:

model fallback;
provider routing;
quota;
lease;
artifact persistence;
stage transition.
5.3. Surface Consolidation
Назначение

Intent-centered consolidation of draft claims/surfaces.

This is the real meaning of Prompt C.

Prompt C finds claims/surfaces that answer the same user intent, deduplicates them, enriches them with each other, and returns self-contained consolidated surfaces.

Владение
CanonicalIntent;
SurfaceCandidate;
ConsolidatedSurface;
merge lineage;
conflict flags;
review-needed decisions.
Паттерны
Entity:
  SurfaceCandidate
  ConsolidatedSurface

Value Object:
  CanonicalIntent
  MergeDecision
  ConflictNote
  SurfaceRelation
  SurfaceKind

Use Case:
  ConsolidateSurfacesByIntent

Port:
  SurfaceConsolidationPort

Adapter:
  PromptCConsolidationAdapter

State Machine:
  ConsolidationReviewStateMachine if manual review is required
Naming rule

Old terms:

RegistryMerge
CanonicalRegistryMerge
QuestionRegistry

must be treated carefully.

Target meaning is:

SurfaceConsolidation
IntentConsolidation
5.4. RAG Enrichment
Назначение

Обогащение retrieval surfaces для улучшения RAG.

Владение
paraphrases;
tags;
synonyms;
retrieval hints;
negative hints;
embedding text variants;
enrichment proposals;
enrichment review status.
Паттерны
Entity:
  EnrichmentProposal

Value Object:
  QueryVariant
  RetrievalTag
  RetrievalHint
  NegativeHint
  EnrichmentMetric

Use Case:
  ProposeSurfaceEnrichment
  EvaluateSurfaceEnrichment
  AcceptSurfaceEnrichment
  RejectSurfaceEnrichment

State Machine:
  EnrichmentProposalStateMachine
Critical rule

Generated enrichment is not automatically good.

It must be checked by retrieval evaluation or manual review.

5.5. Retrieval Evaluation
Назначение

Проверка качества retrieval before/after enrichment and before publication.

Владение
retrieval test cases;
expected surfaces;
retrieval results;
false positives;
false negatives;
before/after metrics;
production simulation.
Паттерны
Entity:
  RetrievalEvalRun
  RetrievalEvalCase
  RetrievalEvalResult

Value Object:
  RetrievalMetric
  RetrievalQuery
  ExpectedSurfaceRef

Use Case:
  RunRetrievalEvaluation
  CompareEnrichmentBeforeAfter
  ApproveGoodRetrievalResults
  RejectBadRetrievalResults

Read Model:
  RetrievalEvalSummary
5.6. Manual Curation
Назначение

Ручная работа пользователя с knowledge surfaces.

Владение
edit surface;
delete surface;
hide/reject surface;
merge/split surface;
approve/reject enrichment;
approve publication;
review flags.
Паттерны
Entity:
  CurationDecision
  ReviewItem

Value Object:
  ReviewReason
  ManualEditPatch
  CuratorRef

Use Cases:
  EditKnowledgeSurface
  RejectKnowledgeSurface
  ApproveKnowledgeSurface
  MergeKnowledgeSurfaces
  SplitKnowledgeSurface
  AcceptEnrichment
  RejectEnrichment
5.7. Publication
Назначение

Публикация curated knowledge into production retrieval.

Владение
production knowledge surface;
final embeddings;
publication version;
active projection;
retention cleanup;
rollback metadata.
Паттерны
Entity:
  KnowledgeSurface
  PublicationRun
  PublicationVersion

Value Object:
  PublicationStatus
  RuntimeProjectionRef

Use Case:
  PublishKnowledgeSurfaces
  UnpublishKnowledgeSurface
  RebuildRuntimeProjection
  CleanupIntermediateArtifacts

State Machine:
  PublicationStateMachine

Domain Events:
  KnowledgeSurfacePublished
  KnowledgeSurfaceUnpublished
  PublicationCompleted
6. Conversation and answer contexts
6.1. Conversation Runtime
Назначение

Runtime клиентского диалога.

Владение
client thread;
messages;
turns;
runtime state;
recent history;
session locks;
answer orchestration invocation.
Паттерны
Entity:
  ClientThread
  ClientMessage
  ConversationTurn

Value Object:
  ThreadId
  ChannelMessageId
  ConversationState

Use Cases:
  ReceiveClientMessage
  ProcessClientMessage
  PersistAssistantReply
6.2. Answer Orchestration
Назначение

Принятие решения, как отвечать клиенту.

Владение
intent classification;
required evidence plan;
retrieval/operational evidence collection;
source authority resolution;
missing slot decision;
final answer generation or escalation.
Паттерны
Entity:
  AnswerPlan
  EvidencePlan

Value Object:
  AnswerPolicyDecision
  MissingSlot
  EvidenceRequirement

Use Case:
  GenerateClientAnswer

Saga / Process Manager:
  ClientAnswerProcess

Domain Events:
  ClientAnswerGenerated
  ClientAnswerEscalated
6.3. Evidence Authority
Назначение

Правила источников правды.

Владение
source priority;
conflict resolution;
authority decision;
evidence rejection reason.
Паттерны
Value Object:
  EvidenceRef
  AuthorityDecision
  SourcePriority
  EvidenceRejectionReason

Domain Service:
  EvidenceAuthorityResolver
Rule

LLM output is never authoritative evidence.

6.4. Human Handoff
Назначение

Escalation to manager and manager reply workflow.

Владение
escalation reason;
manager assignment;
manager session;
manager reply;
handoff status;
manager-visible reason.
Паттерны
Entity:
  HandoffSession
  ManagerReply

Value Object:
  HandoffReason
  ManagerRef

Use Cases:
  EscalateToManager
  AssignManager
  SendManagerReply
  CloseHandoff
7. Commercial and operational contexts
7.1. Commercial Catalog
Назначение

Commercial/pricing facts.

Владение
product/service/offer;
price point;
price fact;
variant axis;
quote input;
missing commercial slot;
price query intent.
Паттерны
Entity:
  Offer
  PriceFact
  OfferGroup

Value Object:
  Money
  Currency
  VariantAxis
  PriceCondition
  PriceFreshness

Use Cases:
  CompilePriceList
  AnswerPriceQuery
  CalculateQuote
7.2. CRM Operational Context
Назначение

Live operational state.

Владение
order/deal state;
live availability;
stock;
discounts;
bookings;
assigned manager;
current ticket state;
CRM sync state.
Rule

Live CRM state must not be stored as ordinary retrieval surface unless explicitly compiled into a snapshot with freshness metadata.

7.3. Action Safety
Назначение

Approval and safety for executable actions.

Владение
action permission;
policy approval;
user confirmation;
manager confirmation;
safe mutation boundary.
Паттерны
Value Object:
  ActionRequest
  ActionApprovalDecision
  SafetyPolicy

Use Case:
  ApproveAction
  RejectAction
  RequireManagerApproval

Domain Service:
  ActionSafetyPolicy
8. Audit / Observability
Назначение

Durable trace of important runtime decisions.

Владение
what evidence was used;
which source won;
which source was rejected;
why manager was called;
which tool was executed;
which policy blocked action;
what was sent to customer;
usage/cost rollups;
workflow progress summaries.
Паттерны
Entity:
  AuditTrace
  UsageRollup

Value Object:
  TraceRef
  CostEstimate
  UsageMetric

Event Handler:
  UsageRollupProjector
  AuditTraceProjector

Read Models:
  WorkbenchProcessingSummary
  StageProgressSummary
  UsageSummary
  RetrievalEvalSummary
9. Use Case placement rules

New use cases must not be placed in generic application/services by default.

Target placement:

src/contexts/<context>/application/use_cases/

Example:

src/contexts/knowledge_workbench/extraction/application/use_cases/extract_knowledge_from_source_unit.py
src/contexts/execution_runtime/application/use_cases/lease_work_item.py
src/contexts/llm_runtime/application/use_cases/execute_llm_task.py
src/contexts/artifact_runtime/application/use_cases/persist_artifact.py

Use case naming must be verb-first:

UploadSourceDocument
SplitSourceDocument
ExtractKnowledgeFromSourceUnit
ConsolidateSurfacesByIntent
RunRetrievalEvaluation
PublishKnowledgeSurfaces
ExecuteLlmTask
LeaseWorkItem
PersistArtifact
10. Unit of Work rules

A Unit of Work is required when a use case must commit multiple state changes atomically.

Examples:

Persist artifact
+ mark work item completed
+ update stage progress
+ record usage
+ append outbox event
Cancel processing run
+ cancel active work items
+ mark stage cancelled/deferred
+ preserve completed artifacts
+ append cancellation event
Publish surfaces
+ create publication version
+ mark surfaces published
+ generate final embeddings
+ apply retention policy to intermediate artifacts
+ append publication event

Unit of Work owns transaction boundary.

Repositories must not independently commit partial business workflows.

11. State Machine rules

Any entity with lifecycle needs an explicit State Machine.

Required state machines:

WorkItemStateMachine
LlmTaskStateMachine
StageRunStateMachine
ProcessingRunStateMachine
PublicationStateMachine
EnrichmentProposalStateMachine

Forbidden pattern:

item.status = new_status
repository.update_item(item)

Required pattern:

state_machine.transition(entity, command)
repository.save(entity)

or explicit methods:

work_item_state_machine.complete_leased(...)
work_item_state_machine.defer_leased(...)
work_item_state_machine.fail_leased(...)
12. Saga / Process Manager rules

Long-running multi-step workflows must be process managers/sagas.

Required saga:

DocumentKnowledgeProcessingSaga

It coordinates:

upload
→ source split
→ claim extraction
→ deterministic cleanup
→ embeddings
→ clustering
→ surface consolidation
→ retrieval evaluation
→ manual review
→ publication
→ cleanup

Saga does not perform LLM request directly.

Saga decides next step based on events/state.

Possible events:

SourceUnitsCreated
ExtractionStageCompleted
ExtractionStageBlockedByQuota
DailyLimitExhausted
UserChoseDegradedFallback
CleanupCompleted
EmbeddingsBuilt
ClustersCreated
ConsolidationCompleted
ReviewApproved
PublicationCompleted
ProcessingCancelled
13. Outbox / Event rules

Domain events that must survive process crash go to transactional outbox.

Required events:

WorkItemCompleted
WorkItemDeferred
ArtifactPersisted
LlmTaskSucceeded
LlmTaskFailed
StageCompleted
DailyLimitExhausted
UserChoiceRequired
KnowledgeSurfacePublished
ClientAnswerGenerated
ManagerEscalationCreated

Outbox event creation must be committed with the state change that caused it.

No direct “do everything now” side effects inside use case if event handler is appropriate.

14. Read Model / CQRS rules

Frontend and dashboard state must not be computed by expensive traversal of all workflow tables on every request.

Read models/projections are allowed and expected.

Required read models:

WorkbenchProcessingSummary
StageProgressSummary
QuotaWaitSummary
ReviewQueueSummary
RetrievalEvalSummary
UsageSummary

Read model is not source of truth.

Read model can be rebuilt from entities/artifacts/events if needed.

15. Ports and Adapters rules

Ports belong to application layer of the context that owns the need.

Adapters belong to infrastructure.

Examples:

LLM Runtime:
  Port: LlmProviderPort
  Adapter: GroqProviderAdapter

Source Management:
  Port: SourceParserPort
  Adapter: MarkdownSourceParser

Artifact Runtime:
  Port: ArtifactRepositoryPort
  Adapter: PostgresArtifactRepository

Execution Runtime:
  Port: WorkItemRepositoryPort
  Adapter: PostgresWorkItemRepository

Conversation Runtime:
  Port: MessageDeliveryPort
  Adapter: TelegramDeliveryAdapter

Adapter must not own business policy.

16. Canonical vocabulary
Core distinctions
WorkItem != LlmTask != PipelineArtifact
SourceUnit != DraftSurface != KnowledgeSurface
PromptA != KnowledgeExtraction
PromptC != LlmRuntime
Groq != LlmRuntime
Queue != Pipeline
Artifact != DTO
DTO != Entity
Repository != UseCase
Service != StateMachine
Canonical names
WorkItem
LlmTask
LlmAttempt
PipelineArtifact
SourceDocument
SourceUnit
ClaimObservation
DraftSurface
ConsolidatedSurface
KnowledgeSurface
RetrievalSurface
ProcessingRun
StageRun
PublicationRun
ClientThread
ClientMessage
HandoffSession
Deprecated / legacy names requiring care
SectionBatchQueueItem:
  legacy hybrid, not canonical WorkItem

CLAIM_OBSERVATIONS_PERSISTED:
  legacy status/checkpoint hybrid

REGISTRY_APPLICATION_QUEUED:
  legacy status/downstream queue marker hybrid

REGISTRY_APPLICATION_APPLIED:
  legacy status/checkpoint hybrid

RegistryMerge:
  old naming; target meaning is SurfaceConsolidation / IntentConsolidation

FAQ:
  legacy product naming; target domain is Knowledge Workbench

NodeRun:
  may be artifact/attempt source, but not canonical Artifact Runtime entity unless redefined

QueueItem:
  too generic; use WorkItem inside Execution Runtime
17. New file placement rules

New canonical code must go under src/contexts.

Examples:

src/contexts/execution_runtime/domain/entities/work_item.py
src/contexts/execution_runtime/domain/state_machines/work_item_state_machine.py
src/contexts/execution_runtime/application/use_cases/lease_work_item.py
src/contexts/execution_runtime/application/ports/work_item_repository.py
src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_repository.py
src/contexts/llm_runtime/domain/entities/llm_task.py
src/contexts/llm_runtime/domain/value_objects/quota_decision.py
src/contexts/llm_runtime/application/use_cases/execute_llm_task.py
src/contexts/llm_runtime/infrastructure/providers/groq/groq_provider_adapter.py
src/contexts/artifact_runtime/domain/entities/pipeline_artifact.py
src/contexts/artifact_runtime/application/use_cases/persist_artifact.py
src/contexts/artifact_runtime/infrastructure/postgres/postgres_artifact_repository.py
src/contexts/knowledge_workbench/extraction/domain/entities/claim_observation.py
src/contexts/knowledge_workbench/extraction/application/use_cases/extract_knowledge_from_source_unit.py
src/contexts/knowledge_workbench/extraction/infrastructure/llm/prompt_a_claim_extraction_adapter.py

Old files may remain in old locations during migration, but must be classified.

18. Migration strategy

Do not physically move the entire project first.

Preferred order:

1. Add bounded context map and canonical vocabulary.
2. Add new context folders.
3. Add new canonical entities/value objects/state machines/use cases there.
4. Keep old files as adapters where necessary.
5. Cut over one vertical slice at a time.
6. Add architecture tests preventing new code in retired paths.
7. Retire old paths only after replacement is active.

First vertical slice candidate:

Prompt A section processing

But it must be implemented through:

Execution Runtime WorkItem
LLM Runtime LlmTask
Artifact Runtime PipelineArtifact
Knowledge Workbench Extraction
Unit of Work
State Machine
Outbox event

Not through another patch inside old Prompt A service/queue handler.

19. Guard rules for future agents

Future coding agents must obey:

1. Do not create new generic services without bounded context.
2. Do not introduce synonyms for canonical concepts.
3. Do not extend ADAPTER/LEGACY/RETIRED concepts as production path.
4. Do not put workflow policy inside provider adapters.
5. Do not put artifact meaning inside queue statuses.
6. Do not mutate lifecycle statuses without state machine.
7. Do not commit multi-entity workflow updates without Unit of Work.
8. Do not use DTO as domain model.
9. Do not make frontend hide backend lifecycle confusion.
10. Do not create new database tables before naming their owning bounded context.
20. Summary

The problem is not lack of code.

The problem is that architectural responsibilities are currently collapsed into services, repositories, DTOs and status strings.

The target architecture must explicitly use:

Bounded Contexts
Entities
Value Objects
Use Cases
State Machines
Unit of Work
Sagas / Process Managers
Domain Events
Outbox
Read Models
Ports and Adapters

The immediate goal is not to apply every pattern everywhere.

The immediate goal is to put the right patterns at the boundaries where the project already hurts:

Execution Runtime
LLM Runtime
Artifact Runtime
Knowledge Workbench
Conversation Runtime

Once these boundaries are fixed, new functionality can be added without constantly duplicating names, inventing parallel services, and mixing old and new semantics.
