# Workflow Frontend Event Projection Map

## 1. Executive summary

Текущий realtime-контур не передаёт frontend канонические workflow events. Любой
`WorkflowEvent`, записанный в `workflow_runtime_outbox_events`, вызывает
`pg_notify('workflow_live_state_changed', ...)`; SSE endpoint получает уведомление,
заново выполняет тяжёлый multi-query live-state и отправляет клиенту полный snapshot.

Целевой контракт должен оставить backend workflow source of truth, но заменить
повторную передачу snapshot на упорядоченные typed event projections:

```text
canonical workflow/capacity/attempt event
→ frontend projection envelope
→ reducer/idempotent patch
→ concrete artifact surface or live overlay
```

Новая UI-модель разделяет artifact surfaces и live overlays:

```text
artifact appeared → frontend renders artifact surface once
workflow/capacity/attempt event → frontend updates live overlay on that surface
targeted read → allowed for artifact content/bootstrap/recovery, not every-second polling
```

Ключевые выводы аудита:

* canonical contract содержит 9 phases, 15 commands, 15 operations и 44 events;
* durable phase vocabulary требует отдельной сверки: migration 090 содержит
  `PROMPT_A_*` constraints, тогда как текущий Python пишет `CLAIM_BUILDER_*`;
* 13 commands зарегистрированы в generic handler map;
* start и source ingestion выполняются специальным upload/ingestion path;
* после `DraftClaimClustersBuilt` workflow продолжается в draft-claim compaction без
  отдельной preview/review pause phase;
* ряд contract events не emitится: started/deferred/all-sections-extracted являются
  наиболее заметными gaps;
* все operations имеют `frontend_visibility=True`, но связь event → projection →
  UI нигде не проверяется;
* SSE несёт полный snapshot, теряет `sequence_number` из notification и не имеет
  reconnect/cursor protocol;
* HTTP GET live-state имеет side effect: запускает background workflow drain;
* frontend подписывает только первые шесть документов;
* миграция должна сначала стабилизировать event envelope/cursor, затем явно
  разделить artifact surfaces, live overlays, attempt outcome visibility и capacity
  windows; только после этого reducer можно сверять со snapshot и убирать snapshot
  из realtime transport. Сам snapshot read model пока нужен для bootstrap/recovery.

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

* snapshot endpoint остаётся bootstrap/recovery read model;
* realtime endpoint передаёт typed projection events с cursor;
* reducer обновляет только затронутые artifact surfaces / live overlays;
* live overlay event payload обязан содержать stable keys and state transition data;
* artifact surface event payload обязан сигналить появление surface и давать stable
  scope for targeted read;
* event payload не обязан тащить тяжёлые artifact bodies, но не должен требовать
  немедленный full workflow-live-state refetch;
* background drain не должен зависеть от frontend read.

## 2.1 Artifact Surface + Live Overlay model

Frontend pipeline UI строится из двух разных слоёв.

### Artifact surfaces

Artifact surface — результат обработки, который появляется один раз и затем
становится якорем UI:

| surface                                | typical key                      | examples of first render data                                |
| -------------------------------------- | -------------------------------- | ------------------------------------------------------------ |
| SourceDocument                         | `source_document_ref`            | filename/format/status via bootstrap/read model              |
| SourceUnit                             | `source_unit_ref`                | ordinal, heading/title, content hash, text via targeted read |
| ClaimBuilderWorkItem                   | `work_item_id`                   | work kind, source_unit_ref, initial state                    |
| DispatchAttempt                        | `dispatch_attempt_id`            | work_item_id, provider/account/model, attempt state          |
| DraftClaimObservation                  | observation ref                  | claim/evidence via targeted read                             |
| DraftClaimEmbeddingStatus              | observation ref + model          | embedding status/dimensions                                  |
| DraftClaimClusterGroup                 | `group_ref`                      | member count, status                                         |
| DraftClaimClusterBatch                 | `batch_ref`                      | group_ref, work_item_id, member count                        |
| CompactedClaim / reduction node        | node/ref                         | compacted text via targeted read                             |
| CurationWorkspace                      | `workspace_ref`                  | item count/status                                            |
| PublishedKnowledgeEntry / RuntimeEntry | publication/runtime ref          | publication counts/status                                    |
| CapacityWindow                         | `window_id` or stable window key | provider/account/model, budgets, reset_at                    |

Artifact surfaces are normally immutable or append-only. Their content may be loaded
through focused endpoints. This is allowed only as event-triggered/bootstrap/recovery
read, not as per-second polling.

### Live overlays

Live overlay is mutable state attached to a surface:

* `source_unit.claim_builder_status`;
* `source_unit.active_work_item`;
* `source_unit.active_attempt`;
* `source_unit.active_capacity_window`;
* `source_unit.split_status`;
* `work_item.state`;
* `work_item.failure_reason`;
* `work_item.retry_eligibility`;
* `dispatch_attempt.provider_status`;
* `dispatch_attempt.validation_status`;
* `dispatch_attempt.persistence_status`;
* `draft_claim.embedding_status`;
* `draft_claim.cluster_membership_status`;
* `cluster_group.compaction_status`;
* `cluster_batch.compaction_status`;
* `capacity_window.remaining_limits`;
* `capacity_window.reset_countdown`;
* `capacity_window.sleeping/waking`;
* `curation_workspace.status`;
* `publication.status`.

Live overlays must be updated by projection events, not by full snapshot refresh.

### Attempt outcome visibility

Attempt rows must show why a work item completed, became retryable/eligible, or
failed:

| layer              | examples                                                                                   |
| ------------------ | ------------------------------------------------------------------------------------------ |
| capacity/admission | admitted, skipped by token estimate, exhausted, wakeup scheduled                           |
| provider execution | request started, success, rate limited, network error, timeout, 5xx                        |
| output validation  | invalid JSON, schema invalid, truncated output, empty claims, validation passed            |
| persistence/domain | draft claims persisted, persistence failed, completed, retryable eligible, terminal failed |

`RETRYABLE` is passive eligibility for future admission. It must not imply that the
work item retries or wakes itself.

### Capacity window rule

CapacityWindow owns provider/account/model reset, wakeup and admission. WorkItem
does not own provider reset and must not expose provider/account/model reset as item
retry countdown.


## 2.2 Patch 17E Claim-builder attempt outcome visibility

Patch 17E prepares the claim-builder attempt outcome visibility contract for this
frontend shape:

```text
SourceUnit surface
└── WorkItem overlay
    └── Attempts list
```

Existing section outcome projections remain the primary owners of the
SourceUnit/WorkItem overlay transition:

| projection | Overlay meaning |
| --- | --- |
| `workflow_claim_builder_section_extracted` | SourceUnit/WorkItem completed. |
| `workflow_claim_builder_section_retryable_failed` | WorkItem became passive retryable eligibility. |
| `workflow_claim_builder_section_terminal_failed` | WorkItem reached terminal failed state. |

Patch 17E does not add new provider/validation/persistence canonical events and
does not add `ProviderRequestStarted`, `ProviderExecutionCompleted`,
`OutputValidationCompleted`, `DraftClaimsPersisted` or
`DraftClaimsPersistenceFailed`. The current durable boundary already emits final
claim-builder outcome events after provider execution, output validation,
persistence decision and WorkItem lifecycle classification are known.

The desired future fanout projection type is:

```text
workflow_claim_builder_attempt_outcome_classified
```

However, the current projection writer persists one `FrontendWorkflowEvent | None`
per canonical `WorkflowEvent`; fanout is not changed in Patch 17E. Therefore 17E
uses projection-only enrichment of the existing section outcome projections with
an `attempt_outcome` block. A later projection fanout migration can split that
same block into `workflow_claim_builder_attempt_outcome_classified` without moving
SourceUnit/WorkItem overlay ownership.

The `attempt_outcome` block is an append/update payload for a DispatchAttempt
history row. It contains:

