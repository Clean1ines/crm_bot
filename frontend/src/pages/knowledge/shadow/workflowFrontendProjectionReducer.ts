import type {
  FrontendWorkflowEventEnvelope,
  WorkbenchLlmAttemptLiveState,
  WorkbenchSectionLaneLiveState,
  WorkbenchSectionQueueItemLiveState,
  WorkbenchWorkflowLiveStateResponse,
  WorkbenchWorkflowStageLiveState,
  WorkbenchWorkflowTimelineEntryLiveState,
} from "@shared/api/modules/knowledge";

export type InitialWorkflowProjectionDocument = {
  documentId: string;
  projectId: string;
  fileName: string;
  documentStatus: string;
  workflowRunId: string;
};

const CLAIM_BUILDER_NODE_NAME = "knowledge_workbench.claim_builder";

const nowIso = (): string => new Date().toISOString();

const emptyUsage = () => ({
  total_prompt_tokens: 0,
  total_completion_tokens: 0,
  total_tokens: 0,
  total_llm_calls: 0,
  model_summaries: [],
});

const emptyTimer = (startedAt: string) => ({
  mode: "running",
  active_elapsed_seconds: 0,
  wall_elapsed_seconds: 0,
  current_active_started_at: startedAt,
  started_at: startedAt,
  completed_at: null,
  is_live: true,
});

const stage = (
  id: string,
  label: string,
  status: WorkbenchWorkflowStageLiveState["status"] = "pending",
): WorkbenchWorkflowStageLiveState => ({
  id,
  label,
  status,
  current: 0,
  total: 0,
  message: "",
  started_at: null,
  completed_at: null,
});

const defaultStages = (): WorkbenchWorkflowStageLiveState[] => [
  stage("source_ingestion", "Подготовка документа", "running"),
  stage("prompt_a_claim_extraction", "Извлечение утверждений", "pending"),
  stage("draft_claim_embeddings", "Векторизация утверждений", "pending"),
  stage("draft_claim_clustering", "Группировка похожих утверждений", "pending"),
  stage("draft_claim_compaction", "Объединение знаний", "pending"),
  stage("cluster_preview", "Предпросмотр базы знаний", "pending"),
  stage("curation", "Проверка человеком", "pending"),
  stage("publication", "Публикация", "pending"),
];

