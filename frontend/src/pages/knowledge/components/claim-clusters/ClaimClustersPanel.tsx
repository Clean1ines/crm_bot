import React, { type ReactNode } from 'react';

import { ClaimClusterRow } from './ClaimClusterRow';
import type { ClaimClustersView } from './claimClusterTypes';

type ClaimClustersPanelSlots = {
  summary: ReactNode;
  details: ReactNode;
};

type ClaimClustersPanelProps = {
  view: ClaimClustersView;
  formatNumber: (value: number) => string;
  children?: (slots: ClaimClustersPanelSlots) => ReactNode;
};

export const ClaimClustersPanel: React.FC<ClaimClustersPanelProps> = ({
  view,
  formatNumber,
  children,
}) => {
  const summary = null;

  const details = view.clusters.length > 0 ? (
    <details
      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3"
      open
    >
      <summary className="cursor-pointer list-none">
        <span className="flex flex-wrap items-center justify-between gap-2">
          <span>
            <span className="font-medium text-[var(--text-primary)]">
              Кластеры утверждений
            </span>
            <span className="ml-2 text-xs text-[var(--text-muted)]">
              {formatNumber(view.clusters.length)} кл.
            </span>
          </span>
          <span className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-xs text-[var(--text-secondary)]">
            {formatNumber(view.compaction.llmAttemptCount)} попыток
          </span>
        </span>
      </summary>

      <div className="mt-2 space-y-1.5">
        {view.clusters.length === 0 && (
          <div className="rounded-lg border border-dashed border-[var(--border-subtle)] px-3 py-2 text-xs text-[var(--text-muted)]">
            Кластеры ещё не сформированы.
          </div>
        )}
        {view.clusters.map((cluster, clusterIndex) => (
          <ClaimClusterRow
            key={cluster.cluster_ref}
            cluster={cluster}
            clusterIndex={clusterIndex}
            attempts={view.compaction.attempts}
            formatNumber={formatNumber}
          />
        ))}
      </div>
    </details>
  ) : null;

  if (children) {
    return <>{children({ summary, details })}</>;
  }

  return (
    <>
      {summary}
      {details}
    </>
  );
};