| block | Meaning |
| --- | --- |
| `attempt_scope` | `workflow_run_id`, `source_document_ref`, `source_unit_ref`, `work_item_id`, `dispatch_attempt_id` and available operation/phase fields. |
| `provider_outcome` | Provider status, provider/account/model, token usage and provider error kind when available. Provider success does not imply task success. |
| `validation_outcome` | Validation status, decision, failure reason, next action, claim count, truncated-output marker and valid-empty acceptance. |
| `persistence_outcome` | Persisted/skipped/not-applicable status, persisted draft claim count, draft-claims availability and targeted read scope when available. |
| `work_item_outcome` | Attempt-row annotation of completed/retryable/terminal WorkItem result. Existing section projections still own the overlay transition. |
| `capacity_annotation` | Non-timer capacity correlation such as provider/account/model window key when available. |
| `targeted_read_hint` | Patch 17B workflow-scoped draft-claims targeted read parameters for successful persisted claims. |

Attempt outcome visibility keeps Patch 17C ownership rules: provider/account/model
reset remains CapacityWindow-owned, `RETRYABLE` means
`eligible_for_future_admission`, and the attempt history payload must not expose
`retry_owner`, `work_item_retry_timer`, provider reset as item retry, or
`_validated_claims`.

## 2.3 Patch 18A DraftClaimObservation document-card rows

Patch 18A makes `DraftClaimObservation` an explicit document-card artifact
surface after successful claim-builder extraction.

The corrected document-card chain is:

```text
Document card
├── SourceUnit rows
│   └── WorkItem overlay / claim-builder attempts
└── DraftClaimObservation rows
```

`DraftClaimObservation` rows are not nested SourceUnit details. They are
separate document-card rows that reference `source_unit_ref`, `work_item_id`
and `dispatch_attempt_id` for provenance and correlation.

Patch 18A keeps `ClaimBuilderSectionExtracted` as the canonical source event.
No `DraftClaimObservationPersisted`, `DraftClaimObservationsPersisted` or
per-claim canonical event is added. The final claim-builder extracted event
already proves that draft claim persistence completed and carries
`persisted_draft_claim_count`.

The `workflow_claim_builder_section_extracted` projection now carries an
explicit row availability block:

| field | Meaning |
| --- | --- |
| `draft_claim_observation_rows.surface_kind` | Always `draft_claim_observation`. |
| `draft_claim_observation_rows.availability` | `available` only when persisted rows exist. |
| `draft_claim_observation_rows.row_count` | Number of newly available draft claim rows for the extracted attempt. |
| `draft_claim_observation_rows.parent_scope` | `workflow_run_id`, `source_document_ref`, `source_unit_ref`, `work_item_id`, `dispatch_attempt_id`. |
| `draft_claim_observation_rows.targeted_read` | Event-triggered targeted read contract for loading row bodies. |

Claim bodies stay out of the projection payload. The projection must not carry
`claim`, `possible_questions`, `exclusion_scope` or `evidence_block`; those are
loaded through Patch 17B targeted read:

```text
GET /api/projects/{project_id}/knowledge/workflows/{workflow_run_id}/draft-claims
  ?source_unit_ref=...
  &work_item_id=...
  &dispatch_attempt_id=...
```

Valid-empty extraction does not expose available DraftClaimObservation rows.
Retryable and terminal claim-builder outcomes also do not expose row
availability.

Embedding status overlay remains later. Current draft-claim embedding events are
aggregate-level and do not prove per-observation embedding status. Cluster rows
also remain later and should attach to DraftClaimObservation rows by
`observation_ref` after targeted read has loaded those rows.

Reducer work remains later; Patch 18A only prepares the backend/frontend
projection contract for document-card DraftClaimObservation rows.


## 3. Canonical workflow phases

Источник:
`src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_workflow_definition.py`.

| phase                              | Meaning / current operations                                                       |
| ---------------------------------- | ---------------------------------------------------------------------------------- |
| `WORKFLOW_STARTED`                 | Создание workflow run; special entry path.                                         |
| `SOURCE_INGESTION`                 | Persist source document и create source units.                                     |
| `CLAIM_BUILDER_WORK_SCHEDULING`    | Создание execution work items для source units.                                    |
| `CLAIM_BUILDER_SECTION_EXTRACTION` | Capacity admission, lease, LLM attempt, claim persistence, split и reconciliation. |
| `DRAFT_CLAIM_EMBEDDING`            | Batch embedding draft claims.                                                      |
| `DRAFT_CLAIM_CLUSTERING`           | Cluster plan, compaction dispatch/execution/application/reconciliation.            |
| `DRAFT_CLAIM_CURATION`             | Открытие manual curation workspace.                                                |
| `PUBLICATION`                      | Atomic publication canonical facts, retrieval entries и embeddings.                |
| `COMPLETED`                        | Terminal phase; отдельной operation нет, состояние выставляет publication handler. |

Legacy phase vocabulary всё ещё присутствует в saga state и migration map. Для
frontend projection protocol следует передавать canonical phase и не заставлять
frontend повторять `LEGACY_PHASE_MIGRATION_MAP`.

## 4. Canonical commands

| command                                    | Execution path                                                     |
| ------------------------------------------ | ------------------------------------------------------------------ |
| `StartKnowledgeExtractionWorkflow`         | Special after-upload/start path; не зарегистрирован в generic map. |
| `IngestSourceDocument`                     | Special source-ingestion path; не зарегистрирован в generic map.   |
| `ScheduleClaimBuilderSectionWork`          | `HandleScheduleClaimBuilderSectionWorkCommandHandler`.             |
| `PrepareClaimBuilderDispatchBatch`         | `HandlePrepareClaimBuilderDispatchBatchCommandHandler`.            |
| `SplitClaimBuilderSourceUnit`              | `HandleSplitClaimBuilderSourceUnitCommandHandler`.                 |
| `ExecuteClaimBuilderSection`               | `HandleExecuteClaimBuilderSectionCommandHandler`.                  |
| `ReconcileClaimBuilderProgress`            | `HandleReconcileClaimBuilderProgressCommandHandler`.               |
| `GenerateDraftClaimEmbeddings`             | `HandleGenerateDraftClaimEmbeddingsCommandHandler`.                |
| `ClusterDraftClaims`                       | `HandleClusterDraftClaimsCommandHandler`.                          |
| `PrepareDraftClaimCompactionDispatchBatch` | `HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler`.    |
| `ExecuteDraftClaimCompaction`              | `HandleExecuteDraftClaimCompactionCommandHandler`.                 |
| `ApplyDraftClaimCompactionResult`          | `HandleApplyDraftClaimCompactionResultCommandHandler`.             |
| `ReconcileDraftClaimCompactionProgress`    | `HandleReconcileDraftClaimCompactionProgressCommandHandler`.       |
| `OpenDraftClaimCurationWorkspace`          | `HandleOpenDraftClaimCurationWorkspaceCommandHandler`.             |
| `PublishDraftClaimCurationWorkspace`       | `HandlePublishDraftClaimCurationWorkspaceCommandHandler`.          |

Текущий workflow не содержит отдельной cluster preview / cluster contract review
phase. После `DraftClaimClustersBuilt` workflow продолжается в draft-claim
compaction. Cluster card/detail UI должен строиться из compaction/cluster read
models или explicit cluster projections, а не из удалённых preview/review events.

## 5. Canonical event inventory

`WorkflowManuallyPaused` и `WorkflowManuallyResumed` являются out-of-band control
events. Остальные events связаны с operation contract.