export const createInitialWorkflowLiveStateResponse = (
  document: InitialWorkflowProjectionDocument,
): WorkbenchWorkflowLiveStateResponse => {
  const startedAt = nowIso();

  return {
    document_id: document.documentId,
    project_id: document.projectId,
    file_name: document.fileName,
    document_status: document.documentStatus || "processing",
    current_processing_run_id: document.workflowRunId,
    workflow: {
      workflow_run_id: document.workflowRunId,
      source_document_ref: document.documentId,
      workflow_status: "running",
      current_phase: "source_ingestion",
      timer: emptyTimer(startedAt),
      usage: emptyUsage(),
      stages: defaultStages(),
      section_lanes: [
        {
          lane_index: 0,
          lane_id: "claim_builder",
          ready_count: 0,
          leased_count: 0,
          done_count: 0,
          failed_count: 0,
          waiting_count: 0,
          total_attempt_count: 0,
          max_attempt_count: 0,
          items: [],
        },
      ],
      llm_attempts: [],
      timeline: [],
      claim_clusters: [],
      claim_compaction_comparisons: [],
      curation: {
        available: false,
        reason_code: "not_ready",
        workflow_run_id: document.workflowRunId,
        workspace_ref: null,
        workspace_status: null,
        item_count: 0,
        excluded_item_count: 0,
      },
      actions: [
        {
          action_id: "cancel_processing",
          visible: true,
          enabled: true,
          reason_code: null,
        },
      ],
    },
  };
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const text = (payload: Record<string, unknown>, key: string): string | null => {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
};

const intValue = (payload: Record<string, unknown>, key: string): number | null => {
  const value = payload[key];
  return typeof value === "number" && Number.isFinite(value)
    ? Math.floor(value)
    : null;
};

const stringArray = (
  payload: Record<string, unknown>,
  key: string,
): string[] => {
  const value = payload[key];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
};

const normalize = (value: string | null | undefined): string =>
  (value || "").trim().toLowerCase();

const cloneResponse = (
  current: WorkbenchWorkflowLiveStateResponse,
): WorkbenchWorkflowLiveStateResponse => ({
  ...current,
  workflow: {
    ...current.workflow,
    timer: { ...current.workflow.timer },
    usage: {
      ...current.workflow.usage,
      model_summaries: current.workflow.usage.model_summaries.map((item) => ({
        ...item,
      })),
    },
    stages: current.workflow.stages.map((item) => ({ ...item })),
    section_lanes: current.workflow.section_lanes.map((lane) => ({
      ...lane,
      items: lane.items.map((item) => ({
        ...item,
        retry_timer: { ...item.retry_timer },
      })),
    })),
    llm_attempts: current.workflow.llm_attempts.map((item) => ({ ...item })),
    timeline: current.workflow.timeline.map((item) => ({ ...item })),
    claim_clusters: current.workflow.claim_clusters?.map((item) => ({
      ...item,
      members: item.members.map((member) => ({ ...member })),
      claims: item.claims.map((claim) => ({ ...claim })),
      comparisons: item.comparisons.map((comparison) => ({ ...comparison })),
      compacted_claims: item.compacted_claims?.map((claim) => ({ ...claim })),
    })),
    claim_compaction_comparisons: current.workflow.claim_compaction_comparisons?.map(
      (item) => ({ ...item }),
    ),
    curation: { ...current.workflow.curation },
    actions: current.workflow.actions.map((item) => ({ ...item })),
  },
});

const stageById = (
  response: WorkbenchWorkflowLiveStateResponse,
  id: string,
): WorkbenchWorkflowStageLiveState => {
  const existing = response.workflow.stages.find((item) => item.id === id);
  if (existing) return existing;

  const created = stage(id, id, "pending");
  response.workflow.stages.push(created);
  return created;
};

const claimBuilderLane = (
  response: WorkbenchWorkflowLiveStateResponse,
): WorkbenchSectionLaneLiveState => {
  const existing = response.workflow.section_lanes.find(
    (item) => item.lane_id === "claim_builder",
  );
  if (existing) return existing;

  const created: WorkbenchSectionLaneLiveState = {
    lane_index: response.workflow.section_lanes.length,
    lane_id: "claim_builder",
    ready_count: 0,
    leased_count: 0,
    done_count: 0,
    failed_count: 0,
    waiting_count: 0,
    total_attempt_count: 0,
    max_attempt_count: 0,
    items: [],
  };
  response.workflow.section_lanes.push(created);
  return created;
};

const queueStatusFromWorkItemState = (state: string | null): string => {
  const normalized = normalize(state);
  if (normalized === "leased" || normalized === "running") return "leased";
  if (normalized === "completed" || normalized === "succeeded") return "completed";
  if (normalized === "retryable_failed") return "retryable_failed";
  if (normalized === "terminal_failed" || normalized === "failed") return "terminal_failed";
  if (normalized === "user_action_required") return "user_action_required";
  return "ready";
};

const upsertSectionItem = (
  response: WorkbenchWorkflowLiveStateResponse,
  patch: {
    sourceUnitRef: string;
    sourceUnitOrdinal: number;
    workItemId?: string | null;
    status?: string | null;
    attemptCount?: number | null;
    errorKind?: string | null;
    leaseExpiresAt?: string | null;
    userActionRequired?: boolean;
    blockedReason?: string | null;
  },
): WorkbenchSectionQueueItemLiveState => {
  const lane = claimBuilderLane(response);
  const existing = lane.items.find(
    (item) =>
      item.section_id === patch.sourceUnitRef ||
      (patch.workItemId ? item.queue_item_id === patch.workItemId : false),
  );

  const nextStatus = patch.status || existing?.status || "ready";
  const item: WorkbenchSectionQueueItemLiveState = {
    queue_item_id: patch.workItemId || existing?.queue_item_id || patch.sourceUnitRef,
    section_id: patch.sourceUnitRef,
    section_index: patch.sourceUnitOrdinal,
    section_key: patch.sourceUnitRef,
    status: nextStatus,
    attempt_count: Math.max(
      existing?.attempt_count ?? 0,
      patch.attemptCount ?? 0,
    ),
    lease_expires_at: patch.leaseExpiresAt ?? existing?.lease_expires_at ?? null,
    claimed_by_worker_id: existing?.claimed_by_worker_id ?? null,
    error_kind: patch.errorKind ?? existing?.error_kind ?? null,
    retry_plan: existing?.retry_plan ?? null,
    user_action_required: patch.userActionRequired ?? existing?.user_action_required ?? false,
    blocked_reason: patch.blockedReason ?? existing?.blocked_reason ?? null,
    retry_timer: existing?.retry_timer ?? {},
  };

  if (existing) {
    const index = lane.items.indexOf(existing);
    lane.items[index] = item;
  } else {
    lane.items.push(item);
  }

  lane.items.sort((left, right) => left.section_index - right.section_index);
  return item;
};

const upsertAttempt = (
  response: WorkbenchWorkflowLiveStateResponse,
  patch: {
    dispatchAttemptId: string;
    sourceUnitRef?: string | null;
    status: string;
    provider?: string | null;
    accountRef?: string | null;
    modelRef?: string | null;
    attemptNumber?: number | null;
    startedAt?: string | null;
    completedAt?: string | null;
    promptTokens?: number | null;
    completionTokens?: number | null;
    totalTokens?: number | null;
    errorKind?: string | null;
    errorMessageUser?: string | null;
  },
): WorkbenchLlmAttemptLiveState => {
  const existing = response.workflow.llm_attempts.find(
    (item) => item.node_run_id === patch.dispatchAttemptId,
  );

  const attempt: WorkbenchLlmAttemptLiveState = {
    node_run_id: patch.dispatchAttemptId,
    section_id: patch.sourceUnitRef ?? existing?.section_id ?? null,
    node_name: CLAIM_BUILDER_NODE_NAME,
    node_kind: "llm",
    status: patch.status,
    started_at: patch.startedAt ?? existing?.started_at ?? null,
    completed_at: patch.completedAt ?? existing?.completed_at ?? null,
    duration_ms: existing?.duration_ms ?? null,
    model_provider: patch.provider ?? existing?.model_provider ?? null,
    model_name: patch.modelRef ?? existing?.model_name ?? null,
    account_ref: patch.accountRef ?? existing?.account_ref ?? null,
    prompt_tokens: patch.promptTokens ?? existing?.prompt_tokens ?? 0,
    completion_tokens: patch.completionTokens ?? existing?.completion_tokens ?? 0,
    total_tokens:
      patch.totalTokens ??
      existing?.total_tokens ??
      (patch.promptTokens ?? 0) + (patch.completionTokens ?? 0),
    error_kind: patch.errorKind ?? existing?.error_kind ?? null,
    error_message_user: patch.errorMessageUser ?? existing?.error_message_user ?? null,
    retry_plan: existing?.retry_plan ?? null,
    user_action_required: existing?.user_action_required ?? false,
    blocked_reason: existing?.blocked_reason ?? null,
  };

  if (existing) {
    const index = response.workflow.llm_attempts.indexOf(existing);
    response.workflow.llm_attempts[index] = attempt;
  } else {
    response.workflow.llm_attempts.push(attempt);
  }

  return attempt;
};

const appendTimeline = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
  message: string,
): void => {
  if (
    response.workflow.timeline.some(
      (item) => item.timeline_entry_id === event.projection_event_id,
    )
  ) {
    return;
  }

  const entry: WorkbenchWorkflowTimelineEntryLiveState = {
    timeline_entry_id: event.projection_event_id,
    event_type: event.event_type,
    phase: event.canonical_phase || "",
    severity: "info",
    message,
    occurred_at: event.occurred_at,
    source_ref: text(event.payload, "source_unit_ref"),
    work_item_id: text(event.payload, "work_item_id"),
    attempt_id: text(event.payload, "dispatch_attempt_id"),
  };
  response.workflow.timeline.push(entry);
};

