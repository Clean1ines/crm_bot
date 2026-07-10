import { describe, expect, it } from 'vitest';

import type { WorkbenchWorkflowLiveState } from '@shared/api/modules/knowledge';

import { selectClaimClustersView } from './claimClusterSelectors';

const workflow = (
  patch: Partial<WorkbenchWorkflowLiveState>,
): WorkbenchWorkflowLiveState => ({
  workflow_run_id: 'workflow-1',
  source_document_ref: 'document-1',
  workflow_status: 'RUNNING',
  current_phase: 'DRAFT_CLAIM_COMPACTION',
  timer: {
    mode: 'running',
    active_elapsed_seconds: 0,
    wall_elapsed_seconds: 0,
    is_live: false,
  },
  usage: {
    total_prompt_tokens: 0,
    total_completion_tokens: 0,
    total_tokens: 0,
    total_llm_calls: 0,
    model_summaries: [],
  },
  stages: [],
  section_lanes: [],
  timeline: [],
  curation: {
    available: false,
    reason_code: 'preview_not_ready',
    item_count: 0,
    excluded_item_count: 0,
  },
  actions: [],
  llm_attempts: [],
  ...patch,
});

describe('selectClaimClustersView', () => {
  it('links compaction attempts to batches by work item even when node name is legacy-shaped', () => {
    const view = selectClaimClustersView(
      workflow({
        claim_clusters: [
          {
            group_ref: 'cluster-1',
            cluster_ref: 'cluster-1',
            status: 'compacted',
            member_count: 1,
            candidate_edge_count: 0,
            batch_count: 1,
            node_count: 1,
            active_node_count: 1,
            active_compacted_node_count: 1,
            comparison_count: 1,
            pending_comparison_count: 0,
            work_item_count: 1,
            ready_work_item_count: 0,
            leased_work_item_count: 0,
            completed_work_item_count: 1,
            retryable_failed_work_item_count: 0,
            terminal_failed_work_item_count: 0,
            user_action_required_work_item_count: 0,
            batches: [
              {
                batch_ref: 'batch-1',
                work_item_id: 'work-1',
                group_ref: 'cluster-1',
                status: 'completed',
                prompt_variant: 'single_draft_claim_enrichment',
                model_id: 'qwen/qwen3-32b',
                artifact_tokens: 100,
                member_count: 1,
                source_claim_refs: ['claim-1'],
                source_node_refs: ['node-1'],
                raw_claim_refs: ['claim-1'],
                compacted_node_refs: ['node-2'],
              },
            ],
            members: [],
            claims: [],
            comparisons: [],
            compacted_claims: [],
          },
        ],
        llm_attempts: [
          {
            node_run_id: 'attempt-1',
            section_id: 'work-1',
            node_name: 'draft_claim_compaction',
            node_kind: 'llm',
            status: 'completed',
            started_at: '2026-07-09T21:00:00Z',
            completed_at: '2026-07-09T21:00:08Z',
            duration_ms: 8000,
            model_provider: 'groq',
            model_name: 'qwen/qwen3-32b',
            account_ref: 'groq_org_primary',
            prompt_tokens: 300,
            completion_tokens: 40,
            total_tokens: 340,
            error_kind: null,
            error_message_user: null,
            retry_plan: null,
            user_action_required: false,
            blocked_reason: null,
          },
        ],
      }),
    );

    expect(view.compaction.llmAttemptCount).toBe(1);
    expect(view.compaction.succeededAttemptCount).toBe(1);
    expect(view.compaction.tokens).toBe(340);
    expect(view.compaction.attempts[0]).toMatchObject({
      workItemId: 'work-1',
      status: 'completed',
      tokenCount: 340,
    });
  });

  it('keeps the compaction summary panel visually neutral when complete', () => {
    const view = selectClaimClustersView(
      workflow({
        curation: {
          available: true,
          reason_code: 'ready',
          item_count: 0,
          excluded_item_count: 0,
        },
        claim_clusters: [
          {
            group_ref: 'cluster-1',
            cluster_ref: 'cluster-1',
            status: 'compacted',
            member_count: 1,
            candidate_edge_count: 0,
            batch_count: 0,
            node_count: 1,
            active_node_count: 1,
            active_compacted_node_count: 1,
            comparison_count: 0,
            pending_comparison_count: 0,
            work_item_count: 0,
            ready_work_item_count: 0,
            leased_work_item_count: 0,
            completed_work_item_count: 1,
            retryable_failed_work_item_count: 0,
            terminal_failed_work_item_count: 0,
            user_action_required_work_item_count: 0,
            members: [],
            claims: [],
            comparisons: [],
            compacted_claims: [],
          },
        ],
      }),
    );

    expect(view.compaction.isComplete).toBe(true);
    expect(view.compaction.panelTone).toBe(
      'border-[var(--border-subtle)] bg-[var(--surface-secondary)]',
    );
  });
});
