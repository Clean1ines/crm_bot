import type { FrontendWorkflowEventEnvelope } from '@shared/api/modules/knowledge';

type JsonRecord = Record<string, unknown>;

export type CompactionTargetedReadRequest =
  | {
      kind: 'draft_claim_clusters_by_workflow';
      workflowRunId: string;
    }
  | {
      kind: 'draft_claim_compaction_frontier_by_workflow_or_group';
      workflowRunId: string;
      groupRef: string | null;
    }
  | {
      kind: 'draft_claim_compaction_nodes_by_workflow_or_group';
      workflowRunId: string;
      groupRef: string | null;
      activeOnly: boolean | null;
    }
  | {
      kind: 'draft_claim_compaction_pending_work_by_workflow_or_group';
      workflowRunId: string;
      groupRef: string | null;
      workItemId: string | null;
    };

export type CompactionClusterGroupShadow = {
  groupRef: string;
  workflowRunId: string | null;
  status: string;
  dirty: boolean;
};

export type CompactionClusterBatchShadow = {
  batchRef: string;
  groupRef: string | null;
  workflowRunId: string | null;
  initialSurfaceOnly: true;
};

export type CompactionFrontierNodeShadow = {
  nodeRef: string;
  workflowRunId: string | null;
  groupRef: string | null;
  active: boolean | null;
  generatedByResultApplied: boolean;
  dirty: boolean;
};

export type CompactionPendingReductionWorkShadow = {
  workItemId: string;
  workflowRunId: string | null;
  groupRef: string | null;
  batchRef: string | null;
  inputNodeRefs: string[];
  inputClaimRefs: string[];
  status: string;
  attemptIds: string[];
  capacityWindowKey: string | null;
  diagnostics: string[];
};

export type CompactionAttemptShadow = {
  dispatchAttemptId: string;
  workItemId: string | null;
  workflowRunId: string | null;
  groupRef: string | null;
  batchRef: string | null;
  status: string;
  providerOutcome: JsonRecord | null;
  validationOutcome: JsonRecord | null;
  workItemOutcome: JsonRecord | null;
};

export type CapacityWindowShadow = {
  windowKey: string;
  workflowRunId: string | null;
  provider: string | null;
  accountRef: string | null;
  modelRef: string | null;
  status: string;
  resetAt: string | null;
  linkedWorkItemIds: string[];
  linkedDispatchAttemptIds: string[];
};

export type CompactionShadowState = {
  appliedProjectionEventIds: Record<string, true>;
  clusterGroups: Record<string, CompactionClusterGroupShadow>;
  clusterBatches: Record<string, CompactionClusterBatchShadow>;
  frontierNodes: Record<string, CompactionFrontierNodeShadow>;
  pendingReductionWork: Record<string, CompactionPendingReductionWorkShadow>;
  attempts: Record<string, CompactionAttemptShadow>;
  capacityWindows: Record<string, CapacityWindowShadow>;
  targetedReadRequests: CompactionTargetedReadRequest[];
  unsupportedProjectionTypes: Record<string, number>;
  workflowCompactionComplete: Record<string, true>;
};

export type CompactionShadowReduceResult = {
  state: CompactionShadowState;
  targetedReadRequests: CompactionTargetedReadRequest[];
};

export function createEmptyCompactionShadowState(): CompactionShadowState {
  return {
    appliedProjectionEventIds: {},
    clusterGroups: {},
    clusterBatches: {},
    frontierNodes: {},
    pendingReductionWork: {},
    attempts: {},
    capacityWindows: {},
    targetedReadRequests: [],
    unsupportedProjectionTypes: {},
    workflowCompactionComplete: {},
  };
}

