import { describe, expect, it } from 'vitest';

import type { FrontendWorkflowEventEnvelope } from '@shared/api/modules/knowledge';

import {
  createInitialRagEvalProjectionState,
  ragEvalProjectionDocumentId,
  reduceRagEvalFrontendProjectionEvent,
} from './ragEvalFrontendProjectionReducer';

const event = (
  projectionType: string,
  payload: Record<string, unknown>,
  sequence = 1,
): FrontendWorkflowEventEnvelope => ({
  projection_event_id: `projection-${sequence}`,
  source_event_id: `source-${sequence}`,
  source_sequence_number: sequence,
  projection_version: 1,
  projection_type: projectionType,
  event_type: projectionType,
  operation_key: null,
  canonical_phase: 'POST_PROMOTION_VERIFICATION',
  workflow_run_id: 'run-1',
  project_id: 'project-1',
  document_id: 'rag-eval:project-1:run-1',
  payload,
  occurred_at: `2026-07-14T12:0${sequence}:00.000Z`,
  causation_command_id: null,
  correlation_id: null,
});

describe('ragEvalFrontendProjectionReducer', () => {
  it('deduplicates by projection event id', () => {
    const initial = createInitialRagEvalProjectionState();
    const scheduled = event('rag_eval_question_generation_work_item_scheduled', {
      run_id: 'run-1',
      project_id: 'project-1',
    });

    const once = reduceRagEvalFrontendProjectionEvent(initial, scheduled);
    const twice = reduceRagEvalFrontendProjectionEvent(once, scheduled);

    expect(twice.question_generation.scheduled).toBe(1);
    expect(twice.seen_projection_event_ids).toEqual(['projection-1']);
  });

  it('tracks verification progress and invalidates verification read models', () => {
    const next = reduceRagEvalFrontendProjectionEvent(
      createInitialRagEvalProjectionState(),
      event('rag_eval_verification_completed', {
        run_id: 'run-1',
        project_id: 'project-1',
        revision_id: 'revision-1',
        status: 'completed',
        processed_count: 7,
        failed_count: 0,
        decision: 'acceptable',
        failure_reasons: [],
        metrics: {
          overall: { query_count: 7 },
          promoted: {},
          holdout: {},
          baseline: {},
          neighbour: {},
        },
      }),
    );

    expect(next.verification.completed_queries).toBe(7);
    expect(next.verification.decision).toBe('acceptable');
    expect(next.invalidation_keys).toContainEqual([
      'workbench-rag-eval',
      'project-1',
      'runs',
      'run-1',
      'post-promotion-verifications',
    ]);
    expect(next.invalidation_keys).toContainEqual([
      'workbench-rag-eval',
      'project-1',
      'embedding-revisions',
      'revision-1',
      'verification',
    ]);
  });

  it('computes the synthetic document id used by the shared workflow event stream', () => {
    expect(ragEvalProjectionDocumentId('project-1', 'run-1', null)).toBe(
      'rag-eval:project-1:run-1',
    );
    expect(ragEvalProjectionDocumentId('project-1', 'run-1', 'source-document:1')).toBe(
      'source-document:1',
    );
  });
});