const recomputeLaneCounters = (
  response: WorkbenchWorkflowLiveStateResponse,
): void => {
  for (const lane of response.workflow.section_lanes) {
    lane.ready_count = 0;
    lane.leased_count = 0;
    lane.done_count = 0;
    lane.failed_count = 0;
    lane.waiting_count = 0;
    lane.total_attempt_count = 0;
    lane.max_attempt_count = 0;

    for (const item of lane.items) {
      const status = normalize(item.status);
      if (status === "leased" || status === "running") {
        lane.leased_count += 1;
      } else if (status === "completed" || status === "claim_observations_persisted") {
        lane.done_count += 1;
      } else if (
        status === "retryable_failed" ||
        status === "terminal_failed" ||
        status === "failed" ||
        status === "user_action_required"
      ) {
        lane.failed_count += 1;
      } else if (status === "deferred" || status === "waiting") {
        lane.waiting_count += 1;
      } else {
        lane.ready_count += 1;
      }

      lane.total_attempt_count += item.attempt_count;
      lane.max_attempt_count = Math.max(lane.max_attempt_count, item.attempt_count);
    }
  }
};

const recomputeUsage = (
  response: WorkbenchWorkflowLiveStateResponse,
): void => {
  const attempts = response.workflow.llm_attempts;
  const totalPrompt = attempts.reduce(
    (total, attempt) => total + Math.max(0, attempt.prompt_tokens || 0),
    0,
  );
  const totalCompletion = attempts.reduce(
    (total, attempt) => total + Math.max(0, attempt.completion_tokens || 0),
    0,
  );
  const totalTokens = attempts.reduce(
    (total, attempt) => total + Math.max(0, attempt.total_tokens || 0),
    0,
  );

  response.workflow.usage = {
    ...response.workflow.usage,
    total_prompt_tokens: totalPrompt,
    total_completion_tokens: totalCompletion,
    total_tokens: Math.max(totalTokens, totalPrompt + totalCompletion),
    total_llm_calls: attempts.length,
  };
};