| canonical event                                | Actual emission status                                         | Primary read-model effect                                      |
| ---------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------- |
| `KnowledgeExtractionWorkflowStarted`           | Special start path; не generic handler.                        | header, phase, timer, timeline                                 |
| `SourceDocumentPersisted`                      | Emit в source-ingestion effects.                               | document/header, timeline                                      |
| `SourceUnitsCreated`                           | Emit в source-ingestion effects.                               | source stage/count, timeline, SourceUnit artifact availability |
| `ClaimBuilderSectionWorkScheduled`             | Emit.                                                          | section lanes, progress, WorkItem overlay availability         |
| `ClaimBuilderDispatchBatchPrepared`            | Emit только при `prepared_dispatch_count > 0`.                 | active attempts/lanes                                          |
| `ClaimBuilderSectionExtractionStarted`         | **Не emitится handler’ом.** Lease/attempt rows заменяют event. | active attempts                                                |
| `ClaimBuilderSectionExtracted`                 | Emit.                                                          | lane item, claims, usage, draft claim artifact availability    |
| `ClaimBuilderSectionExtractionDeferred`        | **Не emitится:** deferred маппится в retryable failed event.   | lane item/retry eligibility                                    |
| `ClaimBuilderSectionExtractionRetryableFailed` | Emit для deferred и retryable.                                 | lane item/retry eligibility                                    |
| `ClaimBuilderSectionExtractionTerminalFailed`  | Emit.                                                          | lane item/error                                                |
| `ClaimBuilderSectionSplitRequired`             | **Не emitится execution handler.**                             | lane/source split warning                                      |
| `ClaimBuilderSourceUnitSplitRequired`          | Emit prepare handler.                                          | source split warning                                           |
| `ClaimBuilderSourceUnitSplitCompleted`         | Emit split handler.                                            | source units/lanes                                             |
| `LlmProviderCapacityObserved`                  | Emit execute claim/compaction handlers.                        | capacity/attempt                                               |
| `ClaimBuilderProgressReconciled`               | Emit.                                                          | progress/stage                                                 |
| `ClaimBuilderAllSectionsExtracted`             | **Не emitится reconcile handler.**                             | phase transition                                               |
| `DraftClaimEmbeddingBatchCompleted`            | Emit per batch.                                                | embedding progress                                             |
| `DraftClaimEmbeddingsGenerated`                | Emit terminal embedding result.                                | stage/result                                                   |
| `DraftClaimClustersBuilt`                      | Emit.                                                          | clusters/stage                                                 |
| `DraftClaimCompactionDispatchBatchPrepared`    | Emit при prepared attempts.                                    | cluster work counts                                            |
| `DraftClaimCompactionAttemptStarted`           | **Не emitится handler’ом.**                                    | attempts/cluster work                                          |
| `DraftClaimCompactionAttemptCompleted`         | Emit.                                                          | attempt/cluster work/usage                                     |
| `DraftClaimCompactionAttemptRetryableFailed`   | Emit.                                                          | attempt/retry eligibility                                      |
| `DraftClaimCompactionAttemptTerminalFailed`    | Emit.                                                          | attempt/error                                                  |
| `DraftClaimCompactionResultApplied`            | Emit.                                                          | comparisons/nodes                                              |
| `DraftClaimCompactionNextWorkScheduled`        | Emit conditionally.                                            | cluster work counts                                            |
| `DraftClaimCompactionWaitingUserModelChoice`   | Emit prepare/apply/reconcile paths.                            | action/warning                                                 |
| `DraftClaimCompactionUserModelChoiceResolved`  | Emit confirmation use case, не prepare handler.                | action removal/timeline                                        |
| `DraftClaimCompactionClusterDone`              | Emit conditionally.                                            | cluster status                                                 |
| `DraftClaimCompactionProgressReconciled`       | Emit.                                                          | stage/cluster counters                                         |
| `DraftClaimCompactionAllGroupsCompacted`       | Emit conditionally.                                            | phase transition                                               |
| `DraftClaimCurationWorkspaceOpened`            | Emit.                                                          | curation availability                                          |
| `DraftClaimCurationReviewRequired`             | Emit.                                                          | action/header                                                  |
| `DraftClaimCurationWorkspacePublished`         | Emit.                                                          | publication/completed state                                    |
| `WorkflowManuallyPaused`                       | Emit pause use case.                                           | header/timer/actions                                           |
| `WorkflowManuallyResumed`                      | Emit resume use case.                                          | header/timer/actions                                           |

Также фактически существуют timeline-only pseudo-events, которых нет в canonical
enum, например `ClaimBuilderDispatchBatchPreparedZero` и capacity-throttled
entries. Они не должны становиться неявным frontend event contract.

## 6. Operation contract matrix

| operation                                       | phase                              | command                                    | success event                               | intermediate events                                                   | failure events                                | next commands                                                              | read models                                     | frontend visible |
| ----------------------------------------------- | ---------------------------------- | ------------------------------------------ | ------------------------------------------- | --------------------------------------------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------------- | ---------------- |
| `start_knowledge_extraction_workflow`           | `WORKFLOW_STARTED`                 | `StartKnowledgeExtractionWorkflow`         | `KnowledgeExtractionWorkflowStarted`        | —                                                                     | —                                             | `IngestSourceDocument`                                                     | progress, timeline                              | yes              |
| `ingest_source_document`                        | `SOURCE_INGESTION`                 | `IngestSourceDocument`                     | `SourceUnitsCreated`                        | `SourceDocumentPersisted`                                             | —                                             | `ScheduleClaimBuilderSectionWork`                                          | progress, timeline, source units                | yes              |
| `schedule_claim_builder_section_work`           | `CLAIM_BUILDER_WORK_SCHEDULING`    | `ScheduleClaimBuilderSectionWork`          | `ClaimBuilderSectionWorkScheduled`          | —                                                                     | —                                             | `PrepareClaimBuilderDispatchBatch`                                         | progress, timeline, work items                  | yes              |
| `prepare_claim_builder_dispatch_batch`          | `CLAIM_BUILDER_SECTION_EXTRACTION` | `PrepareClaimBuilderDispatchBatch`         | `ClaimBuilderDispatchBatchPrepared`         | `ClaimBuilderSourceUnitSplitRequired`                                 | —                                             | `ExecuteClaimBuilderSection`, `SplitClaimBuilderSourceUnit`                | attempts, capacity, progress, timeline          | yes              |
| `split_claim_builder_source_unit`               | `CLAIM_BUILDER_SECTION_EXTRACTION` | `SplitClaimBuilderSourceUnit`              | `ClaimBuilderSourceUnitSplitCompleted`      | —                                                                     | —                                             | `ScheduleClaimBuilderSectionWork`                                          | attempts, progress, timeline, source units      | yes              |
| `execute_claim_builder_section`                 | `CLAIM_BUILDER_SECTION_EXTRACTION` | `ExecuteClaimBuilderSection`               | `ClaimBuilderSectionExtracted`              | `ClaimBuilderSectionExtractionStarted`, `LlmProviderCapacityObserved` | deferred, retryable, terminal, split required | `ReconcileClaimBuilderProgress`                                            | progress, attempts, claims, timeline, capacity  | yes              |
| `reconcile_claim_builder_progress`              | `CLAIM_BUILDER_SECTION_EXTRACTION` | `ReconcileClaimBuilderProgress`            | `ClaimBuilderAllSectionsExtracted`          | `ClaimBuilderProgressReconciled`                                      | —                                             | `GenerateDraftClaimEmbeddings`                                             | progress, attempts, timeline                    | yes              |
| `generate_draft_claim_embeddings`               | `DRAFT_CLAIM_EMBEDDING`            | `GenerateDraftClaimEmbeddings`             | `DraftClaimEmbeddingsGenerated`             | `DraftClaimEmbeddingBatchCompleted`                                   | —                                             | `ClusterDraftClaims`                                                       | progress, claims, timeline                      | yes              |
| `cluster_draft_claims`                          | `DRAFT_CLAIM_CLUSTERING`           | `ClusterDraftClaims`                       | `DraftClaimClustersBuilt`                   | —                                                                     | —                                             | `PrepareDraftClaimCompactionDispatchBatch`                                 | progress, timeline, clusters                    | yes              |
| `prepare_draft_claim_compaction_dispatch_batch` | `DRAFT_CLAIM_CLUSTERING`           | `PrepareDraftClaimCompactionDispatchBatch` | `DraftClaimCompactionDispatchBatchPrepared` | `DraftClaimCompactionUserModelChoiceResolved`                         | —                                             | `ExecuteDraftClaimCompaction`                                              | attempts, capacity, progress, timeline          | yes              |
| `execute_draft_claim_compaction`                | `DRAFT_CLAIM_CLUSTERING`           | `ExecuteDraftClaimCompaction`              | `DraftClaimCompactionAttemptCompleted`      | `DraftClaimCompactionAttemptStarted`, `LlmProviderCapacityObserved`   | retryable, terminal                           | `ApplyDraftClaimCompactionResult`, `ReconcileDraftClaimCompactionProgress` | progress, attempts, capacity, timeline          | yes              |
| `apply_draft_claim_compaction_result`           | `DRAFT_CLAIM_CLUSTERING`           | `ApplyDraftClaimCompactionResult`          | `DraftClaimCompactionResultApplied`         | next work, waiting choice, cluster done                               | —                                             | dynamically appended continuation commands                                 | progress, attempts, timeline                    | yes              |
| `reconcile_draft_claim_compaction_progress`     | `DRAFT_CLAIM_CLUSTERING`           | `ReconcileDraftClaimCompactionProgress`    | `DraftClaimCompactionAllGroupsCompacted`    | progress reconciled, waiting choice                                   | —                                             | `OpenDraftClaimCurationWorkspace`                                          | progress, attempts, timeline                    | yes              |
| `open_draft_claim_curation_workspace`           | `DRAFT_CLAIM_CURATION`             | `OpenDraftClaimCurationWorkspace`          | `DraftClaimCurationWorkspaceOpened`         | `DraftClaimCurationReviewRequired`                                    | —                                             | —                                                                          | progress, timeline, curation workspace          | yes              |
| `publish_draft_claim_curation_workspace`        | `PUBLICATION`                      | `PublishDraftClaimCurationWorkspace`       | `DraftClaimCurationWorkspacePublished`      | —                                                                     | —                                             | —                                                                          | progress, timeline, publication/runtime entries | yes              |

