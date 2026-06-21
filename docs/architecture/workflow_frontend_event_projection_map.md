# Workflow Frontend Event Projection Map

## 1. Executive summary

Текущий realtime-контур не передаёт frontend канонические workflow events. Любой
`WorkflowEvent`, записанный в `workflow_runtime_outbox_events`, вызывает
`pg_notify('workflow_live_state_changed', ...)`; SSE endpoint получает уведомление,
заново выполняет тяжёлый multi-query live-state и отправляет клиенту полный snapshot.

Целевой контракт должен оставить backend workflow source of truth, но заменить
повторную передачу snapshot на упорядоченные typed event projections:

```text
canonical workflow event
→ frontend projection envelope
→ reducer/idempotent patch
→ конкретная строка или виджет KnowledgeDocumentCard
```

Ключевые выводы аудита:

- canonical contract содержит 9 phases, 15 commands, 15 operations и 44 events;
- durable phase vocabulary требует отдельной сверки: migration 090 содержит
  `PROMPT_A_*` constraints, тогда как текущий Python пишет `CLAIM_BUILDER_*`;
- 13 commands зарегистрированы в generic handler map;
- start и source ingestion выполняются специальным upload/ingestion path;
- после `DraftClaimClustersBuilt` workflow продолжается в draft-claim compaction без
  отдельной preview/review pause phase;
- ряд contract events не emitится: started/deferred/all-sections-extracted являются
  наиболее заметными gaps;
- все operations имеют `frontend_visibility=True`, но связь event → projection → UI
  нигде не проверяется;
- SSE несёт полный snapshot, теряет `sequence_number` из notification и не имеет
  reconnect/cursor protocol;
- HTTP GET live-state имеет side effect: запускает background workflow drain;
- frontend подписывает только первые шесть документов;
- миграция должна сначала стабилизировать event envelope/cursor и payloads, затем
  добавить reducer рядом со snapshot, и только после сверки убрать snapshot из
  realtime transport. Сам snapshot read model пока нужен для bootstrap/recovery.

Источники: `knowledge_extraction_workflow_definition.py`,
`knowledge_extraction_command_handler_map.py`, command handlers в
`src/contexts/knowledge_workbench/application/sagas/`,
`faq_workbench_workflow_live_state.py`, `knowledge.py`,
`frontend/src/shared/api/modules/knowledge.ts`, `KnowledgePage.tsx` и
`KnowledgeDocumentCard.tsx`.

## 2. Current root problem

Текущий путь:

```text
handler → outbox INSERT → PostgreSQL NOTIFY
       → SSE listener → полный fetch_workbench_workflow_live_state()
       → полный JSON snapshot → React Query replacement
```

Проблемы:

1. Уведомление уже содержит `sequence_number`, `event_id`, `event_type`,
   `workflow_run_id`, `occurred_at`, но SSE отбрасывает их и передаёт новый snapshot.
2. Один event вызывает повторное чтение workflow run, progress, usage, execution
   items, attempts, capacity observations, timeline, clusters, comparisons,
   compacted nodes и curation workspace.
3. Snapshot является одновременно bootstrap model, realtime transport и
   compatibility API. Эти роли не разделены.
4. Frontend не может дедуплицировать или детерминированно применять изменения:
   transport не передаёт monotonic cursor.
5. Потеря notification частично маскируется полным refetch, но последнее потерянное
   уведомление оставляет UI stale.
6. GET `/workflow-live-state` запускает background drain. Read path меняет runtime.
7. На каждый документ создаётся отдельный PostgreSQL LISTEN connection; frontend
   ограничивает это `.slice(0, 6)`.
8. SSE route отсутствует в generated OpenAPI; HTTP response в generated schema
   фактически `unknown`, а TypeScript contract поддерживается вручную.
9. Durable state, canonical operation contract и frontend labels используют
   несколько phase vocabularies. В найденных migrations нет очевидной forward
   migration, обновляющей migration 090 с `PROMPT_A_*` на текущие
   `CLAIM_BUILDER_*` constraints. Это потенциальный constraint violation на
   свежей БД и блокер для надёжной event projection.

Целевая граница:

- snapshot endpoint остаётся bootstrap/recovery read model;
- realtime endpoint передаёт typed projection events с cursor;
- reducer обновляет только затронутые projections;
- event payload не обязан повторять persistence row, но обязан содержать все поля,
  необходимые для deterministic patch без немедленного full refetch;
- background drain не должен зависеть от frontend read.

## 3. Canonical workflow phases

Источник:
`src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_workflow_definition.py`.