const syncStagesFromLanes = (
  response: WorkbenchWorkflowLiveStateResponse,
): void => {
  const lane = claimBuilderLane(response);
  const total = lane.items.length;
  const done = lane.done_count;
  const failed = lane.failed_count;
  const active = lane.leased_count > 0;
  const ready = lane.ready_count > 0 || lane.waiting_count > 0;

  const claimStage = stageById(response, "prompt_a_claim_extraction");
  claimStage.total = Math.max(claimStage.total, total);
  claimStage.current = Math.max(claimStage.current, done);
  if (total > 0) {
    if (done + failed >= total && failed === 0) {
      claimStage.status = "completed";
      claimStage.completed_at = claimStage.completed_at ?? nowIso();
    } else if (failed > 0 && done + failed >= total) {
      claimStage.status = "failed";
    } else if (active || ready || done > 0) {
      claimStage.status = "running";
      claimStage.started_at = claimStage.started_at ?? response.workflow.timer.started_at ?? nowIso();
    }
  }

  const sourceStage = stageById(response, "source_ingestion");
  if (total > 0) {
    sourceStage.total = Math.max(sourceStage.total, total);
    sourceStage.current = Math.max(sourceStage.current, total);
    sourceStage.status = "completed";
    sourceStage.completed_at = sourceStage.completed_at ?? nowIso();
  }

  if (claimStage.status === "completed") {
    response.document_status = "processing";
    response.workflow.current_phase = "draft_claim_embeddings";
  } else if (claimStage.status === "running") {
    response.document_status = "processing";
    response.workflow.current_phase = "claim_builder_section_extraction";
  }
};

const applySourceUnitsCreated = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
): void => {
  const count = intValue(event.payload, "source_unit_count") ?? 0;
  const sourceStage = stageById(response, "source_ingestion");
  sourceStage.total = Math.max(sourceStage.total, count);
  sourceStage.current = Math.max(sourceStage.current, count);
  sourceStage.status = "completed";
  sourceStage.completed_at = event.occurred_at;

  const claimStage = stageById(response, "prompt_a_claim_extraction");
  claimStage.total = Math.max(claimStage.total, count);
  if (count > 0 && claimStage.status === "pending") {
    claimStage.status = "running";
    claimStage.started_at = claimStage.started_at ?? event.occurred_at;
  }

  response.workflow.current_phase = "claim_builder_work_scheduling";
  appendTimeline(response, event, `Документ разбит на ${count} разделов`);
};

const applySourceUnitCreated = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
): void => {
  const sourceUnitRef = text(event.payload, "source_unit_ref");
  if (!sourceUnitRef) return;

  const ordinal = intValue(event.payload, "source_unit_ordinal") ?? 0;
  upsertSectionItem(response, {
    sourceUnitRef,
    sourceUnitOrdinal: ordinal,
    status: "ready",
    attemptCount: 0,
  });
  appendTimeline(response, event, `Создан раздел ${ordinal + 1}`);
};

