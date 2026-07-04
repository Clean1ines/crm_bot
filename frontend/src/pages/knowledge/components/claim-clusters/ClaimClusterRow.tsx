import React from 'react';
import type {
  WorkbenchClaimClusterBatchLiveState,
  WorkbenchClaimClusterLiveState,
} from '@shared/api/modules/knowledge';

import {
  claimBuilderSectionRowTone,
  claimBuilderSectionStatusLabel,
  claimBuilderSectionStatusTone,
  formatClaimBuilderNumber,
} from '../claim-builder/claimBuilderLabels';
import { ClaimClusterClaimRow } from './ClaimClusterClaimRow';
import { ClaimClusterCompactionAttemptRow } from './ClaimClusterCompactionAttemptRow';
import type { ClaimClusterCompactionAttemptView } from './claimClusterTypes';

type ClaimClusterRowProps = {
  cluster: WorkbenchClaimClusterLiveState;
  clusterIndex: number;
  attempts: ClaimClusterCompactionAttemptView[];
  formatNumber: (value: number) => string;
};

const normalize = (value: string | null | undefined): string =>
  (value || '').trim().toLowerCase();

const clusterUiStatus = (status: string): string => {
  const value = normalize(status);
  if (value === 'compacted' || value === 'completed' || value === 'succeeded') {
    return 'completed';
  }
  if (value === 'processing' || value === 'leased' || value === 'running') {
    return 'leased';
  }
  if (value === 'needs_attention' || value === 'retryable_failed') {
    return 'retryable_failed';
  }
  if (value === 'terminal_failed' || value === 'failed') {
    return 'terminal_failed';
  }
  return 'ready';
};

const batchAttempts = (
  batch: WorkbenchClaimClusterBatchLiveState,
  attempts: ClaimClusterCompactionAttemptView[],
): ClaimClusterCompactionAttemptView[] =>
  attempts.filter((attempt) => attempt.workItemId === batch.work_item_id);

const batchTitle = (
  batch: WorkbenchClaimClusterBatchLiveState,
  batchIndex: number,
): string =>
  batch.prompt_variant?.trim() ||
  batch.batch_ref?.trim() ||
  `Batch ${formatClaimBuilderNumber(batchIndex + 1)}`;

const ClaimClusterBatchRow = ({
  batch,
  batchIndex,
  attempts,
}: {
  batch: WorkbenchClaimClusterBatchLiveState;
  batchIndex: number;
  attempts: ClaimClusterCompactionAttemptView[];
}) => {
  const status = clusterUiStatus(batch.status);
  const ownedAttempts = batchAttempts(batch, attempts);

  return (
    <details className={`rounded-lg border px-3 py-2 ${claimBuilderSectionRowTone(status)}`}>
      <summary className="cursor-pointer list-none">
        <span className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <span className="min-w-0">
            <span className="font-medium text-[var(--text-primary)]">
              Batch {formatClaimBuilderNumber(batchIndex + 1)}
            </span>
            <span className="ml-2 text-[var(--text-muted)]">
              {batchTitle(batch, batchIndex)}
            </span>
          </span>

          <span className="flex flex-wrap items-center gap-2">
            <span className={`text-xs ${claimBuilderSectionStatusTone(status)}`}>
              {claimBuilderSectionStatusLabel(status)}
              {ownedAttempts.length > 0
                ? ` · попыток: ${formatClaimBuilderNumber(ownedAttempts.length)}`
                : ''}
            </span>

            {status === 'retryable_failed' && (
              <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300">
                Нужно внимание
              </span>
            )}
          </span>
        </span>
      </summary>

      <div className="mt-2 space-y-2">
        <div className="space-y-1.5">
          {ownedAttempts.length > 0 ? (
            ownedAttempts.map((attempt) => (
              <ClaimClusterCompactionAttemptRow
                key={attempt.key}
                attempt={attempt}
              />
            ))
          ) : (
            <div className="rounded border border-dashed border-[var(--border-subtle)] px-2 py-1.5 text-xs text-[var(--text-muted)]">
              Попытки обработки этого batch ещё не начались.
            </div>
          )}
        </div>

      </div>
    </details>
  );
};