export function reduceCompactionProjectionEvent(
  state: CompactionShadowState,
  event: FrontendWorkflowEventEnvelope,
): CompactionShadowReduceResult {
  if (state.appliedProjectionEventIds[event.projection_event_id]) {
    return { state, targetedReadRequests: [] };
  }

  const next = cloneState(state);
  next.appliedProjectionEventIds[event.projection_event_id] = true;
  const beforeRequestCount = next.targetedReadRequests.length;
  const payload = asRecord(event.payload);

  switch (event.projection_type) {
    case 'workflow_draft_claim_clusters_built':
      applyClustersBuilt(next, event, payload);
      break;
    case 'workflow_draft_claim_compaction_dispatch_batch_prepared':
      applyDispatchPrepared(next, event, payload);
      break;
    case 'workflow_draft_claim_compaction_attempt_completed':
      applyAttemptOutcome(next, event, payload, 'completed');
      break;
    case 'workflow_draft_claim_compaction_attempt_retryable_failed':
      applyAttemptOutcome(next, event, payload, 'retryable_failed');
      break;
    case 'workflow_draft_claim_compaction_attempt_terminal_failed':
      applyAttemptOutcome(next, event, payload, 'terminal_failed');
      break;
    case 'workflow_draft_claim_compaction_result_applied':
      applyResultApplied(next, event, payload);
      break;
    case 'workflow_draft_claim_compaction_next_work_scheduled':
      applyNextWorkScheduled(next, event, payload);
      break;
    case 'workflow_draft_claim_compaction_cluster_done':
      applyClusterDone(next, event, payload);
      break;
    case 'workflow_draft_claim_compaction_all_groups_compacted':
      next.workflowCompactionComplete[event.workflow_run_id] = true;
      break;
    case 'workflow_capacity_window_observed':
    case 'workflow_capacity_window_exhausted':
    case 'workflow_capacity_window_scheduled_wakeup':
    case 'workflow_capacity_window_leased_work_item':
      applyCapacityWindowEvent(next, event, payload);
      break;
    default:
      next.unsupportedProjectionTypes[event.projection_type] =
        (next.unsupportedProjectionTypes[event.projection_type] ?? 0) + 1;
      break;
  }

  return {
    state: next,
    targetedReadRequests: next.targetedReadRequests.slice(beforeRequestCount),
  };
}

function applyClustersBuilt(
  state: CompactionShadowState,
  event: FrontendWorkflowEventEnvelope,
  payload: JsonRecord,
): void {
  const workflowRunId = text(payload.workflow_run_id) ?? event.workflow_run_id;
  enqueueTargetedRead(state, {
    kind: 'draft_claim_clusters_by_workflow',
    workflowRunId,
  });
}

function applyDispatchPrepared(
  state: CompactionShadowState,
  event: FrontendWorkflowEventEnvelope,
  payload: JsonRecord,
): void {
  const workflowRunId = text(payload.workflow_run_id) ?? event.workflow_run_id;
  const rows = mappingList(asRecord(payload.pending_reduction_work_rows).rows);
  const workItemIds = textList(payload.work_item_ids);
  const dispatchAttemptIds = textList(payload.dispatch_attempt_ids);

  if (rows.length > 0) {
    for (const row of rows) {
      const workItemId = text(row.work_item_id);
      const dispatchAttemptId = text(row.dispatch_attempt_id);
      if (workItemId) {
        const pending = upsertPendingWork(state, workItemId, workflowRunId);
        mergePendingWork(pending, row);
        pending.status = pending.status === 'unknown' ? 'prepared' : pending.status;
      }
      if (dispatchAttemptId) {
        upsertAttempt(state, dispatchAttemptId, {
          workItemId: workItemId ?? null,
          workflowRunId,
          groupRef: text(row.group_ref),
          batchRef: text(row.batch_ref),
          status: 'prepared',
        });
      }
      if (workItemId && dispatchAttemptId) {
        appendAttemptIdToPendingWork(state, workItemId, dispatchAttemptId);
      }
    }
  } else {
    workItemIds.forEach((workItemId, index) => {
      const pending = upsertPendingWork(state, workItemId, workflowRunId);
      pending.status = pending.status === 'unknown' ? 'prepared' : pending.status;
      const dispatchAttemptId = dispatchAttemptIds[index];
      if (dispatchAttemptId) {
        upsertAttempt(state, dispatchAttemptId, {
          workItemId,
          workflowRunId,
          groupRef: null,
          batchRef: null,
          status: 'prepared',
        });
        appendAttemptIdToPendingWork(state, workItemId, dispatchAttemptId);
      }
    });
  }

  enqueueTargetedReadsFromPayload(state, payload);
}