const applyWorkItemScheduled = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
): void => {
  const sourceUnitRef = text(event.payload, "source_unit_ref");
  if (!sourceUnitRef) return;

  const workItemId = text(event.payload, "work_item_id");
  const ordinal = intValue(event.payload, "source_unit_ordinal") ?? 0;
  const state =
    text(event.payload, "schedule_status") ||
    text(event.payload, "initial_work_item_state") ||
    "ready";

  upsertSectionItem(response, {
    sourceUnitRef,
    sourceUnitOrdinal: ordinal,
    workItemId,
    status: queueStatusFromWorkItemState(state),
    attemptCount: intValue(event.payload, "attempt_count") ?? 0,
  });

  response.workflow.current_phase = "claim_builder_section_extraction";
  appendTimeline(response, event, `Раздел ${ordinal + 1} поставлен в очередь`);
};

const applyDispatchAttemptPrepared = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
): void => {
  const sourceUnitRef = text(event.payload, "source_unit_ref");
  const workItemId = text(event.payload, "work_item_id");
  const dispatchAttemptId = text(event.payload, "dispatch_attempt_id");
  if (!sourceUnitRef || !dispatchAttemptId) return;

  const existing = claimBuilderLane(response).items.find(
    (item) => item.section_id === sourceUnitRef || item.queue_item_id === workItemId,
  );
  const ordinal = existing?.section_index ?? 0;
  const attemptNumber = intValue(event.payload, "attempt_number") ?? 1;

  upsertSectionItem(response, {
    sourceUnitRef,
    sourceUnitOrdinal: ordinal,
    workItemId,
    status: "leased",
    attemptCount: attemptNumber,
    leaseExpiresAt: text(event.payload, "lease_expires_at"),
  });

  upsertAttempt(response, {
    dispatchAttemptId,
    sourceUnitRef,
    status: queueStatusFromWorkItemState(text(event.payload, "attempt_state")),
    provider: text(event.payload, "provider"),
    accountRef: text(event.payload, "account_ref"),
    modelRef: text(event.payload, "model_ref"),
    attemptNumber,
    startedAt: event.occurred_at,
  });

  response.workflow.current_phase = "claim_builder_section_extraction";
  appendTimeline(response, event, `LLM-попытка ${attemptNumber} запущена`);
};

const applySectionOutcome = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
  status: "completed" | "retryable_failed" | "terminal_failed",
): void => {
  const sourceUnitRef = text(event.payload, "source_unit_ref");
  const workItemId = text(event.payload, "work_item_id");
  const dispatchAttemptId = text(event.payload, "dispatch_attempt_id");
  if (!sourceUnitRef) return;

  const existing = claimBuilderLane(response).items.find(
    (item) => item.section_id === sourceUnitRef || item.queue_item_id === workItemId,
  );
  const ordinal = existing?.section_index ?? 0;
  const attemptNumber =
    intValue(event.payload, "attempt_number") ??
    Math.max(existing?.attempt_count ?? 0, 1);

  upsertSectionItem(response, {
    sourceUnitRef,
    sourceUnitOrdinal: ordinal,
    workItemId,
    status,
    attemptCount: attemptNumber,
    errorKind: text(event.payload, "error_kind"),
    userActionRequired: status === "terminal_failed",
    blockedReason: text(event.payload, "validation_failure_reason"),
  });

  if (dispatchAttemptId) {
    upsertAttempt(response, {
      dispatchAttemptId,
      sourceUnitRef,
      status,
      provider: text(event.payload, "provider"),
      accountRef: text(event.payload, "account_ref"),
      modelRef: text(event.payload, "model_ref"),
      attemptNumber,
      completedAt: event.occurred_at,
      promptTokens: intValue(event.payload, "actual_prompt_tokens"),
      completionTokens: intValue(event.payload, "actual_completion_tokens"),
      totalTokens: intValue(event.payload, "actual_total_tokens"),
      errorKind: text(event.payload, "error_kind"),
      errorMessageUser: text(event.payload, "validation_failure_reason"),
    });
  }

  const persisted = intValue(event.payload, "persisted_draft_claim_count") ?? 0;
  const message =
    status === "completed"
      ? `Раздел обработан, сохранено утверждений: ${persisted}`
      : status === "retryable_failed"
        ? "Раздел не принят, будет повторная попытка"
        : "Раздел завершился ошибкой";
  appendTimeline(response, event, message);
};

