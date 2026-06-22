import { describe, expect, it } from 'vitest';

import type { FrontendWorkflowEventEnvelope } from '@shared/api/modules/knowledge';
import {
  createEmptyCompactionShadowState,
  reduceCompactionProjectionEvent,
} from './compactionProjectionShadowReducer';

const event = (
  projectionType: string,
  payload: Record<string, unknown>,
  projectionEventId = `${projectionType}:1`,
): FrontendWorkflowEventEnvelope => ({
  projection_event_id: projectionEventId,
  source_event_id: `source:${projectionEventId}`,
  source_sequence_number: 1,
  projection_version: 1,
  projection_type: projectionType,
  event_type: projectionType,
  operation_key: 'test',
  canonical_phase: 'DRAFT_CLAIM_CLUSTERING',
  workflow_run_id: 'workflow-1',
  project_id: 'project-1',
  document_id: 'document-1',
  payload,
  occurred_at: '2026-01-01T00:00:00Z',
  causation_command_id: null,
  correlation_id: null,
});

describe('DraftClaimCompaction projection shadow reducer', () => {
  it('ignores duplicate projection_event_id idempotently', () => {
    const first = reduceCompactionProjectionEvent(
      createEmptyCompactionShadowState(),
      event('workflow_draft_claim_compaction_next_work_scheduled', {
        workflow_run_id: 'workflow-1',
        group_ref: 'group-1',
      }),
    );
    const second = reduceCompactionProjectionEvent(
      first.state,
      event('workflow_draft_claim_compaction_next_work_scheduled', {
        workflow_run_id: 'workflow-1',
        group_ref: 'group-1',
      }),
    );

    expect(first.state.targetedReadRequests).toHaveLength(2);
    expect(second.targetedReadRequests).toHaveLength(0);
    expect(second.state.targetedReadRequests).toHaveLength(2);
  });

  it('appends retry attempts under the same pending work without overwriting history', () => {
    const first = reduceCompactionProjectionEvent(
      createEmptyCompactionShadowState(),
      event('workflow_draft_claim_compaction_attempt_retryable_failed', {
        workflow_run_id: 'workflow-1',
        work_item_id: 'work-1',
        dispatch_attempt_id: 'attempt-1',
        group_ref: 'group-1',
        batch_ref: 'batch-1',
        source_node_refs: ['node-1', 'node-2'],
      }),
    );
    const second = reduceCompactionProjectionEvent(
      first.state,
      event(
        'workflow_draft_claim_compaction_attempt_completed',
        {
          workflow_run_id: 'workflow-1',
          work_item_id: 'work-1',
          dispatch_attempt_id: 'attempt-2',
          group_ref: 'group-1',
          batch_ref: 'batch-1',
        },
        'workflow_draft_claim_compaction_attempt_completed:2',
      ),
    );

    expect(second.state.pendingReductionWork['work-1'].attemptIds).toEqual([
      'attempt-1',
      'attempt-2',
    ]);
    expect(second.state.attempts['attempt-1'].status).toBe('retryable_failed');
    expect(second.state.attempts['attempt-2'].status).toBe('completed');
  });

  it('does not duplicate repeated same attempt event', () => {
    const inputEvent = event('workflow_draft_claim_compaction_attempt_completed', {
      workflow_run_id: 'workflow-1',
      work_item_id: 'work-1',
      dispatch_attempt_id: 'attempt-1',
      group_ref: 'group-1',
      batch_ref: 'batch-1',
    });
    const first = reduceCompactionProjectionEvent(
      createEmptyCompactionShadowState(),
      inputEvent,
    );
    const second = reduceCompactionProjectionEvent(first.state, inputEvent);

    expect(second.state.pendingReductionWork['work-1'].attemptIds).toEqual([
      'attempt-1',
    ]);
    expect(Object.keys(second.state.attempts)).toEqual(['attempt-1']);
  });

  it('does not create generated frontier nodes from AttemptCompleted', () => {
    const result = reduceCompactionProjectionEvent(
      createEmptyCompactionShadowState(),
      event('workflow_draft_claim_compaction_attempt_completed', {
        workflow_run_id: 'workflow-1',
        work_item_id: 'work-1',
        dispatch_attempt_id: 'attempt-1',
        created_node_refs: ['node-generated'],
      }),
    );

    expect(result.state.frontierNodes).toEqual({});
  });

  it('marks generated nodes and enqueues node/frontier reads from ResultApplied', () => {
    const result = reduceCompactionProjectionEvent(
      createEmptyCompactionShadowState(),
      event('workflow_draft_claim_compaction_result_applied', {
        workflow_run_id: 'workflow-1',
        group_ref: 'group-1',
        work_item_id: 'work-1',
        created_node_refs: ['node-generated'],
      }),
    );

    expect(result.state.frontierNodes['node-generated'].generatedByResultApplied).toBe(
      true,
    );
    expect(result.state.targetedReadRequests).toEqual(
      expect.arrayContaining([
        {
          kind: 'draft_claim_compaction_nodes_by_workflow_or_group',
          workflowRunId: 'workflow-1',
          groupRef: 'group-1',
          activeOnly: false,
        },
        {
          kind: 'draft_claim_compaction_frontier_by_workflow_or_group',
          workflowRunId: 'workflow-1',
          groupRef: 'group-1',
        },
      ]),
    );
  });

  it('NextWorkScheduled requests pending/frontier reads and creates no ClusterBatch', () => {
    const result = reduceCompactionProjectionEvent(
      createEmptyCompactionShadowState(),
      event('workflow_draft_claim_compaction_next_work_scheduled', {
        workflow_run_id: 'workflow-1',
        group_ref: 'group-1',
      }),
    );

    expect(result.state.clusterBatches).toEqual({});
    expect(result.state.targetedReadRequests).toEqual(
      expect.arrayContaining([
        {
          kind: 'draft_claim_compaction_pending_work_by_workflow_or_group',
          workflowRunId: 'workflow-1',
          groupRef: 'group-1',
          workItemId: null,
        },
        {
          kind: 'draft_claim_compaction_frontier_by_workflow_or_group',
          workflowRunId: 'workflow-1',
          groupRef: 'group-1',
        },
      ]),
    );
  });

  it('updates capacity windows and links pending work through compaction_context', () => {
    const result = reduceCompactionProjectionEvent(
      createEmptyCompactionShadowState(),
      event('workflow_capacity_window_exhausted', {
        workflow_run_id: 'workflow-1',
        window_key: 'groq:acct:model:minute',
        provider: 'groq',
        account_ref: 'acct',
        model_ref: 'model',
        reset_at: '2026-01-01T00:01:00Z',
        compaction_context: {
          work_item_id: 'work-1',
          dispatch_attempt_id: 'attempt-1',
          group_ref: 'group-1',
          batch_ref: 'batch-1',
        },
      }),
    );

    expect(result.state.capacityWindows['groq:acct:model:minute'].linkedWorkItemIds).toEqual([
      'work-1',
    ]);
    expect(result.state.pendingReductionWork['work-1'].capacityWindowKey).toBe(
      'groq:acct:model:minute',
    );
    expect(result.state.attempts['attempt-1'].workItemId).toBe('work-1');
  });

  it('updates capacity window rows for observed/wakeup/leased events', () => {
    const observed = reduceCompactionProjectionEvent(
      createEmptyCompactionShadowState(),
      event('workflow_capacity_window_observed', {
        workflow_run_id: 'workflow-1',
        window_key: 'window-1',
        provider: 'groq',
        account_ref: 'acct',
        model_ref: 'model',
      }),
    );
    const wakeup = reduceCompactionProjectionEvent(
      observed.state,
      event(
        'workflow_capacity_window_scheduled_wakeup',
        {
          workflow_run_id: 'workflow-1',
          window_key: 'window-1',
          run_after: '2026-01-01T00:01:00Z',
        },
        'wakeup:1',
      ),
    );
    const leased = reduceCompactionProjectionEvent(
      wakeup.state,
      event(
        'workflow_capacity_window_leased_work_item',
        {
          workflow_run_id: 'workflow-1',
          window_key: 'window-1',
          work_item_id: 'work-1',
          dispatch_attempt_id: 'attempt-1',
        },
        'leased:1',
      ),
    );

    expect(leased.state.capacityWindows['window-1'].status).toBe(
      'workflow_capacity_window_leased_work_item',
    );
    expect(leased.state.capacityWindows['window-1'].linkedDispatchAttemptIds).toEqual([
      'attempt-1',
    ]);
  });

  it('records unknown projection types without throwing', () => {
    const result = reduceCompactionProjectionEvent(
      createEmptyCompactionShadowState(),
      event('workflow_unknown_projection', {}),
    );

    expect(result.state.unsupportedProjectionTypes.workflow_unknown_projection).toBe(1);
  });

  it('dedupes targeted read requests by stable key', () => {
    const result = reduceCompactionProjectionEvent(
      createEmptyCompactionShadowState(),
      event('workflow_draft_claim_compaction_result_applied', {
        workflow_run_id: 'workflow-1',
        group_ref: 'group-1',
        targeted_reads: [
          {
            kind: 'draft_claim_compaction_frontier_by_workflow_or_group',
            params: {
              workflow_run_id: 'workflow-1',
              group_ref: 'group-1',
            },
          },
          {
            kind: 'draft_claim_compaction_frontier_by_workflow_or_group',
            params: {
              workflow_run_id: 'workflow-1',
              group_ref: 'group-1',
            },
          },
        ],
      }),
    );

    const frontierReads = result.state.targetedReadRequests.filter(
      (request) =>
        request.kind === 'draft_claim_compaction_frontier_by_workflow_or_group',
    );
    expect(frontierReads).toHaveLength(1);
  });
});
