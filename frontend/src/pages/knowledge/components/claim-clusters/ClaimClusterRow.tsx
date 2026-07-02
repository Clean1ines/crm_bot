import React from 'react';
import type { WorkbenchClaimClusterLiveState } from '@shared/api/modules/knowledge';

import {
  clusterHumanState,
  clusterStatusTitle,
  clusterStatusTone,
  queueStatusLabel,
  statusPillTone,
} from '../workflow-card/workflowCardLabels';
import { ClaimClusterClaimRow } from './ClaimClusterClaimRow';

type ClaimClusterRowProps = {
  cluster: WorkbenchClaimClusterLiveState;
  clusterIndex: number;
  formatNumber: (value: number) => string;
};

export const ClaimClusterRow: React.FC<ClaimClusterRowProps> = ({
  cluster,
  clusterIndex,
  formatNumber,
}) => (
  <details
    key={cluster.cluster_ref}
    className={`rounded-lg border p-2 ${clusterStatusTone(cluster.status)}`}
  >
    <summary className="cursor-pointer list-none">
      <span className="flex flex-wrap items-center justify-between gap-2">
        <span>
          <span className="font-medium text-[var(--text-primary)]">
            Кластер {formatNumber(clusterIndex + 1)}
          </span>
          <span className="ml-2 text-[var(--text-muted)]">
            {clusterHumanState(cluster)} · утверждений: {formatNumber(cluster.member_count)}
          </span>
        </span>
        <span className="rounded-full bg-[var(--surface-elevated)] px-2 py-1 font-medium text-[var(--text-primary)]">
          {clusterStatusTitle(cluster.status)}
        </span>
      </span>
    </summary>
    <div className="mt-2 grid gap-1 text-[var(--text-muted)] [grid-template-columns:repeat(auto-fit,minmax(130px,1fr))]">
      <div>кандидатных связей: {formatNumber(cluster.candidate_edge_count)}</div>
      <div>batch: {formatNumber(cluster.batch_count)}</div>
      <div>
        узлов: {formatNumber(cluster.active_node_count)} активных из{' '}
        {formatNumber(cluster.node_count)}
      </div>
      <div>compacted-узлов: {formatNumber(cluster.active_compacted_node_count)}</div>
      <div>
        сравнений: {formatNumber(cluster.comparison_count)} · ожидают:{' '}
        {formatNumber(cluster.pending_comparison_count)}
      </div>
      <div>work items: {formatNumber(cluster.work_item_count)}</div>
    </div>

    {(cluster.batches ?? []).length > 0 && (
      <div className="mt-2 space-y-1 rounded-lg bg-[var(--surface-elevated)] p-2">
        <div className="font-medium text-[var(--text-primary)]">
          Батчи compaction: {formatNumber(cluster.batches?.length ?? 0)}
        </div>
        <div className="mt-1 space-y-1">
          {(cluster.batches ?? []).map((batch, batchIndex) => (
            <div
              key={batch.batch_ref}
              className="flex flex-wrap items-center justify-between gap-2 rounded border border-[var(--border-subtle)] bg-[var(--surface-secondary)] px-2 py-1"
            >
              <span className="font-medium text-[var(--text-primary)]">
                Batch {formatNumber(batchIndex + 1)}
              </span>
              <span className="text-[var(--text-muted)]">
                утверждений: {formatNumber(batch.member_count)}
              </span>
              <span className={`rounded-full px-2 py-0.5 font-medium ${statusPillTone(batch.status)}`}>
                {queueStatusLabel(batch.status)}
              </span>
            </div>
          ))}
        </div>
      </div>
    )}

    <div className="mt-2 space-y-2">
      {(cluster.claims ?? cluster.members).map((claim) => (
        <ClaimClusterClaimRow
          key={claim.observation_ref}
          claim={claim}
          formatNumber={formatNumber}
        />
      ))}
    </div>
  </details>
);