const setWorkflowActions = (
  response: WorkbenchWorkflowLiveStateResponse,
  mode: "running" | "paused" | "completed",
): void => {
  if (mode === "paused") {
    response.workflow.actions = [
      {
        action_id: "resume_processing",
        visible: true,
        enabled: true,
        reason_code: null,
      },
      {
        action_id: "delete_document",
        visible: true,
        enabled: true,
        reason_code: null,
      },
    ];
    return;
  }

  if (mode === "completed") {
    response.workflow.actions = [
      {
        action_id: "delete_document",
        visible: true,
        enabled: true,
        reason_code: null,
      },
    ];
    return;
  }

  response.workflow.actions = [
    {
      action_id: "cancel_processing",
      visible: true,
      enabled: true,
      reason_code: null,
    },
  ];
};

const applyManualPaused = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
): void => {
  response.document_status = "paused";
  response.workflow.workflow_status = "paused";
  response.workflow.timer.mode = "paused";
  response.workflow.timer.is_live = false;
  response.workflow.timer.current_active_started_at = null;
  setWorkflowActions(response, "paused");
  appendTimeline(response, event, "Обработка документа приостановлена");
};

const applyManualResumed = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
): void => {
  response.document_status = "processing";
  response.workflow.workflow_status = "running";
  response.workflow.timer.mode = "running";
  response.workflow.timer.is_live = true;
  response.workflow.timer.current_active_started_at = event.occurred_at;
  setWorkflowActions(response, "running");
  appendTimeline(response, event, "Обработка документа продолжена");
};

const applyCurationReviewRequired = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
): void => {
  const workspaceRef = text(event.payload, "workspace_ref");
  const itemCount = intValue(event.payload, "item_count") ?? 0;
  const curationStage = stageById(response, "curation");
  curationStage.status = "running";
  curationStage.total = Math.max(curationStage.total, itemCount);
  curationStage.current = itemCount;
  curationStage.started_at = curationStage.started_at ?? event.occurred_at;

  response.document_status = "processed";
  response.workflow.workflow_status = "waiting_for_review";
  response.workflow.current_phase = "draft_claim_curation";
  response.workflow.timer.mode = "paused";
  response.workflow.timer.is_live = false;
  response.workflow.curation = {
    ...response.workflow.curation,
    available: true,
    reason_code: "ready_for_review",
    workflow_run_id: event.workflow_run_id,
    workspace_ref: workspaceRef,
    workspace_status: "pending",
    item_count: itemCount,
  };
  appendTimeline(response, event, `Рабочее пространство проверки готово: ${itemCount}`);
};

const applyCurationPublished = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
): void => {
  const publishedCount = intValue(event.payload, "published_item_count") ?? 0;
  const curationStage = stageById(response, "curation");
  curationStage.status = "completed";
  curationStage.completed_at = event.occurred_at;

  const publicationStage = stageById(response, "publication");
  publicationStage.status = "completed";
  publicationStage.total = Math.max(publicationStage.total, publishedCount);
  publicationStage.current = publishedCount;
  publicationStage.started_at = publicationStage.started_at ?? event.occurred_at;
  publicationStage.completed_at = event.occurred_at;

  response.document_status = "published";
  response.workflow.workflow_status = "completed";
  response.workflow.current_phase = "completed";
  response.workflow.timer.mode = "completed";
  response.workflow.timer.is_live = false;
  response.workflow.timer.completed_at = event.occurred_at;
  response.workflow.curation = {
    ...response.workflow.curation,
    available: false,
    reason_code: "published",
    workspace_status: "published",
  };
  setWorkflowActions(response, "completed");
  appendTimeline(response, event, `Опубликовано записей: ${publishedCount}`);
};

const applyBatchPrepared = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
): void => {
  const sourceUnitRefs = stringArray(event.payload, "source_unit_refs");
  const workItemIds = stringArray(event.payload, "work_item_ids");
  sourceUnitRefs.forEach((sourceUnitRef, index) => {
    const existing = claimBuilderLane(response).items.find(
      (item) => item.section_id === sourceUnitRef,
    );
    upsertSectionItem(response, {
      sourceUnitRef,
      sourceUnitOrdinal: existing?.section_index ?? index,
      workItemId: workItemIds[index] ?? existing?.queue_item_id ?? null,
      status: "leased",
      attemptCount: existing?.attempt_count ?? 0,
    });
  });

  appendTimeline(
    response,
    event,
    `Подготовлен batch LLM dispatch: ${intValue(event.payload, "prepared_dispatch_count") ?? sourceUnitRefs.length}`,
  );
};