Recovery scopes, в порядке contract:

* workflow: start, ingestion, curation, publication;
* phase/source unit: ingestion, scheduling, reconciliation;
* work item attempt/section: prepare/execute/split claim builder;
* embedding batch: embedding;
* cluster build/work item attempt: clustering/compaction;
* curation workspace/publication: terminal manual paths.

## 7. Handler emission matrix

| handler file                                                                        | command                            | DB writes                                                                                                                | actual events emitted                             | timeline writes                                           | progress writes             | next commands                                          | contract gaps                                                                                                                                                                              |
| ----------------------------------------------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------- | --------------------------------------------------------- | --------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| special start path (`start_source_ingestion_workflow.py`, after-upload composition) | `StartKnowledgeExtractionWorkflow` | workflow run/checkpoints/command log                                                                                     | workflow-started path                             | start timeline                                            | initial progress            | ingest                                                 | Не представлен в generic handler map; необходимо окончательно подтвердить единый event payload.                                                                                            |
| `apply_source_ingestion_workflow_effects.py` + source persistence use cases         | `IngestSourceDocument`             | `source_documents`, `knowledge_workbench_documents`, `source_units`, saga state/checkpoints, command/outbox              | `SourceDocumentPersisted`, `SourceUnitsCreated`   | command completed, оба events, next command               | source unit counters        | schedule section work                                  | Нет gap по declared events.                                                                                                                                                                |
| `handle_schedule_claim_builder_section_work_command.py`                             | schedule                           | execution work items/schedules, command/outbox                                                                           | scheduled                                         | scheduled + next command                                  | scheduled totals            | prepare dispatch                                       | Count-only event is not enough for SourceUnit/WorkItem overlay; needs row surface signal.                                                                                                  |
| `handle_prepare_claim_builder_dispatch_batch_command.py`                            | prepare claim dispatch             | lease/attempt/dispatch via composition; command/outbox                                                                   | batch prepared или source split required          | prepared attempts, split, zero-dispatch/capacity throttle | prepared/capacity metadata  | execute items или split; может reschedule same command | Нет typed event для zero dispatch/window exhausted/wakeup; dispatch arrays need attempt row signal.                                                                                        |
| `handle_split_claim_builder_source_unit_command.py`                                 | split                              | source units, superseded/scheduled work, command/outbox                                                                  | split completed                                   | split completed/reschedule                                | source/work counts          | schedule work                                          | Split completed should create SourceUnit/WorkItem surface updates.                                                                                                                         |
| `handle_execute_claim_builder_section_command.py`                                   | execute section                    | attempt outcome, validated claims, usage/capacity observation, command/outbox                                            | extracted, retryable, terminal, capacity observed | outcome                                                   | work/claim/error counters   | reconcile + capacity wakeup                            | Не emitит extraction started, deferred, section split required; deferred collapses into retryable. Attempt outcome visibility lacks provider/validation/persistence sub-stage projections. |
| `handle_reconcile_claim_builder_progress_command.py`                                | reconcile claim                    | command/outbox                                                                                                           | progress reconciled                               | reconciliation                                            | aggregate work counters     | embeddings when complete/eligible                      | Не emitит success `ClaimBuilderAllSectionsExtracted`.                                                                                                                                      |
| `handle_generate_draft_claim_embeddings_command.py`                                 | embeddings                         | `draft_claim_embeddings`, command/outbox                                                                                 | batch completed, embeddings generated             | embedding completion                                      | embedding counters          | cluster                                                | Count fields should distinguish generated/total/failed if frontend displays embedding progress.                                                                                            |
| `handle_cluster_draft_claims_command.py`                                            | cluster                            | compaction groups/edges/members/batches, command/outbox                                                                  | clusters built                                    | cluster/plan built                                        | cluster counters            | prepare compaction                                     | Aggregate event is not enough for cluster artifact surfaces.                                                                                                                               |
| `handle_prepare_draft_claim_compaction_dispatch_batch_command.py`                   | prepare compaction                 | lease/attempt/dispatch, command/outbox                                                                                   | batch prepared, waiting user choice               | prepared/capacity/waiting                                 | cluster work counts         | execute items; may reschedule same command             | Contract declares user-choice-resolved here, but resolution emitится другим use case. Нет window events.                                                                                   |
| `handle_execute_draft_claim_compaction_command.py`                                  | execute compaction                 | attempt outcome, capacity/usage, command/outbox                                                                          | completed/retryable/terminal, capacity observed   | outcome                                                   | attempt/work counters       | apply/reconcile + capacity wakeup                      | Не emitит attempt started.                                                                                                                                                                 |
| `handle_apply_draft_claim_compaction_result_command.py`                             | apply compaction                   | nodes/comparisons/reduction state/work scheduling, command/outbox                                                        | result applied; conditional next/waiting/done     | result/continuation                                       | cluster counters            | continuation prepare/reconcile                         | —                                                                                                                                                                                          |
| `handle_reconcile_draft_claim_compaction_progress_command.py`                       | reconcile compaction               | command/outbox                                                                                                           | progress; conditional all compacted/waiting       | reconciliation                                            | aggregate cluster counters  | open curation or delayed reconcile                     | —                                                                                                                                                                                          |
| `handle_open_draft_claim_curation_workspace_command.py`                             | open curation                      | workspace/items, workflow state, command/outbox                                                                          | workspace opened, review required                 | review required                                           | waiting-review state        | —                                                      | —                                                                                                                                                                                          |
| `handle_publish_draft_claim_curation_workspace_command.py`                          | publish                            | publication, fact registry/facts/triples, runtime retrieval entries/embeddings, workspace/workflow state, command/outbox | workspace published                               | publication completed                                     | terminal completed snapshot | —                                                      | Event payload должен нести publication/workspace/result counts для projection без refetch.                                                                                                 |

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

