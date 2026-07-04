import type { WorkbenchWorkflowLiveState } from '@shared/api/modules/knowledge';

import { normalize } from '../workflow-card/workflowCardLabels';
import type {
  ClaimClusterCompactionAttemptView,
  ClaimClustersDraftArtifact,
  ClaimClustersView,
  FinalCompactedFact,
} from './claimClusterTypes';

const formatViewNumber = (value: number): string =>
  new Intl.NumberFormat('ru-RU').format(Math.max(0, Math.floor(value || 0)));

const attemptNumberFromId = (attemptId: string, fallback: number): number => {
  const match = attemptId.match(/:attempt:(\d+)$/);
  if (!match) return fallback;
  const parsed = Number.parseInt(match[1] ?? '', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

const compactionAttemptStatusLabel = (status: string | null | undefined): string => {
  const value = normalize(status);
  if (value === 'completed' || value === 'succeeded') return 'ответ принят';
  if (value === 'retryable_failed') return 'ответ не принят, будет повтор';
  if (value === 'terminal_failed' || value === 'failed') return 'ошибка';
  if (value === 'leased' || value === 'running') return 'выполняется';
  if (value === 'ready' || value === 'pending') return 'ожидает запуска';
  return 'состояние уточняется';
};

const compactionAttemptTone = (status: string | null | undefined): string => {
  const value = normalize(status);
  if (value === 'completed' || value === 'succeeded') {
    return 'border-emerald-500/25 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200';
  }
  if (value === 'retryable_failed') {
    return 'border-amber-500/25 bg-amber-500/10 text-amber-800 dark:text-amber-200';
  }
  if (value === 'terminal_failed' || value === 'failed') {
    return 'border-rose-500/25 bg-rose-500/10 text-rose-800 dark:text-rose-200';
  }
  if (value === 'leased' || value === 'running') {
    return 'border-sky-500/25 bg-sky-500/10 text-sky-800 dark:text-sky-200';
  }
  return 'border-[var(--border-subtle)] bg-[var(--surface-secondary)] text-[var(--text-secondary)]';
};

const compactionAttemptErrorMessage = (attempt: {
  status?: string | null;
  error_message_user?: string | null;
}): string | null => {
  const explicit = attempt.error_message_user?.trim();
  if (explicit) return explicit;

  const value = normalize(attempt.status);
  if (value === 'retryable_failed') {
    return 'ИИ вернул ответ, который не прошёл проверку качества. Запланирована повторная попытка.';
  }
  if (value === 'terminal_failed' || value === 'failed') {
    return 'Объединение остановилось из-за ошибки.';
  }
  return null;
};

export const selectClaimClustersView = (
  workflow: WorkbenchWorkflowLiveState | null,
  draftArtifacts: readonly ClaimClustersDraftArtifact[] = [],
): ClaimClustersView => {
  const clusters = workflow?.claim_clusters ?? [];
  const hasClusters = clusters.length > 0;
  const nestedComparisons = clusters.flatMap((cluster) => cluster.comparisons ?? []);
  const comparisons = [
    ...(workflow?.claim_compaction_comparisons ?? []),
    ...nestedComparisons,
  ];
  const hasComparisons = comparisons.length > 0;
  const clusteredClaims = clusters.flatMap((cluster) => cluster.claims ?? cluster.members);
  const clusteredClaimCount = clusters.reduce(
    (total, cluster) => total + cluster.member_count,
    0,
  );
  const embeddedClaimCount = clusteredClaims.filter(
    (claim) =>
      Boolean(claim.embedding_ref) &&
      !['failed', 'missing', 'pending'].includes(normalize(claim.embedding_status)),
  ).length;
  const resolvedComparisonCount = comparisons.filter(
    (comparison) =>
      !['pending', 'waiting_user_model_choice'].includes(normalize(comparison.status)),
  ).length;
  const compactedClusterCount = clusters.filter(
    (cluster) => normalize(cluster.status) === 'compacted',
  ).length;
  const ready = clusters.reduce(
    (total, cluster) => total + (cluster.ready_work_item_count ?? 0),
    0,
  );
  const leased = clusters.reduce(
    (total, cluster) => total + (cluster.leased_work_item_count ?? 0),
    0,
  );
  const done = clusters.reduce(
    (total, cluster) => total + (cluster.completed_work_item_count ?? 0),
    0,
  );
  const retry = clusters.reduce(
    (total, cluster) => total + (cluster.retryable_failed_work_item_count ?? 0),
    0,
  );
  const failed = clusters.reduce(
    (total, cluster) => total + (cluster.terminal_failed_work_item_count ?? 0),
    0,
  );
  const needsDecision = clusters.reduce(
    (total, cluster) => total + (cluster.user_action_required_work_item_count ?? 0),
    0,
  );
  const previewCount = clusters.reduce(
    (total, cluster) => total + (cluster.compacted_claims?.length ?? 0),
    0,
  );
  const extractedFacts = Array.from(
    new Map(
      (clusteredClaims.length > 0
        ? clusteredClaims.map((claim) => ({
            key: claim.observation_ref,
            text: claim.claim,
          }))
        : draftArtifacts.map((artifact) => ({
            key: artifact.observationRef,
            text: artifact.claim,
          }))
      )
        .filter((fact) => fact.text.trim().length > 0)
        .map((fact) => [fact.key, fact]),
    ).values(),
  );
  const finalFacts: FinalCompactedFact[] = clusters.flatMap((cluster) =>
    (cluster.compacted_claims ?? [])
      .filter((claim) => claim.active)
      .map((claim) => ({
        ...claim,
        cluster_ref: cluster.cluster_ref,
      })),
  );
  const progressPercent =
    clusters.length > 0
      ? Math.round((compactedClusterCount / clusters.length) * 100)
      : 0;
  const attention = retry + failed + needsDecision;
  const isComplete = clusters.length > 0 && compactedClusterCount === clusters.length;
  const panelTone =
    workflow?.curation.available || isComplete
      ? 'border-emerald-500/30 bg-emerald-500/10'
      : failed > 0
        ? 'border-rose-500/30 bg-rose-500/10'
        : attention > 0
          ? 'border-amber-500/30 bg-amber-500/10'
          : leased > 0
            ? 'border-sky-500/30 bg-sky-500/10'
            : 'border-[var(--border-strong)] bg-[var(--surface-secondary)]';
  const summaryText =
    leased > 0
      ? `Сейчас ИИ объединяет ${formatViewNumber(leased)} кластер(а).`
      : ready > 0
        ? `Ждут объединения ${formatViewNumber(ready)} кластер(а).`
        : compactedClusterCount === clusters.length && clusters.length > 0
          ? 'Все кластеры объединены.'
          : 'Состояние объединения уточняется.';
  const userSummary = workflow?.curation.available
    ? 'Объединение завершено — знания готовы к ручной проверке.'
    : failed > 0
      ? 'Часть кластеров завершилась с ошибкой.'
      : needsDecision > 0
        ? 'Для продолжения нужно решение пользователя.'
        : leased > 0
          ? 'ИИ сейчас объединяет связанные факты.'
          : ready > 0
            ? 'Кластеры ждут своей очереди на объединение.'
            : isComplete
              ? 'Все кластеры объединены.'
              : summaryText;
  const llmAttempts = (workflow?.llm_attempts ?? []).filter(
    (attempt) => attempt.node_name === 'knowledge_workbench.draft_claim_compaction',
  );
  const compactionAttempts: ClaimClusterCompactionAttemptView[] = llmAttempts
    .map((attempt, index) => ({
      key: attempt.node_run_id || `draft-compaction-attempt-${index}`,
      workItemId: attempt.section_id ?? null,
      attemptNumber: attemptNumberFromId(attempt.node_run_id, index + 1),
      status: attempt.status,
      statusLabel: compactionAttemptStatusLabel(attempt.status),
      toneClassName: compactionAttemptTone(attempt.status),
      modelName: attempt.model_name?.trim() || null,
      provider: attempt.model_provider?.trim() || null,
      tokenCount: Math.max(0, attempt.total_tokens || 0),
      durationMs: attempt.duration_ms ?? null,
      startedAt: attempt.started_at ?? null,
      completedAt: attempt.completed_at ?? null,
      errorMessage: compactionAttemptErrorMessage(attempt),
    }))
    .sort((left, right) => {
      const leftTime = left.startedAt ?? left.completedAt ?? '';
      const rightTime = right.startedAt ?? right.completedAt ?? '';
      return leftTime.localeCompare(rightTime) || left.key.localeCompare(right.key);
    });
  const succeededAttemptCount = llmAttempts.filter((attempt) =>
    ['succeeded', 'completed'].includes(normalize(attempt.status)),
  ).length;
  const runningAttemptCount = llmAttempts.filter((attempt) =>
    ['leased', 'running', 'ready'].includes(normalize(attempt.status)),
  ).length;
  const tokens = llmAttempts.reduce(
    (total, attempt) => total + Math.max(0, attempt.total_tokens || 0),
    0,
  );

  return {
    hasClusters,
    clusters,
    hasComparisons,
    comparisons,
    clusteredClaimCount,
    embeddedClaimCount,
    resolvedComparisonCount,
    compactedClusterCount,
    extractedFacts,
    finalFacts,
    compaction: {
      ready,
      leased,
      done,
      retry,
      failed,
      needsDecision,
      previewCount,
      progressPercent,
      attention,
      isComplete,
      panelTone,
      userSummary,
      attempts: compactionAttempts,
      llmAttemptCount: llmAttempts.length,
      succeededAttemptCount,
      runningAttemptCount,
      tokens,
    },
  };
};