| phase | Meaning / current operations |
|---|---|
| `WORKFLOW_STARTED` | Создание workflow run; special entry path. |
| `SOURCE_INGESTION` | Persist source document и create source units. |
| `CLAIM_BUILDER_WORK_SCHEDULING` | Создание execution work items для source units. |
| `CLAIM_BUILDER_SECTION_EXTRACTION` | Capacity admission, lease, LLM attempt, claim persistence, split и reconciliation. |
| `DRAFT_CLAIM_EMBEDDING` | Batch embedding draft claims. |
| `DRAFT_CLAIM_CLUSTERING` | Cluster plan, compaction dispatch/execution/application/reconciliation. |
| `DRAFT_CLAIM_CURATION` | Открытие manual curation workspace. |
| `PUBLICATION` | Atomic publication canonical facts, retrieval entries и embeddings. |
| `COMPLETED` | Terminal phase; отдельной operation нет, состояние выставляет publication handler. |

Legacy phase vocabulary всё ещё присутствует в saga state и migration map. Для
frontend projection protocol следует передавать canonical phase и не заставлять
frontend повторять `LEGACY_PHASE_MIGRATION_MAP`.

## 4. Canonical commands

| command | Execution path |
|---|---|
| `StartKnowledgeExtractionWorkflow` | Special after-upload/start path; не зарегистрирован в generic map. |
| `IngestSourceDocument` | Special source-ingestion path; не зарегистрирован в generic map. |
| `ScheduleClaimBuilderSectionWork` | `HandleScheduleClaimBuilderSectionWorkCommandHandler`. |
| `PrepareClaimBuilderDispatchBatch` | `HandlePrepareClaimBuilderDispatchBatchCommandHandler`. |
| `SplitClaimBuilderSourceUnit` | `HandleSplitClaimBuilderSourceUnitCommandHandler`. |
| `ExecuteClaimBuilderSection` | `HandleExecuteClaimBuilderSectionCommandHandler`. |
| `ReconcileClaimBuilderProgress` | `HandleReconcileClaimBuilderProgressCommandHandler`. |
| `GenerateDraftClaimEmbeddings` | `HandleGenerateDraftClaimEmbeddingsCommandHandler`. |
| `ClusterDraftClaims` | `HandleClusterDraftClaimsCommandHandler`. |
| `PrepareDraftClaimCompactionDispatchBatch` | `HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler`. |
| `ExecuteDraftClaimCompaction` | `HandleExecuteDraftClaimCompactionCommandHandler`. |
| `ApplyDraftClaimCompactionResult` | `HandleApplyDraftClaimCompactionResultCommandHandler`. |
| `ReconcileDraftClaimCompactionProgress` | `HandleReconcileDraftClaimCompactionProgressCommandHandler`. |
| `OpenDraftClaimCurationWorkspace` | `HandleOpenDraftClaimCurationWorkspaceCommandHandler`. |
| `PublishDraftClaimCurationWorkspace` | `HandlePublishDraftClaimCurationWorkspaceCommandHandler`. |

Текущий workflow не содержит отдельной cluster preview / cluster contract review
phase. После `DraftClaimClustersBuilt` workflow продолжается в draft-claim
compaction. Cluster card/detail UI должен строиться из compaction/cluster read
models или explicit cluster projections, а не из удалённых preview/review events.

## 5. Canonical event inventory

`WorkflowManuallyPaused` и `WorkflowManuallyResumed` являются out-of-band control
events. Остальные events связаны с operation contract.