function applyAttemptOutcome(
  state: CompactionShadowState,
  event: FrontendWorkflowEventEnvelope,
  payload: JsonRecord,
  status: string,
): void {
  const workflowRunId = text(payload.workflow_run_id) ?? event.workflow_run_id;
  const workItemId = text(payload.work_item_id);
  const dispatchAttemptId = text(payload.dispatch_attempt_id);
  const attemptOutcome = asRecord(payload.attempt_outcome);
  const attemptScope = asRecord(attemptOutcome.attempt_scope);
  const groupRef = text(payload.group_ref) ?? text(attemptScope.group_ref);
  const batchRef = text(payload.batch_ref) ?? text(attemptScope.batch_ref);

  if (workItemId) {
    const pending = upsertPendingWork(state, workItemId, workflowRunId);
    pending.groupRef = groupRef ?? pending.groupRef;
    pending.batchRef = batchRef ?? pending.batchRef;
    pending.status = status;
    mergePendingWork(pending, payload);
  }

  if (dispatchAttemptId) {
    upsertAttempt(state, dispatchAttemptId, {
      workItemId: workItemId ?? text(attemptScope.work_item_id),
      workflowRunId,
      groupRef,
      batchRef,
      status,
      providerOutcome: asNullableRecord(attemptOutcome.provider_outcome),
      validationOutcome: asNullableRecord(attemptOutcome.validation_outcome),
      workItemOutcome: asNullableRecord(attemptOutcome.work_item_outcome),
    });

    if (workItemId) {
      appendAttemptIdToPendingWork(state, workItemId, dispatchAttemptId);
    }
  }
}

function applyResultApplied(
  state: CompactionShadowState,
  event: FrontendWorkflowEventEnvelope,
  payload: JsonRecord,
): void {
  const workflowRunId = text(payload.workflow_run_id) ?? event.workflow_run_id;
  const groupRef = text(payload.group_ref);
  const workItemId = text(payload.work_item_id);
  const createdNodeRefs = textList(payload.created_node_refs);

  if (workItemId) {
    const pending = upsertPendingWork(state, workItemId, workflowRunId);
    pending.groupRef = groupRef ?? pending.groupRef;
    pending.status = 'result_applied';
  }

  for (const nodeRef of createdNodeRefs) {
    state.frontierNodes[nodeRef] = {
      nodeRef,
      workflowRunId,
      groupRef,
      active: null,
      generatedByResultApplied: true,
      dirty: true,
    };
  }

  enqueueTargetedReadsFromPayload(state, payload);
  enqueueTargetedRead(state, {
    kind: 'draft_claim_compaction_nodes_by_workflow_or_group',
    workflowRunId,
    groupRef,
    activeOnly: false,
  });
  enqueueTargetedRead(state, {
    kind: 'draft_claim_compaction_frontier_by_workflow_or_group',
    workflowRunId,
    groupRef,
  });
}

function applyNextWorkScheduled(
  state: CompactionShadowState,
  event: FrontendWorkflowEventEnvelope,
  payload: JsonRecord,
): void {
  const workflowRunId = text(payload.workflow_run_id) ?? event.workflow_run_id;
  const groupRef = text(payload.group_ref);

  enqueueTargetedReadsFromPayload(state, payload);
  enqueueTargetedRead(state, {
    kind: 'draft_claim_compaction_pending_work_by_workflow_or_group',
    workflowRunId,
    groupRef,
    workItemId: null,
  });
  enqueueTargetedRead(state, {
    kind: 'draft_claim_compaction_frontier_by_workflow_or_group',
    workflowRunId,
    groupRef,
  });
}

