import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import type { WorkbenchWorkflowLiveStateResponse } from '@shared/api/modules/knowledge';

import { KnowledgeDocumentCard } from './KnowledgeDocumentCard';

const workflowProjectionState: WorkbenchWorkflowLiveStateResponse = {
  document_id: 'document-1',
  project_id: 'project-1',
  file_name: 'knowledge.md',
  document_status: 'processing',
  current_processing_run_id: 'run-1',
  workflow: {
    workflow_run_id: 'workflow-1',
    source_document_ref: 'document-1',
    workflow_status: 'RUNNING',
    current_phase: 'DRAFT_CLUSTERS_BUILT',
    timer: {
      mode: 'running',
      active_elapsed_seconds: 12,
      wall_elapsed_seconds: 12,
      is_live: false,
    },
    usage: {
      total_prompt_tokens: 0,
      total_completion_tokens: 0,
      total_tokens: 0,
      total_llm_calls: 0,
      model_summaries: [],
    },
    stages: [
      {
        id: 'draft_claim_embeddings',
        label: 'Embeddings',
        status: 'completed',
        current: 99,
        total: 99,
        message: '',
      },
      {
        id: 'draft_claim_clustering',
        label: 'Clusters',
        status: 'completed',
        current: 99,
        total: 99,
        message: '',
      },
      {
        id: 'draft_claim_compaction',
        label: 'Compaction',
        status: 'running',
        current: 99,
        total: 99,
        message: '',
      },
    ],
    section_lanes: [],
    llm_attempts: [],
    timeline: [],
    claim_clusters: [
      {
        group_ref: 'cluster-1',
        cluster_ref: 'cluster-1',
        status: 'partially_compacted',
        member_count: 2,
        candidate_edge_count: 1,
        batch_count: 1,
        node_count: 3,
        active_node_count: 2,
        active_compacted_node_count: 1,
        comparison_count: 2,
        pending_comparison_count: 1,
        work_item_count: 2,
        ready_work_item_count: 1,
        leased_work_item_count: 1,
        completed_work_item_count: 2,
        retryable_failed_work_item_count: 0,
        terminal_failed_work_item_count: 0,
        user_action_required_work_item_count: 0,
        members: [
          {
            observation_ref: 'claim-1',
            claim: 'Поддержка отвечает круглосуточно.',
            possible_questions: ['Когда работает поддержка?'],
            exclusion_scope: ['Праздничные исключения не описаны'],
            granularity: 'atomic',
            source_document_ref: 'document-1',
            source_unit_ref: 'unit-1',
            embedding_ref: 'embedding-1',
            embedding_model_id: 'text-embedding-3-small',
            embedding_dimensions: 1536,
            embedding_status: 'ready',
            node_ref: 'node-1',
            node_kind: 'raw',
            node_active: true,
            node_status: 'active',
            member_rank: 0,
            member_kind: 'draft_claim',
          },
          {
            observation_ref: 'claim-2',
            claim: 'Оператор подключается по запросу.',
            possible_questions: [],
            exclusion_scope: [],
            granularity: 'atomic',
            source_document_ref: 'document-1',
            source_unit_ref: 'unit-2',
            embedding_ref: 'embedding-2',
            embedding_model_id: 'text-embedding-3-small',
            embedding_dimensions: 1536,
            embedding_status: 'ready',
            node_ref: 'node-2',
            node_kind: 'raw',
            node_active: false,
            node_status: 'superseded',
            member_rank: 1,
            member_kind: 'draft_claim',
          },
        ],
        claims: [
          {
            observation_ref: 'claim-1',
            claim: 'Поддержка отвечает круглосуточно.',
            possible_questions: ['Когда работает поддержка?'],
            exclusion_scope: ['Праздничные исключения не описаны'],
            granularity: 'atomic',
            source_document_ref: 'document-1',
            source_unit_ref: 'unit-1',
            embedding_ref: 'embedding-1',
            embedding_model_id: 'text-embedding-3-small',
            embedding_dimensions: 1536,
            embedding_status: 'ready',
            node_ref: 'node-1',
            node_kind: 'raw',
            node_active: true,
            node_status: 'active',
            member_rank: 0,
            member_kind: 'draft_claim',
          },
          {
            observation_ref: 'claim-2',
            claim: 'Оператор подключается по запросу.',
            possible_questions: [],
            exclusion_scope: [],
            granularity: 'atomic',
            source_document_ref: 'document-1',
            source_unit_ref: 'unit-2',
            embedding_ref: 'embedding-2',
            embedding_model_id: 'text-embedding-3-small',
            embedding_dimensions: 1536,
            embedding_status: 'ready',
            node_ref: 'node-2',
            node_kind: 'raw',
            node_active: false,
            node_status: 'superseded',
            member_rank: 1,
            member_kind: 'draft_claim',
          },
        ],
        comparisons: [
          {
            comparison_ref: 'comparison-1',
            cluster_ref: 'cluster-1',
            left_node_ref: 'node-1',
            right_node_ref: 'node-2',
            status: 'merged',
            result_node_ref: 'node-3',
            round_index: 0,
          },
          {
            comparison_ref: 'comparison-2',
            cluster_ref: 'cluster-1',
            left_node_ref: 'node-3',
            right_node_ref: 'node-4',
            status: 'pending',
            result_node_ref: null,
            round_index: 1,
          },
        ],
      },
    ],
    claim_compaction_comparisons: [
      {
        comparison_ref: 'comparison-1',
        cluster_ref: 'cluster-1',
        left_node_ref: 'node-1',
        right_node_ref: 'node-2',
        status: 'merged',
        result_node_ref: 'node-3',
        round_index: 0,
      },
      {
        comparison_ref: 'comparison-2',
        cluster_ref: 'cluster-1',
        left_node_ref: 'node-3',
        right_node_ref: 'node-4',
        status: 'pending',
        result_node_ref: null,
        round_index: 1,
      },
    ],
    curation: {
      available: false,
      reason_code: 'preview_not_ready',
      item_count: 0,
      excluded_item_count: 0,
    },
    actions: [],
  },
};