| canonical event | Actual emission status | Primary read-model effect |
|---|---|---|
| `KnowledgeExtractionWorkflowStarted` | Special start path; не generic handler. | header, phase, timer, timeline |
| `SourceDocumentPersisted` | Emit в source-ingestion effects. | document/header, timeline |
| `SourceUnitsCreated` | Emit в source-ingestion effects. | source stage/count, timeline |
| `ClaimBuilderSectionWorkScheduled` | Emit. | section lanes, progress |
| `ClaimBuilderDispatchBatchPrepared` | Emit только при `prepared_dispatch_count > 0`. | active attempts/lanes |
| `ClaimBuilderSectionExtractionStarted` | **Не emitится handler’ом.** Lease/attempt rows заменяют event. | active attempts |
| `ClaimBuilderSectionExtracted` | Emit. | lane item, claims, usage |
| `ClaimBuilderSectionExtractionDeferred` | **Не emitится:** deferred маппится в retryable failed event. | lane item/retry |
| `ClaimBuilderSectionExtractionRetryableFailed` | Emit для deferred и retryable. | lane item/retry |
| `ClaimBuilderSectionExtractionTerminalFailed` | Emit. | lane item/error |
| `ClaimBuilderSectionSplitRequired` | **Не emitится execution handler.** | lane/source split warning |
| `ClaimBuilderSourceUnitSplitRequired` | Emit prepare handler. | source split warning |
| `ClaimBuilderSourceUnitSplitCompleted` | Emit split handler. | source units/lanes |
| `LlmProviderCapacityObserved` | Emit execute claim/compaction handlers. | capacity/attempt |
| `ClaimBuilderProgressReconciled` | Emit. | progress/stage |
| `ClaimBuilderAllSectionsExtracted` | **Не emitится reconcile handler.** | phase transition |
| `DraftClaimEmbeddingBatchCompleted` | Emit per batch. | embedding progress |
| `DraftClaimEmbeddingsGenerated` | Emit terminal embedding result. | stage/result |
| `DraftClaimClustersBuilt` | Emit. | clusters/stage |
| `DraftClaimCompactionDispatchBatchPrepared` | Emit при prepared attempts. | cluster work counts |
| `DraftClaimCompactionAttemptStarted` | **Не emitится handler’ом.** | attempts/cluster work |
| `DraftClaimCompactionAttemptCompleted` | Emit. | attempt/cluster work/usage |
| `DraftClaimCompactionAttemptRetryableFailed` | Emit. | attempt/retry |
| `DraftClaimCompactionAttemptTerminalFailed` | Emit. | attempt/error |
| `DraftClaimCompactionResultApplied` | Emit. | comparisons/nodes |
| `DraftClaimCompactionNextWorkScheduled` | Emit conditionally. | cluster work counts |
| `DraftClaimCompactionWaitingUserModelChoice` | Emit prepare/apply/reconcile paths. | action/warning |
| `DraftClaimCompactionUserModelChoiceResolved` | Emit confirmation use case, не prepare handler. | action removal/timeline |
| `DraftClaimCompactionClusterDone` | Emit conditionally. | cluster status |
| `DraftClaimCompactionProgressReconciled` | Emit. | stage/cluster counters |
| `DraftClaimCompactionAllGroupsCompacted` | Emit conditionally. | phase transition |
| `DraftClaimCurationWorkspaceOpened` | Emit. | curation availability |
| `DraftClaimCurationReviewRequired` | Emit. | action/header |
| `DraftClaimCurationWorkspacePublished` | Emit. | publication/completed state |
| `WorkflowManuallyPaused` | Emit pause use case. | header/timer/actions |
| `WorkflowManuallyResumed` | Emit resume use case. | header/timer/actions |

Также фактически существуют timeline-only pseudo-events, которых нет в canonical
enum, например `ClaimBuilderDispatchBatchPreparedZero` и capacity-throttled
entries. Они не должны становиться неявным frontend event contract.

## 6. Operation contract matrix