function applyClusterDone(
  state: CompactionShadowState,
  event: FrontendWorkflowEventEnvelope,
  payload: JsonRecord,
): void {
  const workflowRunId = text(payload.workflow_run_id) ?? event.workflow_run_id;
  const groupRef = text(payload.group_ref);
  if (!groupRef) return;

  state.clusterGroups[groupRef] = {
    groupRef,
    workflowRunId,
    status: 'completed',
    dirty: false,
  };
}

function applyCapacityWindowEvent(
  state: CompactionShadowState,
  event: FrontendWorkflowEventEnvelope,
  payload: JsonRecord,
): void {
  const workflowRunId = text(payload.workflow_run_id) ?? event.workflow_run_id;
  const windowKey = text(payload.window_key);
  if (!windowKey) return;

  const context = asRecord(payload.compaction_context);
  const linkedPending = asRecord(payload.linked_pending_reduction_work);
  const workItemId =
    text(context.work_item_id) ??
    text(linkedPending.work_item_id) ??
    text(payload.work_item_id);
  const dispatchAttemptId =
    text(context.dispatch_attempt_id) ??
    text(linkedPending.dispatch_attempt_id) ??
    text(payload.dispatch_attempt_id);

  const capacityWindow = state.capacityWindows[windowKey] ?? {
    windowKey,
    workflowRunId,
    provider: null,
    accountRef: null,
    modelRef: null,
    status: event.projection_type,
    resetAt: null,
    linkedWorkItemIds: [],
    linkedDispatchAttemptIds: [],
  };

  capacityWindow.provider = text(payload.provider) ?? capacityWindow.provider;
  capacityWindow.accountRef = text(payload.account_ref) ?? capacityWindow.accountRef;
  capacityWindow.modelRef = text(payload.model_ref) ?? capacityWindow.modelRef;
  capacityWindow.resetAt =
    text(payload.reset_at) ?? text(payload.run_after) ?? capacityWindow.resetAt;
  capacityWindow.status = event.projection_type;

  if (workItemId && !capacityWindow.linkedWorkItemIds.includes(workItemId)) {
    capacityWindow.linkedWorkItemIds.push(workItemId);
  }
  if (
    dispatchAttemptId &&
    !capacityWindow.linkedDispatchAttemptIds.includes(dispatchAttemptId)
  ) {
    capacityWindow.linkedDispatchAttemptIds.push(dispatchAttemptId);
  }

  state.capacityWindows[windowKey] = capacityWindow;

  if (workItemId) {
    const pending = upsertPendingWork(state, workItemId, workflowRunId);
    pending.capacityWindowKey = windowKey;
    pending.groupRef = text(context.group_ref) ?? pending.groupRef;
    pending.batchRef = text(context.batch_ref) ?? pending.batchRef;
    if (event.projection_type === 'workflow_capacity_window_leased_work_item') {
      pending.status = 'leased';
    } else if (event.projection_type === 'workflow_capacity_window_exhausted') {
      pending.status = 'waiting_for_capacity';
    }
  }

  if (dispatchAttemptId) {
    upsertAttempt(state, dispatchAttemptId, {
      workItemId: workItemId ?? null,
      workflowRunId,
      groupRef: text(context.group_ref),
      batchRef: text(context.batch_ref),
      status: event.projection_type,
    });
    if (workItemId) {
      appendAttemptIdToPendingWork(state, workItemId, dispatchAttemptId);
    }
  }
}