describe('KnowledgeDocumentCard live-state compaction UI', () => {
  it('shows embedding and clustering stages as running before they finish', () => {
    const runningEmbeddingState: WorkbenchWorkflowLiveStateResponse = {
      ...workflowProjectionState,
      workflow: {
        ...workflowProjectionState.workflow,
        claim_clusters: [],
        claim_compaction_comparisons: [],
        stages: [
          {
            id: 'draft_claim_embeddings',
            label: 'Embeddings',
            status: 'running',
            current: 4,
            total: 10,
            message: '',
          },
          {
            id: 'draft_claim_clustering',
            label: 'Clusters',
            status: 'pending',
            current: 0,
            total: 0,
            message: '',
          },
        ],
      },
    };

    const embeddingMarkup = renderToStaticMarkup(
      <KnowledgeDocumentCard
        doc={{
          id: 'document-1',
          file_name: 'knowledge.md',
          file_size: 1024,
          preprocessing_mode: 'faq',
        }}
        isDeletePending={false}
        onRequestDelete={vi.fn()}
        onCardAction={vi.fn()}
        onOpenCuration={vi.fn()}
        workflowProjectionState={runningEmbeddingState}
        formatSize={() => '1 КБ'}
        knowledgeProcessingModeLabel={() => 'FAQ'}
      />,
    );

    expect(embeddingMarkup).toContain('Векторизация утверждений');
    expect(embeddingMarkup).toContain('4 / 10');
    expect(embeddingMarkup).toContain('идёт');

    const runningClusteringState: WorkbenchWorkflowLiveStateResponse = {
      ...runningEmbeddingState,
      workflow: {
        ...runningEmbeddingState.workflow,
        stages: [
          {
            id: 'draft_claim_embeddings',
            label: 'Embeddings',
            status: 'completed',
            current: 10,
            total: 10,
            message: '',
          },
          {
            id: 'draft_claim_clustering',
            label: 'Clusters',
            status: 'running',
            current: 0,
            total: 10,
            message: '',
          },
        ],
      },
    };

    const clusteringMarkup = renderToStaticMarkup(
      <KnowledgeDocumentCard
        doc={{
          id: 'document-1',
          file_name: 'knowledge.md',
          file_size: 1024,
          preprocessing_mode: 'faq',
        }}
        isDeletePending={false}
        onRequestDelete={vi.fn()}
        onCardAction={vi.fn()}
        onOpenCuration={vi.fn()}
        workflowProjectionState={runningClusteringState}
        formatSize={() => '1 КБ'}
        knowledgeProcessingModeLabel={() => 'FAQ'}
      />,
    );

    expect(clusteringMarkup).toContain('Группировка похожих утверждений');
    expect(clusteringMarkup).toContain('0 / 10');
    expect(clusteringMarkup).toContain('идёт');
  });

  it('uses live cluster data for summaries and exposes claim details', () => {
    const markup = renderToStaticMarkup(
      <KnowledgeDocumentCard
        doc={{
          id: 'document-1',
          file_name: 'knowledge.md',
          file_size: 1024,
          preprocessing_mode: 'faq',
        }}
        isDeletePending={false}
        onRequestDelete={vi.fn()}
        onCardAction={vi.fn()}
        onOpenCuration={vi.fn()}
        workflowProjectionState={workflowProjectionState}
        formatSize={() => '1 КБ'}
        knowledgeProcessingModeLabel={() => 'FAQ'}
      />,
    );
    const normalizedMarkup = markup.replaceAll('\u00a0', ' ');

    expect(normalizedMarkup).toContain('1. Векторизация утверждений');
    expect(normalizedMarkup).toContain('2 / 2');
    expect(normalizedMarkup).toContain('2. Группировка похожих утверждений');
    expect(normalizedMarkup).toContain('1 / 1');
    expect(normalizedMarkup).toContain('3. Объединение знаний');
    expect(normalizedMarkup).toContain('0 / 1');
    expect(normalizedMarkup).toContain('идёт');
    expect(normalizedMarkup).toContain('1 кл.');
    expect(normalizedMarkup).not.toContain('Claim Compaction');
    expect(normalizedMarkup).not.toContain('Сравнения: 1 / 2');
    expect(normalizedMarkup).toContain('<details');
    expect(normalizedMarkup).toContain('Кластер 1');
    expect(normalizedMarkup).toContain('Поддержка отвечает круглосуточно.');
    expect(normalizedMarkup).toContain('Когда работает поддержка?');
    expect(normalizedMarkup).toContain('Праздничные исключения не описаны');
    expect(normalizedMarkup).toContain('Объединение знаний');
    expect(normalizedMarkup).not.toContain('0% кластеров готово');
    expect(normalizedMarkup).not.toContain('В очереди');
    expect(normalizedMarkup).not.toContain('Нужно внимание');
    expect(normalizedMarkup).toContain('Кластер 1');
    expect(normalizedMarkup).toContain('bg-sky-500/10');
    expect(normalizedMarkup).toContain('Поддержка отвечает круглосуточно.');
    expect(normalizedMarkup).toContain('Оператор подключается по запросу.');
  });

  it('shows a clear review-ready completion state', () => {
    const completedState: WorkbenchWorkflowLiveStateResponse = {
      ...workflowProjectionState,
      workflow: {
        ...workflowProjectionState.workflow,
        current_phase: 'WAITING_FOR_REVIEW',
        stages: workflowProjectionState.workflow.stages.map((stage) =>
          stage.id === 'draft_claim_compaction'
            ? { ...stage, status: 'completed', current: 1, total: 1 }
            : stage,
        ),
        claim_clusters: workflowProjectionState.workflow.claim_clusters?.map((cluster) => ({
          ...cluster,
          status: 'compacted',
          active_compacted_node_count: 2,
          ready_work_item_count: 0,
          leased_work_item_count: 0,
          completed_work_item_count: 3,
          pending_comparison_count: 0,
          compacted_claims: [
            {
              node_ref: 'compacted-1',
              claim: 'Поддержка доступна круглосуточно без перерывов.',
              claim_kind: 'property',
              merge_decision: 'unmerged',
              source_claim_refs: ['claim-1'],
              active: true,
            },
            {
              node_ref: 'compacted-2',
              claim: 'Оператор подключается после запроса клиента.',
              claim_kind: 'process',
              merge_decision: 'unmerged',
              source_claim_refs: ['claim-2'],
              active: true,
            },
          ],
        })),
        curation: {
          available: true,
          reason_code: 'ready',
          workflow_run_id: 'workflow-1',
          workspace_ref: 'workspace-1',
          workspace_status: 'draft',
          item_count: 2,
          excluded_item_count: 0,
        },
      },
    };

    const markup = renderToStaticMarkup(
      <KnowledgeDocumentCard
        doc={{
          id: 'document-1',
          file_name: 'knowledge.md',
          file_size: 1024,
          preprocessing_mode: 'faq',
        }}
        isDeletePending={false}
        onRequestDelete={vi.fn()}
        onCardAction={vi.fn()}
        onOpenCuration={vi.fn()}
        workflowProjectionState={completedState}
        formatSize={() => '1 КБ'}
        knowledgeProcessingModeLabel={() => 'FAQ'}
      />,
    );

    expect(markup).not.toContain('100% кластеров готово');
    expect(markup).not.toContain('Объединение завершено — знания готовы к ручной проверке.');
    expect(markup).toContain('bg-emerald-500/10');
    expect(markup).toContain('Факты кластера: 2');
    expect(markup).not.toContain('Итоговые утверждения');
    expect(markup).not.toContain('Поддержка доступна круглосуточно без перерывов.');
    expect(markup).not.toContain('Оператор подключается после запроса клиента.');
  });
});