| operation | phase | command | success event | intermediate events | failure events | next commands | read models | frontend visible |
|---|---|---|---|---|---|---|---|---|
| `start_knowledge_extraction_workflow` | `WORKFLOW_STARTED` | `StartKnowledgeExtractionWorkflow` | `KnowledgeExtractionWorkflowStarted` | — | — | `IngestSourceDocument` | progress, timeline | yes |
| `ingest_source_document` | `SOURCE_INGESTION` | `IngestSourceDocument` | `SourceUnitsCreated` | `SourceDocumentPersisted` | — | `ScheduleClaimBuilderSectionWork` | progress, timeline | yes |
| `schedule_claim_builder_section_work` | `CLAIM_BUILDER_WORK_SCHEDULING` | `ScheduleClaimBuilderSectionWork` | `ClaimBuilderSectionWorkScheduled` | — | — | `PrepareClaimBuilderDispatchBatch` | progress, timeline | yes |
| `prepare_claim_builder_dispatch_batch` | `CLAIM_BUILDER_SECTION_EXTRACTION` | `PrepareClaimBuilderDispatchBatch` | `ClaimBuilderDispatchBatchPrepared` | `ClaimBuilderSourceUnitSplitRequired` | — | `ExecuteClaimBuilderSection`, `SplitClaimBuilderSourceUnit` | attempts, capacity, progress, timeline | yes |
| `split_claim_builder_source_unit` | `CLAIM_BUILDER_SECTION_EXTRACTION` | `SplitClaimBuilderSourceUnit` | `ClaimBuilderSourceUnitSplitCompleted` | — | — | `ScheduleClaimBuilderSectionWork` | attempts, progress, timeline | yes |
| `execute_claim_builder_section` | `CLAIM_BUILDER_SECTION_EXTRACTION` | `ExecuteClaimBuilderSection` | `ClaimBuilderSectionExtracted` | `ClaimBuilderSectionExtractionStarted`, `LlmProviderCapacityObserved` | deferred, retryable, terminal, split required | `ReconcileClaimBuilderProgress` | progress, attempts, claims, timeline, capacity | yes |
| `reconcile_claim_builder_progress` | `CLAIM_BUILDER_SECTION_EXTRACTION` | `ReconcileClaimBuilderProgress` | `ClaimBuilderAllSectionsExtracted` | `ClaimBuilderProgressReconciled` | — | `GenerateDraftClaimEmbeddings` | progress, attempts, timeline | yes |
| `generate_draft_claim_embeddings` | `DRAFT_CLAIM_EMBEDDING` | `GenerateDraftClaimEmbeddings` | `DraftClaimEmbeddingsGenerated` | `DraftClaimEmbeddingBatchCompleted` | — | `ClusterDraftClaims` | progress, claims, timeline | yes |
| `cluster_draft_claims` | `DRAFT_CLAIM_CLUSTERING` | `ClusterDraftClaims` | `DraftClaimClustersBuilt` | — | — | `PrepareDraftClaimCompactionDispatchBatch` | progress, timeline | yes |
| `prepare_draft_claim_compaction_dispatch_batch` | `DRAFT_CLAIM_CLUSTERING` | `PrepareDraftClaimCompactionDispatchBatch` | `DraftClaimCompactionDispatchBatchPrepared` | `DraftClaimCompactionUserModelChoiceResolved` | — | `ExecuteDraftClaimCompaction` | attempts, capacity, progress, timeline | yes |
| `execute_draft_claim_compaction` | `DRAFT_CLAIM_CLUSTERING` | `ExecuteDraftClaimCompaction` | `DraftClaimCompactionAttemptCompleted` | `DraftClaimCompactionAttemptStarted`, `LlmProviderCapacityObserved` | retryable, terminal | `ApplyDraftClaimCompactionResult`, `ReconcileDraftClaimCompactionProgress` | progress, attempts, capacity, timeline | yes |
| `apply_draft_claim_compaction_result` | `DRAFT_CLAIM_CLUSTERING` | `ApplyDraftClaimCompactionResult` | `DraftClaimCompactionResultApplied` | next work, waiting choice, cluster done | — | dynamically appended continuation commands | progress, attempts, timeline | yes |
| `reconcile_draft_claim_compaction_progress` | `DRAFT_CLAIM_CLUSTERING` | `ReconcileDraftClaimCompactionProgress` | `DraftClaimCompactionAllGroupsCompacted` | progress reconciled, waiting choice | — | `OpenDraftClaimCurationWorkspace` | progress, attempts, timeline | yes |
| `open_draft_claim_curation_workspace` | `DRAFT_CLAIM_CURATION` | `OpenDraftClaimCurationWorkspace` | `DraftClaimCurationWorkspaceOpened` | `DraftClaimCurationReviewRequired` | — | — | progress, timeline | yes |
| `publish_draft_claim_curation_workspace` | `PUBLICATION` | `PublishDraftClaimCurationWorkspace` | `DraftClaimCurationWorkspacePublished` | — | — | — | progress, timeline | yes |

Recovery scopes, в порядке contract:

- workflow: start, ingestion, curation, publication;
- phase/source unit: ingestion, scheduling, reconciliation;
- work item attempt/section: prepare/execute/split claim builder;
- embedding batch: embedding;
- cluster build/work item attempt: clustering/compaction;
- curation workspace/publication: terminal manual paths.

## 7. Handler emission matrix