function cloneState(state: CompactionShadowState): CompactionShadowState {
  return {
    appliedProjectionEventIds: { ...state.appliedProjectionEventIds },
    clusterGroups: cloneRecord(state.clusterGroups),
    clusterBatches: cloneRecord(state.clusterBatches),
    frontierNodes: cloneRecord(state.frontierNodes),
    pendingReductionWork: Object.fromEntries(
      Object.entries(state.pendingReductionWork).map(([key, value]) => [
        key,
        {
          ...value,
          inputNodeRefs: [...value.inputNodeRefs],
          inputClaimRefs: [...value.inputClaimRefs],
          attemptIds: [...value.attemptIds],
          diagnostics: [...value.diagnostics],
        },
      ]),
    ),
    attempts: cloneRecord(state.attempts),
    capacityWindows: Object.fromEntries(
      Object.entries(state.capacityWindows).map(([key, value]) => [
        key,
        {
          ...value,
          linkedWorkItemIds: [...value.linkedWorkItemIds],
          linkedDispatchAttemptIds: [...value.linkedDispatchAttemptIds],
        },
      ]),
    ),
    targetedReadRequests: [...state.targetedReadRequests],
    unsupportedProjectionTypes: { ...state.unsupportedProjectionTypes },
    workflowCompactionComplete: { ...state.workflowCompactionComplete },
  };
}

function cloneRecord<T extends object>(record: Record<string, T>): Record<string, T> {
  return Object.fromEntries(
    Object.entries(record).map(([key, value]) => [key, { ...value }]),
  );
}

function upsertPendingWork(
  state: CompactionShadowState,
  workItemId: string,
  workflowRunId: string | null,
): CompactionPendingReductionWorkShadow {
  const existing = state.pendingReductionWork[workItemId];
  if (existing) return existing;

  const pending: CompactionPendingReductionWorkShadow = {
    workItemId,
    workflowRunId,
    groupRef: null,
    batchRef: null,
    inputNodeRefs: [],
    inputClaimRefs: [],
    status: 'unknown',
    attemptIds: [],
    capacityWindowKey: null,
    diagnostics: [],
  };
  state.pendingReductionWork[workItemId] = pending;
  return pending;
}

function mergePendingWork(
  pending: CompactionPendingReductionWorkShadow,
  payload: JsonRecord,
): void {
  pending.groupRef = text(payload.group_ref) ?? pending.groupRef;
  pending.batchRef = text(payload.batch_ref) ?? pending.batchRef;

  const inputNodeRefs =
    textList(payload.input_node_refs).length > 0
      ? textList(payload.input_node_refs)
      : firstNonEmptyTextList(payload, [
          'source_node_refs',
          'compared_node_refs',
          'node_refs',
        ]);
  const inputClaimRefs =
    textList(payload.input_claim_refs).length > 0
      ? textList(payload.input_claim_refs)
      : textList(payload.source_claim_refs);

  if (inputNodeRefs.length > 0) {
    pending.inputNodeRefs = dedupe([...pending.inputNodeRefs, ...inputNodeRefs]);
  }
  if (inputClaimRefs.length > 0) {
    pending.inputClaimRefs = dedupe([...pending.inputClaimRefs, ...inputClaimRefs]);
  }
}

function upsertAttempt(
  state: CompactionShadowState,
  dispatchAttemptId: string,
  values: {
    workItemId: string | null;
    workflowRunId: string | null;
    groupRef: string | null;
    batchRef: string | null;
    status: string;
    providerOutcome?: JsonRecord | null;
    validationOutcome?: JsonRecord | null;
    workItemOutcome?: JsonRecord | null;
  },
): CompactionAttemptShadow {
  const existing = state.attempts[dispatchAttemptId] ?? {
    dispatchAttemptId,
    workItemId: null,
    workflowRunId: null,
    groupRef: null,
    batchRef: null,
    status: 'unknown',
    providerOutcome: null,
    validationOutcome: null,
    workItemOutcome: null,
  };

  state.attempts[dispatchAttemptId] = {
    ...existing,
    workItemId: values.workItemId ?? existing.workItemId,
    workflowRunId: values.workflowRunId ?? existing.workflowRunId,
    groupRef: values.groupRef ?? existing.groupRef,
    batchRef: values.batchRef ?? existing.batchRef,
    status: values.status,
    providerOutcome: values.providerOutcome ?? existing.providerOutcome,
    validationOutcome: values.validationOutcome ?? existing.validationOutcome,
    workItemOutcome: values.workItemOutcome ?? existing.workItemOutcome,
  };
  return state.attempts[dispatchAttemptId];
}