export const reduceWorkflowFrontendProjectionEvent = (
  current: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
): WorkbenchWorkflowLiveStateResponse => {
  const payload = isRecord(event.payload) ? event.payload : {};
  const normalizedEvent: FrontendWorkflowEventEnvelope = {
    ...event,
    payload,
  };

  const next = cloneResponse(current);
  next.current_processing_run_id = normalizedEvent.workflow_run_id;
  next.workflow.workflow_run_id = normalizedEvent.workflow_run_id;
  next.workflow.source_document_ref =
    text(payload, "source_document_ref") || next.workflow.source_document_ref || next.document_id;
  const startsActive = ![
    "workflow_manually_paused",
    "workflow_draft_claim_curation_workspace_opened",
    "workflow_draft_claim_curation_review_required",
    "workflow_draft_claim_curation_workspace_published",
  ].includes(normalizedEvent.projection_type);

  if (startsActive) {
    next.workflow.workflow_status = "running";
    next.workflow.timer.mode = "running";
    next.workflow.timer.is_live = true;
  }
  next.workflow.timer.current_active_started_at =
    next.workflow.timer.current_active_started_at ||
    normalizedEvent.occurred_at;
  next.workflow.timer.started_at =
    next.workflow.timer.started_at ||
    normalizedEvent.occurred_at;

  if (normalizedEvent.canonical_phase) {
    next.workflow.current_phase = normalizedEvent.canonical_phase;
  }

  switch (normalizedEvent.projection_type) {
    case "workflow_source_document_persisted":
      next.document_status = "processing";
      next.workflow.current_phase = "source_ingestion";
      appendTimeline(next, normalizedEvent, "Документ сохранён и принят в обработку");
      break;
    case "workflow_source_units_created":
      applySourceUnitsCreated(next, normalizedEvent);
      break;
    case "workflow_source_unit_created":
      applySourceUnitCreated(next, normalizedEvent);
      break;
    case "workflow_work_items_scheduled":
      appendTimeline(
        next,
        normalizedEvent,
        `Запланировано разделов: ${intValue(payload, "scheduled_work_item_count") ?? 0}`,
      );
      break;
    case "workflow_claim_builder_work_item_scheduled":
      applyWorkItemScheduled(next, normalizedEvent);
      break;
    case "workflow_dispatch_batch_prepared":
      applyBatchPrepared(next, normalizedEvent);
      break;
    case "workflow_claim_builder_dispatch_attempt_prepared":
      applyDispatchAttemptPrepared(next, normalizedEvent);
      break;
    case "workflow_claim_builder_section_extracted":
      applySectionOutcome(next, normalizedEvent, "completed");
      break;
    case "workflow_claim_builder_section_retryable_failed":
      applySectionOutcome(next, normalizedEvent, "retryable_failed");
      break;
    case "workflow_claim_builder_section_terminal_failed":
      applySectionOutcome(next, normalizedEvent, "terminal_failed");
      break;
    case "workflow_claim_builder_all_sections_extracted": {
      const claimStage = stageById(next, "prompt_a_claim_extraction");
      claimStage.status = "completed";
      claimStage.current = Math.max(claimStage.current, claimStage.total);
      claimStage.completed_at = normalizedEvent.occurred_at;
      next.workflow.current_phase = "draft_claim_embeddings";
      appendTimeline(next, normalizedEvent, "Все разделы обработаны");
      break;
    }
    case "workflow_manually_paused":
      applyManualPaused(next, normalizedEvent);
      break;
    case "workflow_manually_resumed":
      applyManualResumed(next, normalizedEvent);
      break;
    case "workflow_draft_claim_curation_workspace_opened":
    case "workflow_draft_claim_curation_review_required":
      applyCurationReviewRequired(next, normalizedEvent);
      break;
    case "workflow_draft_claim_curation_workspace_published":
      applyCurationPublished(next, normalizedEvent);
      break;
    default:
      appendTimeline(
        next,
        normalizedEvent,
        `Получено frontend-событие: ${normalizedEvent.projection_type}`,
      );
      break;
  }

  recomputeLaneCounters(next);
  syncStagesFromLanes(next);
  recomputeUsage(next);

  return next;
};