| frontend event               | source canonical event                         | payload fields                                                                         | UI target                                                | idempotency key | missing data                                                                                                                |
| ---------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------- | --------------- | --------------------------------------------------------------------------------------------------------------------------- |
| workflow started             | `KnowledgeExtractionWorkflowStarted`           | document, workflow, status, phase, started_at                                          | card header/timer/stages                                 | event id        | Подтвердить document id и started_at в actual payload.                                                                      |
| source document ready        | `SourceDocumentPersisted`                      | source_document_ref, project_id, format                                                | document status/timeline                                 | event id        | file name/status могут требовать bootstrap model.                                                                           |
| source units created         | `SourceUnitsCreated`                           | source_document_ref, source_unit_count, surface availability scope                     | source stage/progress + SourceUnit artifact availability | event id        | Count is not enough for SourceUnit rows; use SourceUnit surface signal and/or targeted source-units read.                   |
| work scheduled               | `ClaimBuilderSectionWorkScheduled`             | scheduled_count, work_kind, source refs, work item refs if available                   | lane counts/progress + WorkItem overlay                  | event id        | Нужны item summaries/ids/source_unit_ref для per-row patch, если event несёт только count.                                  |
| dispatch prepared            | `ClaimBuilderDispatchBatchPrepared`            | work item id, attempt id, source unit, lease, model/account                            | lane rows/active attempts                                | event id        | Проверить полный список attempts; attempt row signal обязателен.                                                            |
| attempt started              | `ClaimBuilderSectionExtractionStarted`         | work/attempt/source/model/account/started_at                                           | LLM attempts, lane row                                   | event id        | Event отсутствует; may be replaced by DispatchAttemptPrepared + provider-started event.                                     |
| section extracted            | `ClaimBuilderSectionExtracted`                 | work/attempt/source, claims added, usage, completed_at, draft claim availability scope | lane, claims, usage                                      | event id        | Нужны claim summaries через targeted read or artifact signal; event should not carry heavy claim bodies.                    |
| section deferred             | `ClaimBuilderSectionExtractionDeferred`        | work/attempt, reason, eligibility/window ref                                           | lane warning                                             | event id        | Event отсутствует; не переносить capacity reset в item patch.                                                               |
| section retryable            | `ClaimBuilderSectionExtractionRetryableFailed` | work/attempt, error kind, failure classification, retry eligibility                    | lane/attempt warning                                     | event id        | WorkItem is passive; do not project provider reset or self-retry timer. Future execution is selected by capacity/admission. |
| section terminal failed      | `ClaimBuilderSectionExtractionTerminalFailed`  | work/attempt, error kind/user message                                                  | lane/error                                               | event id        | Достаточно при наличии user-safe message.                                                                                   |
| section split required       | `ClaimBuilderSectionSplitRequired`             | source unit/work id, token estimate, model limit                                       | source/lane warning                                      | event id        | Event отсутствует.                                                                                                          |
| source split required        | `ClaimBuilderSourceUnitSplitRequired`          | source unit refs, affected items, token estimate/reason                                | source/lane warning                                      | event id        | Достаточно.                                                                                                                 |
| source split completed       | `ClaimBuilderSourceUnitSplitCompleted`         | old unit, new unit refs/count, superseded/rescheduled ids                              | source units/lanes                                       | event id        | Нужны new unit summaries/surface signals для patch без source-units refetch.                                                |
| capacity observed            | `LlmProviderCapacityObserved`                  | provider/account/model, remaining request/token budgets, reset_at, observed_at         | CapacityWindow overlay, attempt annotation               | event id        | Payload exists; needs stable window id/key, admission state and must not update WorkItem retry countdown.                   |
| claim progress               | `ClaimBuilderProgressReconciled`               | all work counters, phase status                                                        | progress/stage                                           | event id        | Достаточно, если все counters включены.                                                                                     |
| all sections extracted       | `ClaimBuilderAllSectionsExtracted`             | completed/total, phase transition                                                      | stage/header                                             | event id        | Event отсутствует.                                                                                                          |
| embedding batch completed    | `DraftClaimEmbeddingBatchCompleted`            | batch ref, completed/failed/total, model/dimensions                                    | embedding stage                                          | event id        | Нужен batch ref и cumulative totals.                                                                                        |
| embeddings generated         | `DraftClaimEmbeddingsGenerated`                | generated/total/model/dimensions                                                       | stage/result                                             | event id        | Достаточно при cumulative totals.                                                                                           |
| clusters built               | `DraftClaimClustersBuilt`                      | group refs/count/member counts                                                         | cluster panel/stage                                      | event id        | Для полного cluster UI нужны cluster summaries, не только count.                                                            |
| compaction dispatch prepared | `DraftClaimCompactionDispatchBatchPrepared`    | cluster/work/attempt/model/account                                                     | cluster counters/attempts                                | event id        | Нужны per-attempt refs.                                                                                                     |
| compaction attempt started   | `DraftClaimCompactionAttemptStarted`           | cluster/work/attempt/model/account/started_at                                          | attempts/cluster row                                     | event id        | Event отсутствует.                                                                                                          |
| compaction attempt completed | `DraftClaimCompactionAttemptCompleted`         | cluster/work/attempt, usage, completed_at                                              | attempts/cluster/usage                                   | event id        | Достаточно при cluster ref.                                                                                                 |
| compaction retryable         | `DraftClaimCompactionAttemptRetryableFailed`   | cluster/work/attempt/error/failure classification/retry eligibility                    | cluster attention                                        | event id        | Разделить retry eligibility и capacity wait.                                                                                |
| compaction terminal          | `DraftClaimCompactionAttemptTerminalFailed`    | cluster/work/attempt/error                                                             | cluster error                                            | event id        | Нужен user-safe message.                                                                                                    |
| result applied               | `DraftClaimCompactionResultApplied`            | comparison/result node, source refs, status                                            | comparisons/facts                                        | event id        | Нужен compacted claim summary or artifact availability signal; refs одни потребуют targeted read.                           |
| next compaction work         | `DraftClaimCompactionNextWorkScheduled`        | cluster/work type/new work ids/count                                                   | cluster queue counts                                     | event id        | Нужны ids/status/estimated tokens.                                                                                          |
| waiting model choice         | `DraftClaimCompactionWaitingUserModelChoice`   | cluster/work, reason, candidate model(s)                                               | action/banner                                            | event id        | Достаточно при reason/candidate model.                                                                                      |
| model choice resolved        | `DraftClaimCompactionUserModelChoiceResolved`  | selected model, actor/decision ref                                                     | action removal/timeline                                  | event id        | Нужен stable decision ref.                                                                                                  |
| cluster done                 | `DraftClaimCompactionClusterDone`              | cluster ref/status/result count                                                        | cluster panel                                            | event id        | Нужны final compacted claim summaries или subsequent patch events.                                                          |
| compaction progress          | `DraftClaimCompactionProgressReconciled`       | ready/leased/completed/retryable/terminal/user-action totals                           | progress/cluster panel                                   | event id        | Достаточно.                                                                                                                 |
| all groups compacted         | `DraftClaimCompactionAllGroupsCompacted`       | completed/total, phase transition                                                      | stage/header                                             | event id        | Достаточно.                                                                                                                 |
| curation opened              | `DraftClaimCurationWorkspaceOpened`            | workspace ref/status/item counts                                                       | curation button/modal availability                       | event id        | Нужны excluded count и version/revision.                                                                                    |
| curation review required     | `DraftClaimCurationReviewRequired`             | workspace ref, item counts                                                             | header/action/banner                                     | event id        | Достаточно.                                                                                                                 |
| publication completed        | `DraftClaimCurationWorkspacePublished`         | publication ref, published fact/entry/embedding counts, completed_at                   | document status/result/actions                           | event id        | Проверить actual payload; likely не хватает всех result counts.                                                             |
| workflow paused              | `WorkflowManuallyPaused`                       | phase, paused_at, reason                                                               | header/timer/actions                                     | event id        | Достаточно при reason.                                                                                                      |
| workflow resumed             | `WorkflowManuallyResumed`                      | phase, resumed_at                                                                      | header/timer/actions                                     | event id        | Достаточно.                                                                                                                 |

UI projection reducers должны обновлять по stable keys:

* document/workflow: `workflow_run_id`;
* artifact surfaces: `source_document_ref`, `source_unit_ref`, observation ref,
  `group_ref`, `batch_ref`, node/workspace/publication refs;