| handler file | command | DB writes | actual events emitted | timeline writes | progress writes | next commands | contract gaps |
|---|---|---|---|---|---|---|---|
| special start path (`start_source_ingestion_workflow.py`, after-upload composition) | `StartKnowledgeExtractionWorkflow` | workflow run/checkpoints/command log | workflow-started path | start timeline | initial progress | ingest | Не представлен в generic handler map; необходимо окончательно подтвердить единый event payload. |
| `apply_source_ingestion_workflow_effects.py` + source persistence use cases | `IngestSourceDocument` | `source_documents`, `knowledge_workbench_documents`, `source_units`, saga state/checkpoints, command/outbox | `SourceDocumentPersisted`, `SourceUnitsCreated` | command completed, оба events, next command | source unit counters | schedule section work | Нет gap по declared events. |
| `handle_schedule_claim_builder_section_work_command.py` | schedule | execution work items/schedules, command/outbox | scheduled | scheduled + next command | scheduled totals | prepare dispatch | — |
| `handle_prepare_claim_builder_dispatch_batch_command.py` | prepare claim dispatch | lease/attempt/dispatch via composition; command/outbox | batch prepared или source split required | prepared attempts, split, zero-dispatch/capacity throttle | prepared/capacity metadata | execute items или split; может reschedule same command | Нет typed event для zero dispatch/window exhausted/wakeup. |
| `handle_split_claim_builder_source_unit_command.py` | split | source units, superseded/scheduled work, command/outbox | split completed | split completed/reschedule | source/work counts | schedule work | — |
| `handle_execute_claim_builder_section_command.py` | execute section | attempt outcome, validated claims, usage/capacity observation, command/outbox | extracted, retryable, terminal, capacity observed | outcome | work/claim/error counters | reconcile + capacity wakeup | Не emitит extraction started, deferred, section split required; deferred collapses into retryable. |
| `handle_reconcile_claim_builder_progress_command.py` | reconcile claim | command/outbox | progress reconciled | reconciliation | aggregate work counters | embeddings when complete/eligible | Не emitит success `ClaimBuilderAllSectionsExtracted`. |
| `handle_generate_draft_claim_embeddings_command.py` | embeddings | `draft_claim_embeddings`, command/outbox | batch completed, embeddings generated | embedding completion | embedding counters | cluster | — |
| `handle_cluster_draft_claims_command.py` | cluster | compaction groups/edges/members/batches, command/outbox | clusters built | cluster/plan built | cluster counters | prepare compaction | — |
| `handle_prepare_draft_claim_compaction_dispatch_batch_command.py` | prepare compaction | lease/attempt/dispatch, command/outbox | batch prepared, waiting user choice | prepared/capacity/waiting | cluster work counts | execute items; may reschedule same command | Contract declares user-choice-resolved here, but resolution emitится другим use case. Нет window events. |
| `handle_execute_draft_claim_compaction_command.py` | execute compaction | attempt outcome, capacity/usage, command/outbox | completed/retryable/terminal, capacity observed | outcome | attempt/work counters | apply/reconcile + capacity wakeup | Не emitит attempt started. |
| `handle_apply_draft_claim_compaction_result_command.py` | apply compaction | nodes/comparisons/reduction state/work scheduling, command/outbox | result applied; conditional next/waiting/done | result/continuation | cluster counters | continuation prepare/reconcile | — |
| `handle_reconcile_draft_claim_compaction_progress_command.py` | reconcile compaction | command/outbox | progress; conditional all compacted/waiting | reconciliation | aggregate cluster counters | open curation or delayed reconcile | — |
| `handle_open_draft_claim_curation_workspace_command.py` | open curation | workspace/items, workflow state, command/outbox | workspace opened, review required | review required | waiting-review state | — | — |
| `handle_publish_draft_claim_curation_workspace_command.py` | publish | publication, fact registry/facts/triples, runtime retrieval entries/embeddings, workspace/workflow state, command/outbox | workspace published | publication completed | terminal completed snapshot | — | Event payload должен нести publication/workspace/result counts для projection без refetch. |

Pause/resume control handlers отдельно пишут outbox и timeline; resume не создаёт
progress snapshot самостоятельно. Degraded fallback confirmation emitит
`DraftClaimCompactionUserModelChoiceResolved` и append’ит prepare command.

## 8. Frontend projection event catalog

Рекомендуемый общий envelope:

```json
{
  "projection_version": 1,
  "sequence_number": 123,
  "event_id": "workflow-event:...",
  "event_type": "SourceUnitsCreated",
  "workflow_run_id": "...",
  "document_id": "...",
  "occurred_at": "...",
  "idempotency_key": "event_id",
  "patch": {}
}
```

`sequence_number` обязателен для ordering/resume; `event_id` — для dedupe.

