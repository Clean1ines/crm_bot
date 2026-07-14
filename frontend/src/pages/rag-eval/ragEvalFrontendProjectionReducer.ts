import type { FrontendWorkflowEventEnvelope } from '@shared/api/modules/knowledge';
import type { WorkbenchRagEvalVerificationMetrics } from '@shared/api/modules/ragEval';

export type RagEvalProjectionCounters = {
  scheduled: number;
  waiting: number;
  running: number;
  completed: number;
  failed: number;
  attempts: number;
};

export type RagEvalProjectionState = {
  run_id: string | null;
  status: string | null;
  phase: string | null;
  seen_projection_event_ids: string[];
  question_generation: RagEvalProjectionCounters;
  adjudication: RagEvalProjectionCounters;
  retrieval: {
    total: number;
    evaluated: number;
    pass_strong: number;
    pass_weak: number;
    confusion: number;
    miss: number;
    existing_alias_failure: number;
  };
  promotion: {
    candidates: number;
    approved: number;
    rejected: number;
    applied: number;
  };
  revisions: Record<string, string>;
  verification: {
    total_queries: number;
    completed_queries: number;
    failed_queries: number;
    decision: string | null;
    failure_reasons: string[];
    metrics: WorkbenchRagEvalVerificationMetrics | null;
  };
  timeline: Array<{
    projection_event_id: string;
    projection_type: string;
    occurred_at: string;
    status: string | null;
    phase: string | null;
  }>;
  invalidation_keys: string[][];
};

export const createInitialRagEvalProjectionState = (): RagEvalProjectionState => ({
  run_id: null,
  status: null,
  phase: null,
  seen_projection_event_ids: [],
  question_generation: emptyCounters(),
  adjudication: emptyCounters(),
  retrieval: {
    total: 0,
    evaluated: 0,
    pass_strong: 0,
    pass_weak: 0,
    confusion: 0,
    miss: 0,
    existing_alias_failure: 0,
  },
  promotion: {
    candidates: 0,
    approved: 0,
    rejected: 0,
    applied: 0,
  },
  revisions: {},
  verification: {
    total_queries: 0,
    completed_queries: 0,
    failed_queries: 0,
    decision: null,
    failure_reasons: [],
    metrics: null,
  },
  timeline: [],
  invalidation_keys: [],
});

export const ragEvalProjectionDocumentId = (
  projectId: string,
  runId: string,
  sourceDocumentRef?: string | null,
): string => {
  const source = sourceDocumentRef?.trim();
  return source || `rag-eval:${projectId}:${runId}`;
};

export const reduceRagEvalFrontendProjectionEvent = (
  state: RagEvalProjectionState,
  event: FrontendWorkflowEventEnvelope,
): RagEvalProjectionState => {
  if (state.seen_projection_event_ids.includes(event.projection_event_id)) {
    return state;
  }

  const payload = event.payload;
  const runId = text(payload, 'run_id') ?? text(payload, 'rag_eval_run_id') ?? event.workflow_run_id;
  const next: RagEvalProjectionState = {
    ...state,
    run_id: runId,
    status: text(payload, 'status') ?? state.status,
    phase: text(payload, 'phase') ?? event.canonical_phase ?? state.phase,
    seen_projection_event_ids: [
      ...state.seen_projection_event_ids,
      event.projection_event_id,
    ].slice(-250),
    invalidation_keys: invalidationKeysFor(event, runId),
    timeline: [
      {
        projection_event_id: event.projection_event_id,
        projection_type: event.projection_type,
        occurred_at: event.occurred_at,
        status: text(payload, 'status'),
        phase: text(payload, 'phase') ?? event.canonical_phase,
      },
      ...state.timeline,
    ].slice(0, 50),
  };

  if (event.projection_type.includes('question_generation')) {
    next.question_generation = reduceCounters(
      state.question_generation,
      event.projection_type,
      payload,
    );
  }
  if (event.projection_type.includes('adjudication')) {
    next.adjudication = reduceCounters(
      state.adjudication,
      event.projection_type,
      payload,
    );
  }
  if (event.projection_type === 'rag_eval_retrieval_evaluation_completed') {
    next.retrieval = {
      ...state.retrieval,
      total: numberValue(payload, 'total_count') ?? state.retrieval.total,
      evaluated: numberValue(payload, 'evaluated_count') ?? numberValue(payload, 'completed_questions') ?? state.retrieval.evaluated,
      pass_strong: classificationCount(payload, 'pass_strong', state.retrieval.pass_strong),
      pass_weak: classificationCount(payload, 'pass_weak', state.retrieval.pass_weak),
      confusion: classificationCount(payload, 'confusion', state.retrieval.confusion),
      miss: classificationCount(payload, 'miss', state.retrieval.miss),
      existing_alias_failure: classificationCount(
        payload,
        'existing_alias_retrieval_failure',
        state.retrieval.existing_alias_failure,
      ),
    };
  }
  if (event.projection_type === 'rag_eval_promotion_candidates_ready') {
    next.promotion = {
      ...state.promotion,
      candidates: numberValue(payload, 'candidate_count') ?? state.promotion.candidates,
    };
  }
  if (event.projection_type === 'rag_eval_promotions_applied') {
    const appliedCount =
      numberValue(payload, 'applied_count') ?? stringArray(payload, 'promotion_ids').length;
    next.promotion = {
      ...state.promotion,
      applied: appliedCount || state.promotion.applied,
    };
  }
  if (event.projection_type === 'rag_eval_embedding_revision_created') {
    const revisionId = text(payload, 'revision_id');
    if (revisionId) {
      next.revisions = { ...state.revisions, [revisionId]: text(payload, 'status') ?? 'pending_verification' };
    }
  }
  if (
    event.projection_type === 'rag_eval_verification_batch_completed' ||
    event.projection_type === 'rag_eval_verification_completed' ||
    event.projection_type === 'rag_eval_verification_regression_failed'
  ) {
    next.verification = {
      total_queries: numberValue(payload, 'query_count') ?? state.verification.total_queries,
      completed_queries: numberValue(payload, 'processed_count') ?? numberValue(payload, 'outcome_count') ?? state.verification.completed_queries,
      failed_queries: numberValue(payload, 'failed_count') ?? state.verification.failed_queries,
      decision: text(payload, 'decision') ?? state.verification.decision,
      failure_reasons: stringArray(payload, 'failure_reasons'),
      metrics: verificationMetricsValue(payload, 'metrics') ?? state.verification.metrics,
    };
  }
  if (
    event.projection_type === 'rag_eval_embedding_revision_accepted' ||
    event.projection_type === 'rag_eval_embedding_revision_rolled_back'
  ) {
    const revisionId = text(payload, 'revision_id');
    if (revisionId) {
      next.revisions = { ...state.revisions, [revisionId]: text(payload, 'status') ?? state.revisions[revisionId] ?? 'updated' };
    }
  }

  return next;
};