* live overlays: `work_item_id`, `dispatch_attempt_id`, artifact ref + overlay kind;
* timeline: `event_id` или отдельный `timeline_entry_id`;
* capacity window: stable `window_id` or provider/account/model/window key.

Full `workflow-live-state` is not a realtime dependency. It may be used only for
bootstrap/recovery/debug/manual refresh.

## 9. Capacity window event catalog

Запрошенные target events не представлены отдельным canonical vocabulary. Сейчас
часть сигналов существует как `LlmProviderCapacityObserved`, `capacity_retry_at`,
timeline-only записи, logs и capacity wakeup command.

| target capacity event                      | Current evidence                                                       | Payload expectation                                                                     | Frontend target                | Gap                                                                 |
| ------------------------------------------ | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------------- |
| `CapacityWindowObserved`                   | `LlmProviderCapacityObserved`, observation repository                  | window id, provider/account/model, remaining requests/tokens, reset_at, observed_at | capacity badge/attempt details | Нужен отдельный typed projection name/window id.                    |
| `CapacityWindowExhausted`                  | `_minute_window_exhausted`, zero dispatch, capacity-throttled timeline | window id, exhausted dimensions, reset_at                                           | waiting banner/countdown       | Нет canonical event.                                                |
| `CapacityWindowHasRemainingCapacity`       | admission calculation в `prepare_llm_dispatch_batch.py`                | window id, admissible item/token count                                              | optional diagnostics           | Нет event; может быть backend-only, если UI не показывает capacity. |
| `CapacityWindowLeasedWorkItem`             | prepare result `started_attempts`                                      | window id, work/attempt id, reserved tokens                                         | lane/attempt                   | Сейчас растворено в dispatch-prepared.                              |
| `CapacityWindowSkippedItemByTokenEstimate` | input-size preflight metadata/source split path                        | window id, work/source ref, estimated tokens, remaining tokens/model limit          | source/lane warning            | Нет отдельного event; split event покрывает только часть случаев.   |
| `CapacityWindowScheduledWakeup`            | `append_capacity_window_prepare_wakeup.py` создаёт command `run_after` | window id, wakeup id, reset_at/run_after, command type                              | waiting countdown              | Нет outbox event; только command/log.                               |
| `CapacityWindowBecameAvailable`            | due command execution после reset                                      | window id, available_at, budgets                                                    | убрать waiting banner          | Нет event.                                                          |
| `CapacityWindowPickedRetryableItem`        | lease query ordering/status                                            | window id, work id, attempt count                                                   | diagnostics/lane               | Нет event и explicit selection reason.                              |
| `CapacityWindowPickedFreshItem`            | lease query ordering/status                                            | window id, work id                                                                  | diagnostics/lane               | Нет event и explicit selection reason.                              |

Рекомендация: selection events можно сохранять как low-volume projection events
только для реально leased item, а не для каждого просмотренного кандидата. Skipped
by token estimate нужен, когда он меняет visible state или требует split/action.

## 9.1 CapacityWindow projection events after Patch 17C

Patch 17C adds a reusable CapacityWindow/admission projection boundary for the
claim-builder path. It should be reused by draft-claim compaction later instead of
creating a second capacity/admission model.

Implemented frontend projection types:

| frontend projection | Source canonical event | Reducer meaning |
| --- | --- | --- |
| `workflow_capacity_window_observed` | `LlmProviderCapacityObserved` | Updates capacity window counters/reset observation and may annotate the dispatch attempt. |
| `workflow_capacity_window_exhausted` | `CapacityWindowExhausted` | Updates CapacityWindow exhausted/sleeping overlay for a concrete provider/account/model window. |
| `workflow_capacity_window_scheduled_wakeup` | `CapacityWindowScheduledWakeup` | Updates CapacityWindow wakeup/delivery overlay. `run_after` is command delivery scheduling, not WorkItem retry. |
| `workflow_capacity_window_leased_work_item` | `CapacityWindowLeasedWorkItem` | Links CapacityWindow/admission selection to the work item and dispatch attempt. |

These events update the CapacityWindow overlay, not a WorkItem retry countdown.
WorkItem retryable overlay remains passive:

```text
retry_eligibility = eligible_for_future_admission
retry_driver = capacity_window_admission
```

`workflow_capacity_window_observed` is projected from the existing
`LlmProviderCapacityObserved` event. The Patch 17C CapacityWindow projector handles
`workflow_capacity_window_exhausted`,
`workflow_capacity_window_scheduled_wakeup`, and
`workflow_capacity_window_leased_work_item`.

### Payload expectations

| projection | Stable key | Scope fields | Capacity fields | Causation fields | Forbidden fields |
| --- | --- | --- | --- | --- | --- |
| `workflow_capacity_window_observed` | `window_key = provider:account_ref:model_ref` plus `dispatch_attempt_id` | `workflow_run_id`, `dispatch_attempt_id`, `work_item_id` | `provider`, `account_ref`, `model_ref`, `outcome_class`, `observed_at`, `remaining_minute_requests`, `remaining_minute_tokens`, `remaining_daily_requests`, `remaining_daily_tokens`, optional `minute_reset_at`, `daily_reset_at`, `actual_prompt_tokens`, `actual_completion_tokens`, `actual_total_tokens` | source event id/sequence, `causation_command_id`, `correlation_id` | Do not project as item retry countdown; do not add `next_attempt_at`, `retry_owner`, `work_item_retry_timer`. |
| `workflow_capacity_window_exhausted` | `window_key = provider:account_ref:model_ref` | `workflow_run_id`, optional `work_item_id`, `dispatch_attempt_id`, `source_unit_ref` | `provider`, `account_ref`, `model_ref`, `exhausted_reason`, `exhausted_dimensions`, `reset_at`, optional `observed_at` | `operation_key`, `canonical_phase`, optional `causation_command_id`, source event id/sequence | `next_attempt_at`, `retry_owner`, `work_item_retry_timer`, provider reset as item retry. |
| `workflow_capacity_window_scheduled_wakeup` | `window_key = provider:account_ref:model_ref`, `wakeup_command_id` | `workflow_run_id` | `provider`, `account_ref`, `model_ref`, `run_after`, `reset_at`, `prepare_command_type`, `wakeup_reason` | `operation_key`, `canonical_phase`, optional `causation_command_id`, source event id/sequence | `next_attempt_at`, `retry_owner`, `work_item_retry_timer`, `lease_expires_at` as retry timer. |
| `workflow_capacity_window_leased_work_item` | `window_key = provider:account_ref:model_ref`, `dispatch_attempt_id` | `workflow_run_id`, `work_item_id`, `dispatch_attempt_id`, optional `source_unit_ref` | `provider`, `account_ref`, `model_ref`, `lease_expires_at`, `selection_kind`, optional `token_estimate`, `reserved_tokens`, projected `admission_driver=capacity_window_admission` | `operation_key`, `canonical_phase`, optional `causation_command_id`, source event id/sequence | `next_attempt_at`, `retry_owner`, `work_item_retry_timer`, provider reset as item retry. |

The CapacityWindow projector builds allowlisted payloads and defensively prevents
`next_attempt_at`, `retry_owner`, and `work_item_retry_timer` from appearing in the
projection payload. If legacy canonical payloads contain those fields, capacity
projection code must strip or reject them before frontend overlay state is updated.

### Claim-builder now, compaction later

Patch 17C wires CapacityWindow events through the claim-builder prepare/execute
path. The event/projector model is intentionally generic enough to be reused by
draft-claim compaction prepare/execute paths. Compaction UI/reducer work was not
implemented in Patch 17C. Compaction projection wiring was intentionally left for a
later patch unless already safe through shared builders.

Do not duplicate a second capacity/admission model for compaction. Compaction
should reuse CapacityWindow observed/exhausted/scheduled-wakeup/leased-work-item
semantics.

### Legacy compatibility impact

Patch 17C does not remove WorkItem `next_attempt_at`, old live-state retry timer,
lease SQL behavior, `capacity_retry_at`, or `LlmDispatchExecutionResult.next_attempt_at`.
These remain compatibility paths until frontend reducer shadow comparison and later
runtime migration. New frontend capacity semantics should prefer CapacityWindow
projection events, while old snapshot/live-state fields remain compatibility data.