| frontend event | source canonical event | payload fields | UI target | idempotency key | missing data |
|---|---|---|---|---|---|
| workflow started | `KnowledgeExtractionWorkflowStarted` | document, workflow, status, phase, started_at | card header/timer/stages | event id | Подтвердить document id и started_at в actual payload. |
| source document ready | `SourceDocumentPersisted` | source_document_ref, project_id, format | document status/timeline | event id | file name/status могут требовать bootstrap model. |
| source units created | `SourceUnitsCreated` | source_document_ref, source_unit_count | source stage/progress | event id | Достаточно. |
| work scheduled | `ClaimBuilderSectionWorkScheduled` | scheduled_count, work_kind, source refs | lane counts/progress | event id | Нужны item summaries/ids для per-row patch, если event несёт только count. |
| dispatch prepared | `ClaimBuilderDispatchBatchPrepared` | work item id, attempt id, source unit, lease, model/account | lane rows/active attempts | event id | Проверить полный список attempts; started timestamp обязателен. |
| attempt started | `ClaimBuilderSectionExtractionStarted` | work/attempt/source/model/account/started_at | LLM attempts, lane row | event id | Event отсутствует. |
| section extracted | `ClaimBuilderSectionExtracted` | work/attempt/source, claims added, usage, completed_at | lane, claims, usage | event id | Нужны claim summaries либо отдельные `claims_created` refs. |
| section deferred | `ClaimBuilderSectionExtractionDeferred` | work/attempt, reason, retry ownership/window ref | lane warning | event id | Event отсутствует; не переносить capacity reset в item patch. |
| section retryable | `ClaimBuilderSectionExtractionRetryableFailed` | work/attempt, error kind, retry plan | lane/attempt warning | event id | `next_attempt_at` должен остаться только для item-owned backoff. |
| section terminal failed | `ClaimBuilderSectionExtractionTerminalFailed` | work/attempt, error kind/user message | lane/error | event id | Достаточно при наличии user-safe message. |
| section split required | `ClaimBuilderSectionSplitRequired` | source unit/work id, token estimate, model limit | source/lane warning | event id | Event отсутствует. |
| source split required | `ClaimBuilderSourceUnitSplitRequired` | source unit refs, affected items, token estimate/reason | source/lane warning | event id | Достаточно. |
| source split completed | `ClaimBuilderSourceUnitSplitCompleted` | old unit, new unit refs/count, superseded/rescheduled ids | source units/lanes | event id | Нужны new unit summaries для patch без source-units refetch. |
| capacity observed | `LlmProviderCapacityObserved` | provider/account/model, remaining request/token budgets, reset_at, observed_at | capacity/attempt | event id | Payload существует; нужен stable `window_id` и admission state. |
| claim progress | `ClaimBuilderProgressReconciled` | all work counters, phase status | progress/stage | event id | Достаточно, если все counters включены. |
| all sections extracted | `ClaimBuilderAllSectionsExtracted` | completed/total, phase transition | stage/header | event id | Event отсутствует. |
| embedding batch completed | `DraftClaimEmbeddingBatchCompleted` | batch ref, completed/failed/total, model/dimensions | embedding stage | event id | Нужен batch ref и cumulative totals. |
| embeddings generated | `DraftClaimEmbeddingsGenerated` | generated/total/model/dimensions | stage/result | event id | Достаточно при cumulative totals. |
| clusters built | `DraftClaimClustersBuilt` | group refs/count/member counts | cluster panel/stage | event id | Для полного cluster UI нужны cluster summaries, не только count. |
| compaction dispatch prepared | `DraftClaimCompactionDispatchBatchPrepared` | cluster/work/attempt/model/account | cluster counters/attempts | event id | Нужны per-attempt refs. |
| compaction attempt started | `DraftClaimCompactionAttemptStarted` | cluster/work/attempt/model/account/started_at | attempts/cluster row | event id | Event отсутствует. |
| compaction attempt completed | `DraftClaimCompactionAttemptCompleted` | cluster/work/attempt, usage, completed_at | attempts/cluster/usage | event id | Достаточно при cluster ref. |
| compaction retryable | `DraftClaimCompactionAttemptRetryableFailed` | cluster/work/attempt/error/retry plan | cluster attention | event id | Разделить item retry и capacity wait. |
| compaction terminal | `DraftClaimCompactionAttemptTerminalFailed` | cluster/work/attempt/error | cluster error | event id | Нужен user-safe message. |
| result applied | `DraftClaimCompactionResultApplied` | comparison/result node, source refs, status | comparisons/facts | event id | Нужен compacted claim summary; refs одни потребуют refetch. |
| next compaction work | `DraftClaimCompactionNextWorkScheduled` | cluster/work type/new work ids/count | cluster queue counts | event id | Нужны ids/status/estimated tokens. |
| waiting model choice | `DraftClaimCompactionWaitingUserModelChoice` | cluster/work, reason, candidate model(s) | action/banner | event id | Достаточно при reason/candidate model. |
| model choice resolved | `DraftClaimCompactionUserModelChoiceResolved` | selected model, actor/decision ref | action removal/timeline | event id | Нужен stable decision ref. |
| cluster done | `DraftClaimCompactionClusterDone` | cluster ref/status/result count | cluster panel | event id | Нужны final compacted claim summaries или subsequent patch events. |
| compaction progress | `DraftClaimCompactionProgressReconciled` | ready/leased/completed/retryable/terminal/user-action totals | progress/cluster panel | event id | Достаточно. |
| all groups compacted | `DraftClaimCompactionAllGroupsCompacted` | completed/total, phase transition | stage/header | event id | Достаточно. |
| curation opened | `DraftClaimCurationWorkspaceOpened` | workspace ref/status/item counts | curation button/modal availability | event id | Нужны excluded count и version/revision. |
| curation review required | `DraftClaimCurationReviewRequired` | workspace ref, item counts | header/action/banner | event id | Достаточно. |
| publication completed | `DraftClaimCurationWorkspacePublished` | publication ref, published fact/entry/embedding counts, completed_at | document status/result/actions | event id | Проверить actual payload; likely не хватает всех result counts. |
| workflow paused | `WorkflowManuallyPaused` | phase, paused_at, reason | header/timer/actions | event id | Достаточно при reason. |
| workflow resumed | `WorkflowManuallyResumed` | phase, resumed_at | header/timer/actions | event id | Достаточно. |

UI projection reducers должны обновлять по stable keys:

- document/workflow: `workflow_run_id`;
- source unit/work item/attempt: соответствующий ref/id;
- cluster/comparison/node/workspace/publication: domain ref;
- timeline: `event_id` или отдельный `timeline_entry_id`;
- capacity window: `provider + account_ref + model_ref + window_kind + reset_at`.

## 9. Capacity window event catalog

Запрошенные target events не представлены отдельным canonical vocabulary. Сейчас
часть сигналов существует как `LlmProviderCapacityObserved`, `capacity_retry_at`,
timeline-only записи, logs и capacity wakeup command.

| target capacity event | Current evidence | Minimal payload | Frontend target | Gap |
|---|---|---|---|---|
| `CapacityWindowObserved` | `LlmProviderCapacityObserved`, observation repository | window id, provider/account/model, remaining requests/tokens, reset_at, observed_at | capacity badge/attempt details | Нужен отдельный typed projection name/window id. |
| `CapacityWindowExhausted` | `_minute_window_exhausted`, zero dispatch, capacity-throttled timeline | window id, exhausted dimensions, reset_at | waiting banner/countdown | Нет canonical event. |
| `CapacityWindowHasRemainingCapacity` | admission calculation в `prepare_llm_dispatch_batch.py` | window id, admissible item/token count | optional diagnostics | Нет event; может быть backend-only, если UI не показывает capacity. |
| `CapacityWindowLeasedWorkItem` | prepare result `started_attempts` | window id, work/attempt id, reserved tokens | lane/attempt | Сейчас растворено в dispatch-prepared. |
| `CapacityWindowSkippedItemByTokenEstimate` | input-size preflight metadata/source split path | window id, work/source ref, estimated tokens, remaining tokens/model limit | source/lane warning | Нет отдельного event; split event покрывает только часть случаев. |
| `CapacityWindowScheduledWakeup` | `append_capacity_window_prepare_wakeup.py` создаёт command `run_after` | window id, wakeup id, reset_at/run_after, command type | waiting countdown | Нет outbox event; только command/log. |
| `CapacityWindowBecameAvailable` | due command execution после reset | window id, available_at, budgets | убрать waiting banner | Нет event. |
| `CapacityWindowPickedRetryableItem` | lease query ordering/status | window id, work id, attempt count | diagnostics/lane | Нет event и explicit selection reason. |
| `CapacityWindowPickedFreshItem` | lease query ordering/status | window id, work id | diagnostics/lane | Нет event и explicit selection reason. |

Рекомендация: selection events можно сохранять как low-volume projection events
только для реально leased item, а не для каждого просмотренного кандидата. Skipped
by token estimate нужен, когда он меняет visible state или требует split/action.

## 10. Snapshot dependency audit

### HTTP endpoint

`GET /api/projects/{project_id}/knowledge/{document_id}/workflow-live-state`
в `src/interfaces/http/knowledge.py`.

- возвращает полный `WorkbenchDocumentWorkflowLiveState`;
- перед чтением добавляет `_drain_workflow_from_live_state_poll` в
  `BackgroundTasks`;
- background task вызывает resume runner с `max_drain_commands=25`;
- это unsafe dependency: read traffic влияет на workflow liveness.

### SSE endpoint

`GET .../workflow-live-state/events`.

- отправляет initial full snapshot;
- подписывается на PostgreSQL `workflow_live_state_changed`;
- после каждого notification снова строит full snapshot;
- queue maxsize 100, overflow silently dropped;
- окно race между initial snapshot и `add_listener`;
- нет cursor, `Last-Event-ID`, reconnect/backoff или replay;
- отдельный LISTEN connection на документ.

### Frontend query/hook

`KnowledgePage.tsx`:

- initial `Promise.all` HTTP snapshots;
- только `documents.slice(0, 6)`;
- отдельный stream per document;
- stream заменяет весь cached payload;
- одновременно патчит document list status/run id;
- нет `onError`, reconnect или fallback polling.

`knowledge.ts` вручную объявляет крупный snapshot type и fetch-stream parser.

### UI dependency

`KnowledgeDocumentCard.tsx` напрямую вычисляет из snapshot:

- headline/status/phase/timer;
- token/call usage;
- stage rows;
- section lane/item/attempt rows;
- retry timers;
- cluster/compaction counters, facts и comparisons;
- curation/actions/timeline.

### Background drain side effects

Независимый lifespan runtime уже существует и reclaim’ит leases/finds due
workflows/drains commands. Поэтому HTTP-triggered drain является compatibility
side effect, а не единственным liveness mechanism. Удалять его следует только
после runtime observability/health evidence, но realtime projection migration не
должна сохранять зависимость от GET.

### Additional contract risks