const emptyCounters = (): RagEvalProjectionCounters => ({
  scheduled: 0,
  waiting: 0,
  running: 0,
  completed: 0,
  failed: 0,
  attempts: 0,
});

const reduceCounters = (
  counters: RagEvalProjectionCounters,
  projectionType: string,
  payload: Record<string, unknown>,
): RagEvalProjectionCounters => {
  const next = { ...counters };
  if (projectionType.endsWith('work_item_scheduled')) next.scheduled += 1;
  if (projectionType.endsWith('dispatch_attempt_prepared')) {
    next.running += 1;
    next.attempts += 1;
  }
  if (projectionType.endsWith('attempt_completed')) {
    next.completed += 1;
    next.running = Math.max(0, next.running - 1);
  }
  if (projectionType.endsWith('progress_reconciled')) {
    next.waiting = numberValue(payload, 'waiting_count') ?? next.waiting;
    next.completed = numberValue(payload, 'completed_count') ?? next.completed;
    next.failed = numberValue(payload, 'failed_count') ?? next.failed;
  }
  return next;
};

const invalidationKeysFor = (
  event: FrontendWorkflowEventEnvelope,
  runId: string,
): string[][] => {
  const projectPrefix = ['workbench-rag-eval', event.project_id];
  const runPrefix = [...projectPrefix, 'runs', runId];
  const revisionId = text(event.payload, 'revision_id');
  const keys = [
    [...projectPrefix, 'latest'],
    runPrefix,
  ];
  if (event.projection_type.includes('question_generation') || event.projection_type.includes('retrieval')) {
    keys.push([...runPrefix, 'questions']);
  }
  if (event.projection_type.includes('promotion')) {
    keys.push([...runPrefix, 'promotion-candidates']);
  }
  if (event.projection_type.includes('revision') || event.projection_type.includes('verification')) {
    keys.push([...runPrefix, 'embedding-revisions']);
    keys.push([...runPrefix, 'post-promotion-verifications']);
  }
  if (revisionId) {
    keys.push([...projectPrefix, 'embedding-revisions', revisionId]);
    keys.push([...projectPrefix, 'embedding-revisions', revisionId, 'verification']);
  }
  return keys;
};

const text = (payload: Record<string, unknown>, key: string): string | null => {
  const value = payload[key];
  return typeof value === 'string' && value.trim() ? value.trim() : null;
};

const numberValue = (payload: Record<string, unknown>, key: string): number | null => {
  const value = payload[key];
  return typeof value === 'number' && Number.isFinite(value) ? Math.floor(value) : null;
};

const stringArray = (payload: Record<string, unknown>, key: string): string[] => {
  const value = payload[key];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : [];
};

const recordValue = (
  payload: Record<string, unknown>,
  key: string,
): Record<string, unknown> | null => {
  const value = payload[key];
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
};

const verificationMetricsValue = (
  payload: Record<string, unknown>,
  key: string,
): WorkbenchRagEvalVerificationMetrics | null => {
  const value = recordValue(payload, key);
  if (!value) return null;
  return ['overall', 'promoted', 'holdout', 'baseline', 'neighbour'].every(
    (role) => recordValue(value, role) !== null,
  )
    ? (value as unknown as WorkbenchRagEvalVerificationMetrics)
    : null;
};

const classificationCount = (
  payload: Record<string, unknown>,
  key: string,
  fallback: number,
): number => {
  const counts = recordValue(payload, 'classification_counts');
  if (!counts) return fallback;
  const value = counts[key];
  return typeof value === 'number' && Number.isFinite(value) ? Math.floor(value) : fallback;
};