## 10. Snapshot dependency audit

### HTTP endpoint

`GET /api/projects/{project_id}/knowledge/{document_id}/workflow-live-state`
в `src/interfaces/http/knowledge.py`.

* возвращает полный `WorkbenchDocumentWorkflowLiveState`;
* перед чтением добавляет `_drain_workflow_from_live_state_poll` в
  `BackgroundTasks`;
* background task вызывает resume runner с `max_drain_commands=25`;
* это unsafe dependency: read traffic влияет на workflow liveness.

### SSE endpoint

`GET .../workflow-live-state/events`.

* отправляет initial full snapshot;
* подписывается на PostgreSQL `workflow_live_state_changed`;
* после каждого notification снова строит full snapshot;
* queue maxsize 100, overflow silently dropped;
* окно race между initial snapshot и `add_listener`;
* нет cursor, `Last-Event-ID`, reconnect/backoff или replay;
* отдельный LISTEN connection на документ.

### Frontend query/hook

`KnowledgePage.tsx`:

* initial `Promise.all` HTTP snapshots;
* только `documents.slice(0, 6)`;
* отдельный stream per document;
* stream заменяет весь cached payload;
* одновременно патчит document list status/run id;
* нет `onError`, reconnect или fallback polling.

`knowledge.ts` вручную объявляет крупный snapshot type и fetch-stream parser.

### UI dependency

`KnowledgeDocumentCard.tsx` напрямую вычисляет из snapshot:

* headline/status/phase/timer;
* token/call usage;
* stage rows;
* section lane/item/attempt rows;
* retry timers;
* cluster/compaction counters, facts и comparisons;
* curation/actions/timeline.

### Background drain side effects

Независимый lifespan runtime уже существует и reclaim’ит leases/finds due
workflows/drains commands. Поэтому HTTP-triggered drain является compatibility
side effect, а не единственным liveness mechanism. Удалять его следует только
после runtime observability/health evidence, но realtime projection migration не
должна сохранять зависимость от GET.

### Additional contract risks

* backend action `pause_processing` frontend обрабатывает тем же cancel path;
* generated OpenAPI не описывает SSE route;
* snapshot response типизирован вручную;
* migration 090 и текущие Python phase keys потенциально несовместимы;
* ADR 0001 остаётся `Proposed`, `docs/adr/README.md` отсутствует.

## 11. Migration order

1. **Зафиксировать projection envelope.** Version, sequence, event id, workflow id,
   document id, occurred_at, patch. Добавить replay/cursor semantics.
2. **Выровнять durable/canonical phase vocabulary.** Подтвердить runtime schema,
   добавить forward migration/contract tests при необходимости; frontend получает
   только canonical phase.
3. **Зафиксировать Artifact Surface + Live Overlay boundary.** SourceUnit,
   DraftClaim, ClusterGroup, CompactedClaim, CurationWorkspace и PublishedEntry
   появляются как surfaces; WorkItem, DispatchAttempt, capacity and attempt
   outcomes обновляют overlays.
4. **Закрыть canonical emission gaps.** Started events, all-sections-extracted,
   distinct deferred semantics либо удалить их из contract осознанным ADR.
5. **Добавить capacity window vocabulary.** Не копировать provider reset time в
   item retry projection; emit observed/exhausted/wakeup/available/admitted.
6. **Обогатить payloads.** Stable refs и cumulative counters для reducers;
   user-safe errors; attempt outcome reasons; artifact availability scopes;
   publication/result counts.
7. **Ввести backend projection mapper.** Allowlist canonical events → versioned
   frontend events. Unknown events не должны silently превращаться в full refetch.
8. **Добавить multiplexed SSE stream.** Project/user scoped stream либо один stream
   на страницу; replay after sequence; keepalive; auth и bounded backpressure.
9. **Добавить frontend normalized store/reducer рядом со snapshot.** Snapshot
   bootstrap → event patches; при cursor gap выполнить один recovery snapshot.
10. **Shadow compare.** Одновременно строить old snapshot и reducer state в тестах/
    telemetry, сравнивать header, stages, counters, attempts, clusters и actions.
11. **Перевести widgets по частям.** Header/timer → progress/lanes → attempts/usage →
    capacity → clusters/compaction → curation/publication.
12. **Отвязать GET от drain.** Только после подтверждения lifespan runtime; оставить
    explicit resume/admin endpoints.
13. **Убрать full snapshot из realtime SSE.** Snapshot endpoint оставить для
    bootstrap/recovery/debug до отдельного решения.
14. **После стабилизации пересмотреть snapshot scope.** Не удалять live-state в
    рамках первой миграции.

Первые три безопасных patch-а:

1. typed envelope/cursor и read-only event stream рядом с существующим SSE;
2. artifact surface + live overlay + attempt outcome gap closure plus contract tests;
3. frontend reducer в shadow mode с automatic recovery snapshot.

## 12. Open questions / unsafe assumptions

1. Должен ли projection stream быть project-level multiplexed или workflow-level?
2. Каков retention/replay SLA для outbox events и можно ли outbox использовать как
   replay log без отдельной projection stream table?
3. Нужна ли frontend полная timeline, или только bounded recent activity?
4. Which artifact bodies are loaded by targeted read after availability event, and
   which light summaries belong in projection payload?
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

| category                    | Finding                                                                                                                                                                                                                     |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| existing canonical event    | 44 enum events; большинство outcome/progress/publication events имеют emit path.                                                                                                                                            |
| actual emitted event        | Handlers emit 26 canonical event types; source/start/control/confirmation добавляют ещё несколько.                                                                                                                          |
| missing actual event        | extraction started/deferred/split-required, all-sections-extracted, compaction attempt started.                                                                                                                             |
| missing frontend projection | Все события: formal typed projection catalog отсутствует; capacity selection/wakeup events отсутствуют даже канонически.                                                                                                    |
| unsafe snapshot dependency  | SSE full refetch, GET-triggered drain, six-document limit, no replay/reconnect, manual TS/OpenAPI drift.                                                                                                                    |
| recommended migration order | envelope/cursor → phase vocabulary alignment → artifact surface/live overlay boundary → emission gaps → capacity ownership → payloads → mapper/stream → shadow reducer → widgets → detach drain → retire realtime snapshot. |

### Validation

Аудит использовал read-only `rg`, focused file reads и независимые read-only
planner/architect/backend/frontend mapper passes. Backend/frontend tests не
запускались: обязательный `bash dev_scripts/ensure_test_env.sh` может создать
`.env.test`, что нарушило бы строгий read-only режим задачи.

## Patch 18B DraftClaimClusterGroup document-card rows

`DraftClaimClustersBuilt` remains the canonical source event for clustering completion. The event is intentionally count-only: it proves that the clustering plan was persisted and reports aggregate counts, but it does not carry `group_ref`, `batch_ref`, member refs, claim text, questions, evidence, or exclusion bodies.

`workflow_draft_claim_clusters_built` is therefore a lightweight document-card availability signal. When `group_count > 0`, it exposes a `draft_claim_cluster_rows` block with `surface_kind=draft_claim_cluster_group`, `availability=available`, `row_count`, `batch_count`, parent workflow scope, and a targeted-read hint with `kind=draft_claim_clusters_by_workflow` and `include_batches=true`.

ClusterGroup rows are document-card artifact surfaces. ClusterBatch rows are child artifact surfaces under ClusterGroup rows. Their refs and row summaries are loaded by targeted read from the workflow-scoped draft-claim cluster endpoints. Cluster members are loaded on ClusterGroup expansion and default to refs (`observation_ref`, `embedding_ref`, `source_unit_ref`, rank/kind), not claim bodies. Claim/evidence/question bodies stay on the DraftClaimObservation targeted-read surface.

Patch 18B does not update every DraftClaimObservation row with live cluster membership. It also does not add per-cluster, per-batch, or per-member canonical events. Compaction attempt visibility remains later and will attach to ClusterBatch rows after the batch parent surfaces are available. Reducer and React rendering remain later.\n\n

