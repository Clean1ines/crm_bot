import type {
  FrontendWorkflowEventEnvelope,
  WorkbenchLlmAttemptLiveState,
  WorkbenchSectionLaneLiveState,
  WorkbenchSectionQueueItemLiveState,
  WorkbenchWorkflowLiveStateResponse,
  WorkbenchWorkflowStageLiveState,
  WorkbenchWorkflowTimelineEntryLiveState,
  WorkbenchClaimClusterLiveState,
  WorkbenchClaimClusterBatchLiveState,
  WorkbenchCompactedClaimPreviewLiveState,
} from "@shared/api/modules/knowledge";

export type InitialWorkflowProjectionDocument = {
  documentId: string;
  projectId: string;
  fileName: string;
  documentStatus: string;
  workflowRunId: string;
};

const CLAIM_BUILDER_NODE_NAME = "knowledge_workbench.claim_builder";
const DRAFT_CLAIM_COMPACTION_NODE_NAME =
  "knowledge_workbench.draft_claim_compaction";

const nowIso = (): string => new Date().toISOString();

const emptyUsage = () => ({
  total_prompt_tokens: 0,
  total_completion_tokens: 0,
  total_tokens: 0,
  total_llm_calls: 0,
  model_summaries: [],
});

const emptyTimer = () => ({
  mode: "stopped",
  active_elapsed_seconds: 0,
  wall_elapsed_seconds: 0,
  current_active_started_at: null,
  started_at: null,
  completed_at: null,
  is_live: false,
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
  return {
    document_id: document.documentId,
    project_id: document.projectId,
    file_name: document.fileName,
    document_status: document.documentStatus || "processing",
    current_processing_run_id: document.workflowRunId,
    workflow: {
      workflow_run_id: document.workflowRunId,
      source_document_ref: document.documentId,
      workflow_status: "pending",
      current_phase: "source_ingestion",
      timer: emptyTimer(),
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
          action_id: "pause_processing",
          visible: false,
          enabled: false,
          reason_code: "not_running",
        },
        {
          action_id: "resume_processing",
          visible: false,
          enabled: false,
          reason_code: "not_paused",
        },
        {
          action_id: "cancel_processing",
          visible: false,
          enabled: false,
          reason_code: "hidden_terminal_cancel",
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

const recordValue = (
  payload: Record<string, unknown>,
  key: string,
): Record<string, unknown> | null => {
  const value = payload[key];
  return isRecord(value) ? value : null;
};

const recordArray = (
  payload: Record<string, unknown>,
  key: string,
): Record<string, unknown>[] => {
  const value = payload[key];
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord);
};

const normalize = (value: string | null | undefined): string =>
  (value || "").trim().toLowerCase();

const isPausedWorkflow = (response: WorkbenchWorkflowLiveStateResponse): boolean =>
  normalize(response.workflow.workflow_status) === "paused" ||
  normalize(response.workflow.timer.mode) === "paused";

const secondsBetweenIso = (
  startedAt: string | null | undefined,
  stoppedAt: string | null | undefined,
): number => {
  if (!startedAt || !stoppedAt) return 0;

  const startedMs = Date.parse(startedAt);
  const stoppedMs = Date.parse(stoppedAt);

  if (!Number.isFinite(startedMs) || !Number.isFinite(stoppedMs)) return 0;
  return Math.max(0, Math.floor((stoppedMs - startedMs) / 1000));
};

const freezeWorkflowTimer = (
  response: WorkbenchWorkflowLiveStateResponse,
  occurredAt: string,
  mode: string,
): void => {
  const timer = response.workflow.timer;
  const activeStartedAt = timer.current_active_started_at ?? occurredAt;

  const elapsedSeconds = Math.max(
    timer.active_elapsed_seconds ?? 0,
    (timer.active_elapsed_seconds ?? 0) + secondsBetweenIso(activeStartedAt, occurredAt),
  );

  timer.mode = mode;
  timer.active_elapsed_seconds = elapsedSeconds;
  timer.wall_elapsed_seconds = Math.max(
    timer.wall_elapsed_seconds ?? 0,
    elapsedSeconds,
  );
  timer.current_active_started_at = null;
  timer.completed_at = timer.completed_at ?? occurredAt;
  timer.is_live = false;
};

const markWorkflowRunning = (
  response: WorkbenchWorkflowLiveStateResponse,
  occurredAt: string,
): void => {
  response.document_status = "processing";
  response.workflow.workflow_status = "running";
  response.workflow.timer.mode = "running";
  response.workflow.timer.started_at =
    response.workflow.timer.started_at ?? occurredAt;
  response.workflow.timer.current_active_started_at = occurredAt;
  response.workflow.timer.completed_at = null;
  response.workflow.timer.is_live = true;
  setWorkflowActionState(response, "pause_processing", {
    visible: true,
    enabled: true,
    reason_code: null,
  });
  setWorkflowActionState(response, "resume_processing", {
    visible: false,
    enabled: false,
    reason_code: "not_paused",
  });
  setWorkflowActionState(response, "cancel_processing", {
    visible: false,
    enabled: false,
    reason_code: "hidden_terminal_cancel",
  });
};

const markWorkflowPaused = (
  response: WorkbenchWorkflowLiveStateResponse,
  occurredAt: string,
): void => {
  response.document_status = "paused";
  response.workflow.workflow_status = "paused";
  freezeWorkflowTimer(response, occurredAt, "paused");
  setWorkflowActionState(response, "pause_processing", {
    visible: false,
    enabled: false,
    reason_code: "not_running",
  });
  setWorkflowActionState(response, "resume_processing", {
    visible: true,
    enabled: true,
    reason_code: null,
  });
  setWorkflowActionState(response, "cancel_processing", {
    visible: false,
    enabled: false,
    reason_code: "not_running",
  });
};

const hideActiveProcessingActions = (
  response: WorkbenchWorkflowLiveStateResponse,
): void => {
  setWorkflowActionState(response, "pause_processing", {
    visible: false,
    enabled: false,
    reason_code: "waiting_for_curation",
  });
  setWorkflowActionState(response, "resume_processing", {
    visible: false,
    enabled: false,
    reason_code: "waiting_for_curation",
  });
  setWorkflowActionState(response, "cancel_processing", {
    visible: false,
    enabled: false,
    reason_code: "waiting_for_curation",
  });
};


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
      batches: item.batches?.map((batch) => ({ ...batch })),
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


const setWorkflowActionState = (
  response: WorkbenchWorkflowLiveStateResponse,
  actionId: string,
  patch: {
    visible: boolean;
    enabled: boolean;
    reason_code?: string | null;
  },
): void => {
  const existing = response.workflow.actions.find((item) => item.action_id === actionId);
  if (existing) {
    existing.visible = patch.visible;
    existing.enabled = patch.enabled;
    existing.reason_code = patch.reason_code ?? null;
    return;
  }

  response.workflow.actions.push({
    action_id: actionId,
    visible: patch.visible,
    enabled: patch.enabled,
    reason_code: patch.reason_code ?? null,
  });
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
    sourceUnitTitle?: string | null;
    sourceUnitText?: string | null;
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
    source_unit_title: patch.sourceUnitTitle ?? existing?.source_unit_title ?? null,
    source_unit_text: patch.sourceUnitText ?? existing?.source_unit_text ?? null,
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
    nodeName?: string | null;
  },
): WorkbenchLlmAttemptLiveState => {
  const existing = response.workflow.llm_attempts.find(
    (item) => item.node_run_id === patch.dispatchAttemptId,
  );

  const attempt: WorkbenchLlmAttemptLiveState = {
    node_run_id: patch.dispatchAttemptId,
    section_id: patch.sourceUnitRef ?? existing?.section_id ?? null,
    node_name: patch.nodeName ?? existing?.node_name ?? CLAIM_BUILDER_NODE_NAME,
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

const findLiveAttemptIdForSection = (
  response: WorkbenchWorkflowLiveStateResponse,
  sourceUnitRef: string,
): string | null => {
  const attempts = response.workflow.llm_attempts.filter(
    (attempt) =>
      attempt.section_id === sourceUnitRef &&
      ["leased", "running"].includes(normalize(attempt.status)),
  );
  const latest = attempts.sort(
    (left, right) =>
      Date.parse(right.started_at || "") - Date.parse(left.started_at || ""),
  )[0];
  return latest?.node_run_id ?? null;
};

const findLiveCompactionAttemptIdForScope = (
  response: WorkbenchWorkflowLiveStateResponse,
  scopeRefs: Array<string | null | undefined>,
): string | null => {
  const refs = new Set(scopeRefs.filter((item): item is string => Boolean(item)));
  if (refs.size === 0) return null;

  const attempts = response.workflow.llm_attempts.filter((attempt) => {
    const nodeName = normalize(attempt.node_name);
    const sectionId = attempt.section_id;
    if (!sectionId) return false;
    return (
      nodeName.includes("draft_claim_compaction") &&
      refs.has(sectionId) &&
      ["leased", "running"].includes(normalize(attempt.status))
    );
  });
  const latest = attempts.sort(
    (left, right) =>
      Date.parse(right.started_at || "") - Date.parse(left.started_at || ""),
  )[0];
  return latest?.node_run_id ?? null;
};

const resolveOutcomeAttemptId = (
  response: WorkbenchWorkflowLiveStateResponse,
  sourceUnitRef: string,
  dispatchAttemptId: string | null,
): string | null => {
  if (
    dispatchAttemptId &&
    response.workflow.llm_attempts.some(
      (attempt) => attempt.node_run_id === dispatchAttemptId,
    )
  ) {
    return dispatchAttemptId;
  }
  return findLiveAttemptIdForSection(response, sourceUnitRef) ?? dispatchAttemptId;
};

const resolveCompactionOutcomeAttemptId = (
  response: WorkbenchWorkflowLiveStateResponse,
  dispatchAttemptId: string | null,
  scopeRefs: Array<string | null | undefined>,
): string | null => {
  if (
    dispatchAttemptId &&
    response.workflow.llm_attempts.some(
      (attempt) => attempt.node_run_id === dispatchAttemptId,
    )
  ) {
    return dispatchAttemptId;
  }

  return (
    findLiveCompactionAttemptIdForScope(response, scopeRefs) ??
    dispatchAttemptId
  );
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
    if (!isPausedWorkflow(response)) {
      response.document_status = "processing";
    }
    if (
      response.workflow.current_phase === "source_ingestion" ||
      response.workflow.current_phase === "claim_builder_work_scheduling" ||
      response.workflow.current_phase === "claim_builder_section_extraction"
    ) {
      response.workflow.current_phase = "draft_claim_embeddings";
    }
  } else if (claimStage.status === "running") {
    if (!isPausedWorkflow(response)) {
      response.document_status = "processing";
    }
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
    sourceUnitTitle: text(event.payload, "source_unit_title"),
    sourceUnitText: text(event.payload, "source_unit_text"),
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
    sourceUnitTitle: text(event.payload, "source_unit_title"),
    sourceUnitText: text(event.payload, "source_unit_text"),
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

const draftClaimsFromPayload = (
  payload: Record<string, unknown>,
): Record<string, unknown>[] => {
  const value = payload.draft_claims;
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord);
};

const attachDraftClaimsToSectionItem = (
  response: WorkbenchWorkflowLiveStateResponse,
  sourceUnitRef: string,
  draftClaims: Record<string, unknown>[],
): void => {
  if (!sourceUnitRef || draftClaims.length === 0) return;

  for (const lane of response.workflow.section_lanes) {
    lane.items = lane.items.map((item) => {
      if (item.section_id !== sourceUnitRef) return item;
      const previous =
        (item as unknown as { draft_claims?: Record<string, unknown>[] })
          .draft_claims ?? [];
      const byRef = new Map<string, Record<string, unknown>>();

      for (const claim of previous) {
        const ref =
          typeof claim.observation_ref === "string"
            ? claim.observation_ref
            : JSON.stringify(claim);
        byRef.set(ref, claim);
      }
      for (const claim of draftClaims) {
        const ref =
          typeof claim.observation_ref === "string"
            ? claim.observation_ref
            : JSON.stringify(claim);
        byRef.set(ref, claim);
      }

      return {
        ...item,
        draft_claims: Array.from(byRef.values()),
      } as WorkbenchSectionQueueItemLiveState & {
        draft_claims: Record<string, unknown>[];
      };
    });
  }
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

  const outcomeAttemptId = resolveOutcomeAttemptId(
    response,
    sourceUnitRef,
    dispatchAttemptId,
  );

  if (outcomeAttemptId) {
    upsertAttempt(response, {
      dispatchAttemptId: outcomeAttemptId,
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

  attachDraftClaimsToSectionItem(
    response,
    sourceUnitRef,
    draftClaimsFromPayload(event.payload),
  );

  const persisted = intValue(event.payload, "persisted_draft_claim_count") ?? 0;
  const message =
    status === "completed"
      ? `Раздел обработан, сохранено утверждений: ${persisted}`
      : status === "retryable_failed"
        ? "Раздел не принят, будет повторная попытка"
        : "Раздел завершился ошибкой";
  appendTimeline(response, event, message);
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

const markStage = (
  response: WorkbenchWorkflowLiveStateResponse,
  id: string,
  status: WorkbenchWorkflowStageLiveState["status"],
  occurredAt: string,
  current?: number,
  total?: number,
): void => {
  const item = stageById(response, id);
  item.status = status;
  if (typeof total === "number") item.total = Math.max(item.total, total);
  if (typeof current === "number") item.current = Math.max(item.current, current);
  if (status === "running") {
    item.started_at = item.started_at ?? occurredAt;
  }
  if (status === "completed") {
    item.started_at = item.started_at ?? occurredAt;
    item.completed_at = item.completed_at ?? occurredAt;
    if (item.total > 0) item.current = Math.max(item.current, item.total);
  }
};

const claimClustersFromPayload = (
  payload: Record<string, unknown>,
): WorkbenchClaimClusterLiveState[] => {
  const value = payload.clusters;
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord) as unknown as WorkbenchClaimClusterLiveState[];
};

const recomputeClusterBatchCounters = (
  cluster: WorkbenchClaimClusterLiveState,
): WorkbenchClaimClusterLiveState => {
  const batches = cluster.batches ?? [];
  const ready = batches.filter((item) => normalize(item.status) === "ready").length;
  const leased = batches.filter((item) =>
    ["leased", "running"].includes(normalize(item.status)),
  ).length;
  const completed = batches.filter((item) =>
    ["completed", "succeeded"].includes(normalize(item.status)),
  ).length;
  const retryableFailed = batches.filter((item) =>
    normalize(item.status) === "retryable_failed",
  ).length;
  const terminalFailed = batches.filter((item) =>
    ["terminal_failed", "failed"].includes(normalize(item.status)),
  ).length;
  const userActionRequired = batches.filter((item) =>
    normalize(item.status) === "user_action_required",
  ).length;

  return {
    ...cluster,
    status:
      batches.length > 0 && completed === batches.length
        ? "compacted"
        : leased > 0
          ? "processing"
          : retryableFailed + terminalFailed + userActionRequired > 0
            ? "needs_attention"
            : ready > 0
              ? "ready"
              : cluster.status,
    batch_count: Math.max(cluster.batch_count, batches.length),
    work_item_count: Math.max(cluster.work_item_count, batches.length),
    ready_work_item_count: ready,
    leased_work_item_count: leased,
    completed_work_item_count: completed,
    retryable_failed_work_item_count: retryableFailed,
    terminal_failed_work_item_count: terminalFailed,
    user_action_required_work_item_count: userActionRequired,
  };
};

const compactionBatchFromPayload = (
  payload: Record<string, unknown>,
  key: "next_batch",
): WorkbenchClaimClusterBatchLiveState | null => {
  const value = payload[key];
  if (!isRecord(value)) return null;
  return value as unknown as WorkbenchClaimClusterBatchLiveState;
};


const liveCompactionBatchFromRecord = (
  record: Record<string, unknown>,
  status: string,
): WorkbenchClaimClusterBatchLiveState | null => {
  const workItemId =
    text(record, "work_item_id") ||
    text(record, "row_key");
  const batchRef =
    text(record, "batch_ref") ||
    text(record, "batch_id") ||
    workItemId;
  const groupRef =
    text(record, "group_ref") ||
    text(record, "cluster_ref");

  if (!batchRef || !workItemId || !groupRef) return null;

  const sourceClaimRefs =
    stringArray(record, "source_claim_refs").length > 0
      ? stringArray(record, "source_claim_refs")
      : stringArray(record, "input_claim_refs");

  const sourceNodeRefs =
    stringArray(record, "source_node_refs").length > 0
      ? stringArray(record, "source_node_refs")
      : stringArray(record, "input_node_refs");

  const rawClaimRefs =
    stringArray(record, "raw_claim_refs").length > 0
      ? stringArray(record, "raw_claim_refs")
      : sourceClaimRefs;

  const compactedNodeRefs = stringArray(record, "compacted_node_refs");
  const memberCount = Math.max(
    sourceClaimRefs.length,
    sourceNodeRefs.length,
    rawClaimRefs.length,
    compactedNodeRefs.length,
    intValue(record, "member_count") ?? 0,
  );

  return {
    batch_ref: batchRef,
    work_item_id: workItemId,
    group_ref: groupRef,
    status,
    prompt_variant:
      text(record, "prompt_variant") ||
      text(record, "next_work_type") ||
      text(record, "expected_output_kind") ||
      "draft_claim_compaction",
    model_id:
      text(record, "model_id") ||
      text(record, "model_ref") ||
      text(record, "active_model_ref") ||
      "unknown",
    artifact_tokens: intValue(record, "artifact_tokens") ?? 0,
    member_count: memberCount,
    source_claim_refs: sourceClaimRefs,
    source_node_refs: sourceNodeRefs,
    raw_claim_refs: rawClaimRefs,
    compacted_node_refs: compactedNodeRefs,
  };
};

const upsertCompactionBatchFromPayload = (
  response: WorkbenchWorkflowLiveStateResponse,
  payload: Record<string, unknown>,
  status: string,
): void => {
  const pendingWork = recordValue(payload, "pending_reduction_work");
  const source = pendingWork ? { ...pendingWork, ...payload } : payload;
  const batch = liveCompactionBatchFromRecord(source, status);
  if (batch) {
    upsertCompactionBatch(response, batch);
  }
};

const upsertPreparedCompactionRows = (
  response: WorkbenchWorkflowLiveStateResponse,
  payload: Record<string, unknown>,
): void => {
  const pendingRows = recordValue(payload, "pending_reduction_work_rows");
  const rows = [
    ...(pendingRows ? recordArray(pendingRows, "rows") : []),
    ...recordArray(payload, "dispatch_contexts"),
  ];

  for (const row of rows) {
    const batch = liveCompactionBatchFromRecord(row, "leased");
    if (batch) {
      upsertCompactionBatch(response, batch);
    }
  }
};

const upsertPreparedCompactionAttempts = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
): void => {
  const dispatchAttemptIds = stringArray(event.payload, "dispatch_attempt_ids");
  const workItemIds = stringArray(event.payload, "work_item_ids");

  dispatchAttemptIds.forEach((dispatchAttemptId, index) => {
    upsertAttempt(response, {
      dispatchAttemptId,
      sourceUnitRef: workItemIds[index] ?? null,
      status: "leased",
      startedAt: event.occurred_at,
      nodeName: DRAFT_CLAIM_COMPACTION_NODE_NAME,
    });
  });
};

const upsertCompactionAttempt = (
  response: WorkbenchWorkflowLiveStateResponse,
  event: FrontendWorkflowEventEnvelope,
  status: string,
): void => {
  const payload = isRecord(event.payload) ? event.payload : {};
  const attemptOutcome = recordValue(payload, "attempt_outcome") ?? {};
  const attemptScope = recordValue(attemptOutcome, "attempt_scope") ?? {};
  const providerOutcome = recordValue(attemptOutcome, "provider_outcome") ?? {};
  const validationOutcome = recordValue(attemptOutcome, "validation_outcome") ?? {};

  const dispatchAttemptId =
    text(payload, "dispatch_attempt_id") ||
    text(attemptScope, "dispatch_attempt_id");

  const workItemId =
    text(payload, "work_item_id") ||
    text(attemptScope, "work_item_id");

  const groupRef =
    text(payload, "group_ref") ||
    text(attemptScope, "group_ref");
  const batchRef =
    text(payload, "batch_ref") ||
    text(attemptScope, "batch_ref");
  const outcomeAttemptId = resolveCompactionOutcomeAttemptId(
    response,
    dispatchAttemptId,
    [workItemId, batchRef, groupRef],
  );
  if (!outcomeAttemptId) return;

  upsertAttempt(response, {
    dispatchAttemptId: outcomeAttemptId,
    sourceUnitRef: workItemId ?? batchRef ?? groupRef,
    status,
    provider: text(providerOutcome, "provider") ?? text(payload, "provider"),
    accountRef: text(providerOutcome, "account_ref") ?? text(payload, "account_ref"),
    modelRef: text(providerOutcome, "model_ref") ?? text(payload, "model_ref"),
    completedAt: event.occurred_at,
    promptTokens:
      intValue(providerOutcome, "prompt_tokens") ??
      intValue(payload, "actual_prompt_tokens"),
    completionTokens:
      intValue(providerOutcome, "completion_tokens") ??
      intValue(payload, "actual_completion_tokens"),
    totalTokens:
      intValue(providerOutcome, "total_tokens") ??
      intValue(payload, "actual_total_tokens"),
    errorKind:
      text(providerOutcome, "error_kind") ??
      text(validationOutcome, "validation_error") ??
      text(payload, "error_kind"),
    errorMessageUser:
      text(validationOutcome, "validation_decision") ??
      text(validationOutcome, "validation_error"),
    nodeName: DRAFT_CLAIM_COMPACTION_NODE_NAME,
  });
};


const compactedArtifactsFromPayload = (
  payload: Record<string, unknown>,
): WorkbenchCompactedClaimPreviewLiveState[] => {
  const value = payload.compacted_artifacts;
  if (!Array.isArray(value)) return [];

  return value
    .filter(isRecord)
    .map((artifact) => {
      const sourceClaimRefs = stringArray(artifact, "source_claim_refs");
      return {
        node_ref:
          text(artifact, "node_ref") ||
          text(artifact, "key") ||
          sourceClaimRefs.join(":") ||
          text(payload, "batch_ref") ||
          text(payload, "work_item_id") ||
          "compacted-artifact",
        claim: text(artifact, "claim") || "",
        claim_kind: text(artifact, "claim_kind"),
        granularity: text(artifact, "granularity"),
        merge_decision: text(artifact, "merge_decision"),
        source_claim_refs: sourceClaimRefs,
        active: true,
        compacted_payload:
          artifact as WorkbenchCompactedClaimPreviewLiveState["compacted_payload"],
      };
    })
    .filter((artifact) => artifact.claim.trim().length > 0);
};

const upsertCompactedArtifacts = (
  response: WorkbenchWorkflowLiveStateResponse,
  groupRef: string | null,
  artifacts: WorkbenchCompactedClaimPreviewLiveState[],
): void => {
  if (!groupRef || artifacts.length === 0) return;

  const clusters = response.workflow.claim_clusters ?? [];
  response.workflow.claim_clusters = clusters.map((cluster) => {
    if (cluster.group_ref !== groupRef && cluster.cluster_ref !== groupRef) return cluster;

    const existing = cluster.compacted_claims ?? [];
    const byRef = new Map(existing.map((claim) => [claim.node_ref, claim]));

    for (const artifact of artifacts) {
      byRef.set(artifact.node_ref, {
        ...byRef.get(artifact.node_ref),
        ...artifact,
      });
    }

    return {
      ...cluster,
      compacted_claims: Array.from(byRef.values()),
    };
  });
};

const upsertCompactionBatch = (
  response: WorkbenchWorkflowLiveStateResponse,
  batch: WorkbenchClaimClusterBatchLiveState,
): void => {
  const clusters = response.workflow.claim_clusters ?? [];
  response.workflow.claim_clusters = clusters.map((cluster) => {
    if (cluster.group_ref !== batch.group_ref && cluster.cluster_ref !== batch.group_ref) {
      return cluster;
    }

    const batches = cluster.batches ?? [];
    const existingIndex = batches.findIndex(
      (item) =>
        item.batch_ref === batch.batch_ref ||
        item.work_item_id === batch.work_item_id,
    );
    const nextBatches =
      existingIndex >= 0
        ? batches.map((item, index) =>
            index === existingIndex ? { ...item, ...batch } : item,
          )
        : [...batches, batch];

    return recomputeClusterBatchCounters({
      ...cluster,
      batches: nextBatches,
    });
  });
};

const updateCompactionBatch = (
  response: WorkbenchWorkflowLiveStateResponse,
  patch: {
    groupRef?: string | null;
    batchRef?: string | null;
    workItemId?: string | null;
    status: string;
  },
): void => {
  const clusters = response.workflow.claim_clusters ?? [];
  if (!patch.batchRef && !patch.workItemId) return;

  response.workflow.claim_clusters = clusters.map((cluster) => {
    if (patch.groupRef && cluster.group_ref !== patch.groupRef && cluster.cluster_ref !== patch.groupRef) {
      return cluster;
    }

    const batches = cluster.batches ?? [];
    let changed = false;
    const nextBatches = batches.map((batch) => {
      const sameBatch =
        (patch.batchRef ? batch.batch_ref === patch.batchRef : false) ||
        (patch.workItemId ? batch.work_item_id === patch.workItemId : false);
      if (!sameBatch) return batch;
      changed = true;
      return {
        ...batch,
        status: patch.status,
      };
    });

    return changed
      ? recomputeClusterBatchCounters({ ...cluster, batches: nextBatches })
      : cluster;
  });
};


const replaceClaimClusters = (
  response: WorkbenchWorkflowLiveStateResponse,
  clusters: WorkbenchClaimClusterLiveState[],
): void => {
  response.workflow.claim_clusters = clusters
    .slice()
    .sort((left, right) => left.cluster_ref.localeCompare(right.cluster_ref));
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

  if (normalizedEvent.canonical_phase) {
    next.workflow.current_phase = normalizedEvent.canonical_phase;
  }

  switch (normalizedEvent.projection_type) {
    case "workflow_source_document_persisted":
      markWorkflowRunning(next, normalizedEvent.occurred_at);
      next.document_status = "processing";
      next.workflow.current_phase = "source_ingestion";
      appendTimeline(next, normalizedEvent, "Документ сохранён и принят в обработку");
      break;
    case "workflow_manually_paused":
      markWorkflowPaused(next, normalizedEvent.occurred_at);
      appendTimeline(next, normalizedEvent, "Обработка поставлена на паузу");
      break;
    case "workflow_manually_resumed":
      markWorkflowRunning(next, normalizedEvent.occurred_at);
      appendTimeline(next, normalizedEvent, "Обработка возобновлена");
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
    case "workflow_draft_claim_embedding_batch_completed": {
      const requested = intValue(payload, "requested_embedding_count") ?? 0;
      const persisted = intValue(payload, "persisted_embedding_count") ?? 0;
      markStage(
        next,
        "draft_claim_embeddings",
        "running",
        normalizedEvent.occurred_at,
        persisted,
        Math.max(requested, persisted),
      );
      next.workflow.current_phase = "draft_claim_embeddings";
      appendTimeline(next, normalizedEvent, `Векторизация batch: ${persisted}/${Math.max(requested, persisted)}`);
      break;
    }

    case "workflow_draft_claim_embeddings_generated": {
      const requested = intValue(payload, "requested_embedding_count") ?? 0;
      const persisted = intValue(payload, "persisted_embedding_count") ?? 0;
      const total = Math.max(requested, persisted);
      markStage(next, "draft_claim_embeddings", "completed", normalizedEvent.occurred_at, total, total);
      markStage(next, "draft_claim_clustering", "running", normalizedEvent.occurred_at);
      next.workflow.current_phase = "draft_claim_clustering";
      appendTimeline(next, normalizedEvent, `Векторизация утверждений завершена: ${persisted}`);
      break;
    }

    case "workflow_draft_claim_clusters_built": {
      const clusters = claimClustersFromPayload(payload);
      const groupCount = intValue(payload, "group_count") ?? clusters.length;
      const batchCount = intValue(payload, "batch_count") ?? 0;

      if (clusters.length > 0) {
        replaceClaimClusters(next, clusters);
      }

      markStage(
        next,
        "draft_claim_clustering",
        "completed",
        normalizedEvent.occurred_at,
        groupCount,
        groupCount,
      );
      markStage(
        next,
        "draft_claim_compaction",
        batchCount > 0 ? "running" : "completed",
        normalizedEvent.occurred_at,
        0,
        batchCount,
      );

      next.workflow.current_phase = "draft_claim_compaction";
      appendTimeline(
        next,
        normalizedEvent,
        `Сформированы кластеры утверждений: ${groupCount}`,
      );
      break;
    }

    case "workflow_draft_claim_compaction_dispatch_batch_prepared": {
      upsertPreparedCompactionRows(next, payload);
      upsertPreparedCompactionAttempts(next, normalizedEvent);
      const workItemIds = stringArray(payload, "work_item_ids");
      workItemIds.forEach((workItemId) => {
        updateCompactionBatch(next, {
          workItemId,
          status: "leased",
        });
      });
      markStage(
        next,
        "draft_claim_compaction",
        "running",
        normalizedEvent.occurred_at,
      );
      next.workflow.current_phase = "draft_claim_compaction";
      appendTimeline(
        next,
        normalizedEvent,
        `Подготовлены batch work items compaction: ${workItemIds.length}`,
      );
      break;
    }

    case "workflow_draft_claim_compaction_attempt_completed": {
      upsertCompactionBatchFromPayload(next, payload, "completed");
      updateCompactionBatch(next, {
        groupRef: text(payload, "group_ref"),
        batchRef: text(payload, "batch_ref"),
        workItemId: text(payload, "work_item_id"),
        status: "completed",
      });
      upsertCompactionAttempt(next, normalizedEvent, "completed");
      markStage(next, "draft_claim_compaction", "running", normalizedEvent.occurred_at);
      next.workflow.current_phase = "draft_claim_compaction";
      appendTimeline(next, normalizedEvent, "Batch compaction завершён");
      break;
    }

    case "workflow_draft_claim_compaction_attempt_retryable_failed": {
      upsertCompactionBatchFromPayload(next, payload, "retryable_failed");
      updateCompactionBatch(next, {
        groupRef: text(payload, "group_ref"),
        batchRef: text(payload, "batch_ref"),
        workItemId: text(payload, "work_item_id"),
        status: "retryable_failed",
      });
      upsertCompactionAttempt(next, normalizedEvent, "retryable_failed");
      markStage(next, "draft_claim_compaction", "running", normalizedEvent.occurred_at);
      next.workflow.current_phase = "draft_claim_compaction";
      appendTimeline(next, normalizedEvent, "Batch compaction требует повторной обработки");
      break;
    }

    case "workflow_draft_claim_compaction_attempt_terminal_failed": {
      upsertCompactionBatchFromPayload(next, payload, "terminal_failed");
      updateCompactionBatch(next, {
        groupRef: text(payload, "group_ref"),
        batchRef: text(payload, "batch_ref"),
        workItemId: text(payload, "work_item_id"),
        status: "terminal_failed",
      });
      upsertCompactionAttempt(next, normalizedEvent, "terminal_failed");
      markStage(next, "draft_claim_compaction", "failed", normalizedEvent.occurred_at);
      next.workflow.current_phase = "draft_claim_compaction";
      appendTimeline(next, normalizedEvent, "Batch compaction завершился ошибкой");
      break;
    }

    case "workflow_draft_claim_compaction_result_applied": {
      upsertCompactedArtifacts(
        next,
        text(payload, "group_ref"),
        compactedArtifactsFromPayload(payload),
      );
      updateCompactionBatch(next, {
        groupRef: text(payload, "group_ref"),
        batchRef: text(payload, "batch_ref"),
        workItemId: text(payload, "work_item_id"),
        status: "completed",
      });
      markStage(next, "draft_claim_compaction", "running", normalizedEvent.occurred_at);
      next.workflow.current_phase = "draft_claim_compaction";
      appendTimeline(next, normalizedEvent, "Результат batch compaction применён");
      break;
    }

    case "workflow_draft_claim_compaction_next_work_scheduled": {
      const nextBatch =
        compactionBatchFromPayload(payload, "next_batch") ??
        liveCompactionBatchFromRecord(payload, "ready");
      if (nextBatch) {
        upsertCompactionBatch(next, nextBatch);
      }
      markStage(next, "draft_claim_compaction", "running", normalizedEvent.occurred_at);
      next.workflow.current_phase = "draft_claim_compaction";
      appendTimeline(next, normalizedEvent, "Запланирован следующий batch compaction");
      break;
    }

    case "workflow_draft_claim_compaction_cluster_done": {
      const groupRef = text(payload, "group_ref");
      next.workflow.claim_clusters = (next.workflow.claim_clusters ?? []).map((cluster) =>
        groupRef && (cluster.group_ref === groupRef || cluster.cluster_ref === groupRef)
          ? recomputeClusterBatchCounters({
              ...cluster,
              status: "compacted",
              batches: (cluster.batches ?? []).map((batch) => ({
                ...batch,
                status: "completed",
              })),
            })
          : cluster,
      );
      const completedClusters = (next.workflow.claim_clusters ?? []).filter(
        (cluster) => normalize(cluster.status) === "compacted",
      ).length;
      const totalClusters = next.workflow.claim_clusters?.length ?? 0;
      markStage(
        next,
        "draft_claim_compaction",
        totalClusters > 0 && completedClusters >= totalClusters ? "completed" : "running",
        normalizedEvent.occurred_at,
        completedClusters,
        totalClusters,
      );
      next.workflow.current_phase = "draft_claim_compaction";
      appendTimeline(next, normalizedEvent, "Кластер compaction завершён");
      break;
    }

    case "workflow_draft_claim_compaction_progress_reconciled": {
      const summary = recordValue(payload, "summary");
      const totalGroups =
        intValue(summary ?? {}, "total_group_count") ??
        intValue(summary ?? {}, "group_count") ??
        next.workflow.claim_clusters?.length ??
        0;
      const completedGroups =
        intValue(summary ?? {}, "done_group_count") ??
        intValue(summary ?? {}, "completed_group_count") ??
        0;
      markStage(
        next,
        "draft_claim_compaction",
        completedGroups > 0 && totalGroups > 0 && completedGroups >= totalGroups
          ? "completed"
          : "running",
        normalizedEvent.occurred_at,
        completedGroups,
        totalGroups,
      );
      next.workflow.current_phase = "draft_claim_compaction";
      appendTimeline(next, normalizedEvent, "Прогресс compaction сверён");
      break;
    }

    case "workflow_draft_claim_compaction_waiting_user_model_choice": {
      markStage(next, "draft_claim_compaction", "running", normalizedEvent.occurred_at);
      next.workflow.current_phase = "draft_claim_compaction";
      appendTimeline(next, normalizedEvent, "Compaction ожидает выбора модели");
      break;
    }


    case "workflow_draft_claim_compaction_all_groups_compacted": {
      next.workflow.claim_clusters = (next.workflow.claim_clusters ?? []).map((cluster) =>
        recomputeClusterBatchCounters({
          ...cluster,
          status: "compacted",
          batches: (cluster.batches ?? []).map((batch) => ({
            ...batch,
            status: "completed",
          })),
        }),
      );
      const totalClusters = next.workflow.claim_clusters?.length ?? 0;
      markStage(
        next,
        "draft_claim_compaction",
        "completed",
        normalizedEvent.occurred_at,
        totalClusters,
        totalClusters,
      );
      next.workflow.workflow_status = "waiting_for_review";
      next.document_status = "waiting_for_review";
      next.workflow.current_phase = "draft_claim_curation";
      next.workflow.curation = {
        ...next.workflow.curation,
        available: true,
        reason_code: "compaction_completed",
        workflow_run_id: normalizedEvent.workflow_run_id,
        workspace_ref: next.workflow.curation.workspace_ref ?? null,
        workspace_status: next.workflow.curation.workspace_status ?? "pending_open",
      };
      freezeWorkflowTimer(next, normalizedEvent.occurred_at, "stopped");
      hideActiveProcessingActions(next);
      setWorkflowActionState(next, "open_curation", {
        visible: true,
        enabled: true,
        reason_code: null,
      });
      appendTimeline(next, normalizedEvent, "Все кластеры compaction завершены");
      break;
    }

    case "workflow_draft_claim_curation_workspace_opened": {
      next.workflow.curation = {
        ...next.workflow.curation,
        available: true,
        reason_code: "workspace_opened",
        workflow_run_id: normalizedEvent.workflow_run_id,
        workspace_ref: text(payload, "workspace_ref"),
        workspace_status: "open",
        item_count: intValue(payload, "item_count") ?? 0,
      };
      next.workflow.workflow_status = "waiting_for_review";
      next.document_status = "waiting_for_review";
      markStage(next, "curation", "running", normalizedEvent.occurred_at);
      next.workflow.current_phase = "draft_claim_curation";
      freezeWorkflowTimer(next, normalizedEvent.occurred_at, "stopped");
      hideActiveProcessingActions(next);
      setWorkflowActionState(next, "open_curation", {
        visible: true,
        enabled: true,
        reason_code: null,
      });
      appendTimeline(next, normalizedEvent, "Открыто пространство проверки знаний");
      break;
    }

    case "workflow_draft_claim_curation_review_required": {
      next.workflow.curation = {
        ...next.workflow.curation,
        available: true,
        reason_code: "review_required",
        workflow_run_id: normalizedEvent.workflow_run_id,
        workspace_ref: text(payload, "workspace_ref"),
        workspace_status: "review_required",
        item_count: intValue(payload, "item_count") ?? next.workflow.curation.item_count,
      };
      next.workflow.workflow_status = "waiting_for_review";
      next.document_status = "waiting_for_review";
      markStage(next, "curation", "running", normalizedEvent.occurred_at);
      next.workflow.current_phase = "draft_claim_curation";
      freezeWorkflowTimer(next, normalizedEvent.occurred_at, "stopped");
      hideActiveProcessingActions(next);
      setWorkflowActionState(next, "open_curation", {
        visible: true,
        enabled: true,
        reason_code: null,
      });
      appendTimeline(next, normalizedEvent, "Требуется ручная проверка знаний");
      break;
    }

    case "workflow_draft_claim_curation_workspace_published": {
      markStage(next, "curation", "completed", normalizedEvent.occurred_at);
      markStage(
        next,
        "publication",
        "completed",
        normalizedEvent.occurred_at,
        intValue(payload, "published_item_count") ?? 0,
        intValue(payload, "published_item_count") ?? 0,
      );
      next.workflow.workflow_status = "completed";
      next.document_status = "completed";
      next.workflow.current_phase = "publication";
      freezeWorkflowTimer(next, normalizedEvent.occurred_at, "completed");
      hideActiveProcessingActions(next);
      setWorkflowActionState(next, "open_curation", {
        visible: true,
        enabled: false,
        reason_code: "published",
      });
      appendTimeline(next, normalizedEvent, "Проверенные знания опубликованы");
      break;
    }


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