function appendAttemptIdToPendingWork(
  state: CompactionShadowState,
  workItemId: string,
  dispatchAttemptId: string,
): void {
  const pending = upsertPendingWork(state, workItemId, null);
  if (!pending.attemptIds.includes(dispatchAttemptId)) {
    pending.attemptIds.push(dispatchAttemptId);
  }
}

function enqueueTargetedReadsFromPayload(
  state: CompactionShadowState,
  payload: JsonRecord,
): void {
  const reads = [
    ...mappingList(payload.targeted_reads),
    asRecord(payload.targeted_read),
    asRecord(asRecord(payload.next_compaction_work).targeted_read),
    ...mappingList(asRecord(payload.next_compaction_work).targeted_reads),
    asRecord(asRecord(payload.frontier_update).targeted_read),
  ];

  for (const read of reads) {
    const converted = targetedReadFromBackendPayload(read);
    if (converted) {
      enqueueTargetedRead(state, converted);
    }
  }
}

function targetedReadFromBackendPayload(
  payload: JsonRecord,
): CompactionTargetedReadRequest | null {
  const kind = text(payload.kind);
  const params = asRecord(payload.params);
  const workflowRunId = text(params.workflow_run_id);
  if (!kind || !workflowRunId) return null;

  if (kind === 'draft_claim_clusters_by_workflow') {
    return { kind, workflowRunId };
  }
  if (kind === 'draft_claim_compaction_frontier_by_workflow_or_group') {
    return {
      kind,
      workflowRunId,
      groupRef: text(params.group_ref),
    };
  }
  if (kind === 'draft_claim_compaction_nodes_by_workflow_or_group') {
    return {
      kind,
      workflowRunId,
      groupRef: text(params.group_ref),
      activeOnly: booleanValue(params.active_only),
    };
  }
  if (kind === 'draft_claim_compaction_pending_work_by_workflow_or_group') {
    return {
      kind,
      workflowRunId,
      groupRef: text(params.group_ref),
      workItemId: text(params.work_item_id),
    };
  }
  return null;
}

function enqueueTargetedRead(
  state: CompactionShadowState,
  request: CompactionTargetedReadRequest,
): void {
  const key = targetedReadKey(request);
  if (state.targetedReadRequests.some((existing) => targetedReadKey(existing) === key)) {
    return;
  }
  state.targetedReadRequests.push(request);
}

function targetedReadKey(request: CompactionTargetedReadRequest): string {
  if (request.kind === 'draft_claim_clusters_by_workflow') {
    return `${request.kind}:${request.workflowRunId}`;
  }
  if (request.kind === 'draft_claim_compaction_nodes_by_workflow_or_group') {
    return `${request.kind}:${request.workflowRunId}:${request.groupRef ?? ''}:${String(
      request.activeOnly,
    )}`;
  }
  if (request.kind === 'draft_claim_compaction_pending_work_by_workflow_or_group') {
    return `${request.kind}:${request.workflowRunId}:${request.groupRef ?? ''}:${
      request.workItemId ?? ''
    }`;
  }
  return `${request.kind}:${request.workflowRunId}:${request.groupRef ?? ''}`;
}

function asRecord(value: unknown): JsonRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return {};
  }
  return value as JsonRecord;
}

function asNullableRecord(value: unknown): JsonRecord | null {
  const record = asRecord(value);
  return Object.keys(record).length > 0 ? record : null;
}

function mappingList(value: unknown): JsonRecord[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is JsonRecord => {
      return typeof item === 'object' && item !== null && !Array.isArray(item);
    })
    .map((item) => item);
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value : null;
}

function textList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => {
    return typeof item === 'string' && item.trim().length > 0;
  });
}

function firstNonEmptyTextList(payload: JsonRecord, keys: string[]): string[] {
  for (const key of keys) {
    const values = textList(payload[key]);
    if (values.length > 0) return values;
  }
  return [];
}

function booleanValue(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function dedupe(values: string[]): string[] {
  return Array.from(new Set(values));
}
