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
    {(cluster.compacted_claims ?? []).length > 0 && (
      <div className="mt-2 text-[var(--text-muted)]">
        Итоговых утверждений: {formatNumber(cluster.compacted_claims?.length ?? 0)}
      </div>
    )}

    <div className="mt-2 space-y-2">
      {(cluster.claims ?? cluster.members).map((claim) => (
        <ClaimClusterClaimRow
          key={claim.observation_ref}
          claim={claim}
        />
      ))}
    </div>
  </details>
);