- backend action `pause_processing` frontend обрабатывает тем же cancel path;
- generated OpenAPI не описывает SSE route;
- snapshot response типизирован вручную;
- migration 090 и текущие Python phase keys потенциально несовместимы;
- ADR 0001 остаётся `Proposed`, `docs/adr/README.md` отсутствует.

## 11. Migration order

1. **Зафиксировать projection envelope.** Version, sequence, event id, workflow id,
   document id, occurred_at, patch. Добавить replay/cursor semantics.
2. **Выровнять durable/canonical phase vocabulary.** Подтвердить runtime schema,
   добавить forward migration/contract tests при необходимости; frontend получает
   только canonical phase.
3. **Закрыть canonical emission gaps.** Started events, all-sections-extracted,
   distinct deferred semantics либо удалить их из contract осознанным ADR.
4. **Добавить capacity window vocabulary.** Не копировать provider reset time в
   item retry projection; emit observed/exhausted/wakeup/available/admitted.
5. **Обогатить payloads.** Stable refs и cumulative counters для reducers; user-safe
   errors; publication/result counts.
6. **Ввести backend projection mapper.** Allowlist canonical events → versioned
   frontend events. Unknown events не должны silently превращаться в full refetch.
7. **Добавить multiplexed SSE stream.** Project/user scoped stream либо один stream
   на страницу; replay after sequence; keepalive; auth и bounded backpressure.
8. **Добавить frontend normalized store/reducer рядом со snapshot.** Snapshot
   bootstrap → event patches; при cursor gap выполнить один recovery snapshot.
9. **Shadow compare.** Одновременно строить old snapshot и reducer state в тестах/
   telemetry, сравнивать header, stages, counters, attempts, clusters и actions.
10. **Перевести widgets по частям.** Header/timer → progress/lanes → attempts/usage →
   capacity → clusters/compaction → curation/publication.
11. **Отвязать GET от drain.** Только после подтверждения lifespan runtime; оставить
    explicit resume/admin endpoints.
12. **Убрать full snapshot из realtime SSE.** Snapshot endpoint оставить для
    bootstrap/recovery/debug до отдельного решения.
13. **После стабилизации пересмотреть snapshot scope.** Не удалять live-state в
    рамках первой миграции.

Первые три безопасных patch-а:

1. typed envelope/cursor и read-only event stream рядом с существующим SSE;
2. emission/payload gap closure плюс contract tests;
3. frontend reducer в shadow mode с automatic recovery snapshot.

## 12. Open questions / unsafe assumptions

1. Должен ли projection stream быть project-level multiplexed или workflow-level?
2. Каков retention/replay SLA для outbox events и можно ли outbox использовать как
   replay log без отдельной projection stream table?
3. Нужна ли frontend полная timeline, или только bounded recent activity?
4. Требуются ли claim texts/cluster members в realtime events, либо эти тяжёлые
   данные останутся lazy read models?
5. Как versioning payload согласуется с generated OpenAPI и TypeScript types?
6. Какие errors безопасно показывать пользователю без provider/internal leakage?
7. Нужны ли `CapacityWindowPickedFreshItem/RetryableItem` пользователю или только
   diagnostic UI?
8. `frontend_visibility=True` сейчас выставлено всем operations. Это означает
   visible business change или лишь необходимость refresh существующего read model?
9. Contract и tests расходятся с реализацией по all-sections-extracted/started/
   deferred events. Следует исправить emitters или изменить contract через ADR?
10. Snapshot query связывает attempt с nearest capacity observation по времени.
    Для event projection нужен явный observation/window ref, иначе correlation
    остаётся эвристической.
11. Проверка выполнена статически. Не проверялись реальные PostgreSQL notifications,
    proxy buffering, connection-pool pressure и browser reconnect.

### Gap report

| category | Finding |
|---|---|
| existing canonical event | 44 enum events; большинство outcome/progress/publication events имеют emit path. |
| actual emitted event | Handlers emit 26 canonical event types; source/start/control/confirmation добавляют ещё несколько. |
| missing actual event | extraction started/deferred/split-required, all-sections-extracted, compaction attempt started. |
| missing frontend projection | Все события: formal typed projection catalog отсутствует; capacity selection/wakeup events отсутствуют даже канонически. |
| unsafe snapshot dependency | SSE full refetch, GET-triggered drain, six-document limit, no replay/reconnect, manual TS/OpenAPI drift. |
| recommended migration order | envelope/cursor → phase vocabulary alignment → emission gaps → capacity ownership → payloads → mapper/stream → shadow reducer → widgets → detach drain → retire realtime snapshot. |

### Validation

Аудит использовал read-only `rg`, focused file reads и независимые read-only
planner/architect/backend/frontend mapper passes. Backend/frontend tests не
запускались: обязательный `bash dev_scripts/ensure_test_env.sh` может создать
`.env.test`, что нарушило бы строгий read-only режим задачи.