## Patch 18C DraftClaimCompaction stage artifact graph

ClusterBatch rows receive compaction processing visibility after Patch 18B. A
compaction attempt is similar to a claim-builder attempt because it has provider,
validation, work-item, and capacity outcomes, but it is not identical: attempt
success means the LLM/validation path completed, while generated durable
compacted/reduction node rows become available only after
`DraftClaimCompactionResultApplied`.

Patch 18C therefore treats `DraftClaimCompactionResultApplied` as the generated
node availability boundary. The projection exposes a lightweight
`generated_compaction_nodes` block with counts/refs when available and a targeted
read hint. Generated compacted/reduction nodes are document-card artifact
surfaces loaded by targeted read from the workflow-scoped compaction node read
endpoint. The projection never forwards compacted claim bodies, reduced rewrite
bodies, raw model output, prompt messages, claim/evidence/question bodies, or
triples from attempt metadata.

Reduced rewrite may require targeted read even when the applied event has no
`created_node_refs`, because the reduction state persists the rewritten compacted
node while the event may only carry parent scope and superseded refs. In that
case the projection must not invent node refs; it points the frontend to
workflow/group targeted read.

`DraftClaimCompactionNextWorkScheduled` is a processing/progress signal only. It
does not invent ClusterBatch rows when the event has no persisted batch refs.
`DraftClaimCompactionClusterDone` is a ClusterGroup-level completion overlay.
`DraftClaimCompactionAllGroupsCompacted` is document-level compaction completion
and curation-readiness, not publication readiness. Curation, publication,
workflow-live-state, reducer, and React rendering remain later.

CapacityWindow ownership remains unchanged: provider/account/model admission and
reset are CapacityWindow-owned. Compaction projections must not expose provider
reset or `next_attempt_at` as a WorkItem-owned retry timer.


## Patch 18D DraftClaimCompaction active frontier correctness

Patch 18D makes compaction correctness a backend invariant before reducer,
curation, or publication work. The compaction stage is modeled as an active
frontier of raw/compacted artifacts, immutable compacted artifacts, origin sets,
and durable origin-level separation edges.

`source_claim_refs` remains the origin_set for raw and compacted nodes. A
successful apply consumes only the input artifacts that participated in the
applied result. Retryable and terminal failures do not consume raw inputs, do not
create compacted artifacts, and do not create separation edges.

Successful non-merge records durable origin-level separation edges between
origins that ended in different output partitions. Successful merge does not
create separation edges inside merged origins. The planner must reject future
candidate comparisons whenever any origin in one active artifact is separated
from any origin in the other active artifact. Eligibility is evaluated before
ordinary token/capacity fit checks.

Compacted artifacts are immutable. If the LLM returns an output partition whose
origin_set maps to an existing compacted node, the stored artifact is preserved;
LLM changes to that existing artifact body are ignored. New compacted artifacts
are created only for genuinely new origin_sets.

Cluster-of-one self-enrichment remains allowed. A singleton token-budget chunk
inside a larger ClusterGroup is not self-enriched as an initial batch; it waits
in the active raw frontier until it can be compared with an eligible active
compacted artifact.

Frontend reducer, React rendering, curation, publication, workflow-live-state,
SSE transport, LLM Runtime, Capacity Runtime ownership, and draft embedding
cleanup remain later.


## Patch 18E — DraftClaimCompaction document-card reduction surface

Patch 18E adds the backend/API read contract for the compaction document-card
artifact surface after Patch 18D correctness invariants. The surface is not a
frontend reducer and does not render React components.

The new reduction frontier read contract exposes active raw waiting rows,
active compacted rows, inactive/superseded counts, group completion summary,
separation summary/debug counts, and pending work counts through targeted read.
Generated compacted node rows remain loaded through the Patch 18C
`draft-claim-compaction-nodes` targeted read; Patch 18E only adds lightweight
row counts such as `source_claim_count` and `supersedes_node_count`.

Origin-level separation edges remain backend correctness state. The default
frontier response returns summary/debug counts and bounded sample pairs; it does
not return the full raw separation edge graph.

`DraftClaimCompactionNextWorkScheduled` remains progress visibility and does not
invent ClusterBatch rows. `DraftClaimCompactionClusterDone` is a ClusterGroup
completion overlay. `DraftClaimCompactionAllGroupsCompacted` is document-level
compaction completion and curation-readiness later. Frontend reducer, React UI,
curation, publication, workflow-live-state, SSE transport, and cross-cluster
triple reconciliation remain later.


## Patch 18F — DraftClaimCompaction CapacityWindow correlation

Patch 18F makes CapacityWindow projections and document-card reads attachable to
DraftClaimCompaction dynamic reduction work. CapacityWindow remains the owner of
admission/reset timing; WorkItem retry overlays do not own provider reset state.

Dynamic compaction work is represented as pending reduction work keyed by
`work_item_id`, not as fake ClusterBatch rows. The pending work rows carry
`group_ref`, `batch_ref`, `input_node_refs`, `input_claim_refs`, status, optional
`dispatch_attempt_id`, and optional capacity window identity derived from the LLM
allocation payload. The frontier read contract exposes these pending rows next to
capacity-aware pending counts.

`DraftClaimCompactionNextWorkScheduled` remains progress visibility. It does not
invent persisted ClusterBatch rows. `run_after` is workflow command delivery for
scheduled wakeups, not WorkItem retry ownership. `lease_expires_at` remains lease
ownership, not a retry timer. Frontend reducer, React UI, curation, publication,
and cross-cluster triple reconciliation remain later.

Patch 19A — DraftClaimCompaction document-card reducer contract

Patch 19A hardens the compaction document-card reducer contract before frontend reducer/UI work.

Contract:

cluster_groups[group_ref]
cluster_batches[batch_ref]                 # initial batch surface only
compaction_frontier_nodes[node_ref]
pending_reduction_work[work_item_id]
compaction_attempts[dispatch_attempt_id]
capacity_windows[window_key]

Rules:

ClusterBatch is an initial batch surface only.
Dynamic reduction work is not a fake ClusterBatch.
Dynamic reduction work row key is work_item_id.
Attempt history key is dispatch_attempt_id.
Attempts append under pending_reduction_work[work_item_id].
ResultApplied is generated-node/frontier availability, not merely attempt success.
NextWorkScheduled triggers pending/frontier targeted read, not fake batch creation.
CapacityWindow events update capacity_windows[window_key] and linked pending work when compaction_context.work_item_id is present.
Heavy generated bodies stay behind targeted reads.
Frontend reducer, React UI, curation and publication remain later.

Patch 19B — Frontend projection-event client and compaction shadow reducer

Patch 19B adds the frontend foundation for consuming projection events without switching the visible UI.

New frontend client contract:

GET frontend-events
SSE frontend-events/stream
FrontendWorkflowEventEnvelope
FrontendWorkflowEventsResponse
FrontendWorkflowEventsQuery

New pure shadow reducer contract:

frontend_workflow_event envelope
→ idempotent event-to-entity patch
→ shadow reducer state
→ targeted read requests / recovery hints

Reducer-owned shadow entities:

cluster_groups[group_ref]
cluster_batches[batch_ref]
compaction_frontier_nodes[node_ref]
pending_reduction_work[work_item_id]
compaction_attempts[dispatch_attempt_id]
capacity_windows[window_key]

Patch 19B keeps the current compatibility path:

workflow-live-state snapshot
streamWorkflowLiveState
KnowledgePage visible behavior
KnowledgeDocumentCard rendering

These remain untouched and are still used for visible UI. The projection stream is not hooked into KnowledgePage in Patch 19B. The shadow reducer is pure TypeScript, has no React imports, no DOM/API calls, and is ready for later stream hookup and snapshot parity/debug comparison.

Patch 19B does not implement:

visible UI replacement
DocumentCard rendering switch
CapacityWindow dashboard UI
curation
publication
cross-cluster triple reconciliation