export const ClaimClusterRow: React.FC<ClaimClusterRowProps> = ({
  cluster,
  clusterIndex,
  attempts,
  formatNumber,
}) => {
  const status = clusterUiStatus(cluster.status);
  const batches = cluster.batches ?? [];
  const clusterAttempts = attempts.filter((attempt) =>
    batches.some((batch) => batch.work_item_id === attempt.workItemId),
  );

  return (
    <details
      key={cluster.cluster_ref}
      className={`rounded-lg border px-3 py-2 ${claimBuilderSectionRowTone(status)}`}
    >
      <summary className="cursor-pointer list-none">
        <span className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <span className="min-w-0">
            <span className="font-medium text-[var(--text-primary)]">
              Кластер {formatNumber(clusterIndex + 1)}
            </span>
            <span className="ml-2 text-[var(--text-muted)]">
              утверждений: {formatNumber(cluster.member_count)}
            </span>
          </span>

          <span className="flex flex-wrap items-center gap-2">
            <span className={`text-xs ${claimBuilderSectionStatusTone(status)}`}>
              {claimBuilderSectionStatusLabel(status)}
              {clusterAttempts.length > 0
                ? ` · попыток: ${formatNumber(clusterAttempts.length)}`
                : ''}
            </span>

            {(cluster.user_action_required_work_item_count ?? 0) > 0 && (
              <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300">
                Нужно решение
              </span>
            )}
          </span>
        </span>
      </summary>

      <div className="mt-2 space-y-2">
        <div className="grid gap-2 text-xs text-[var(--text-muted)] [grid-template-columns:repeat(auto-fit,minmax(120px,1fr))]">
          <div>batch: {formatNumber(batches.length)}</div>
          <div>готово: {formatNumber(cluster.completed_work_item_count ?? 0)}</div>
          <div>в работе: {formatNumber(cluster.leased_work_item_count ?? 0)}</div>
          <div>ожидает: {formatNumber(cluster.ready_work_item_count ?? 0)}</div>
          <div>итогов: {formatNumber(cluster.compacted_claims?.length ?? 0)}</div>
        </div>

        <details className="rounded border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-2 py-1.5" open>
          <summary className="cursor-pointer list-none text-xs font-medium text-[var(--text-primary)]">
            Факты кластера: {formatNumber((cluster.claims ?? cluster.members).length)}
          </summary>
          <div className="mt-2 space-y-2">
            {(cluster.claims ?? cluster.members).map((claim) => (
              <ClaimClusterClaimRow
                key={claim.observation_ref}
                claim={claim}
              />
            ))}
          </div>
        </details>

        <div className="space-y-1.5">
          {batches.length > 0 ? (
            batches.map((batch, batchIndex) => (
              <ClaimClusterBatchRow
                key={batch.batch_ref || batch.work_item_id}
                batch={batch}
                batchIndex={batchIndex}
                attempts={attempts}
              />
            ))
          ) : (
            <div className="rounded border border-dashed border-[var(--border-subtle)] px-2 py-1.5 text-xs text-[var(--text-muted)]">
              Batch work items для этого кластера ещё не появились.
            </div>
          )}
        </div>

        {(cluster.compacted_claims ?? []).length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs font-medium text-[var(--text-primary)]">
              Итоговые утверждения
            </div>
            {(cluster.compacted_claims ?? []).map((claim) => (
              <div
                key={claim.node_ref}
                className="rounded border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-2 py-1.5 text-xs text-[var(--text-secondary)]"
              >
                {claim.claim}
              </div>
            ))}
          </div>
        )}
      </div>
    </details>
  );
};
