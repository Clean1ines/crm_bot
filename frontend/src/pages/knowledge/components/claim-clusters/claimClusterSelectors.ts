import type { WorkbenchWorkflowLiveState } from '@shared/api/modules/knowledge';

import { normalize } from '../workflow-card/workflowCardLabels';
import type {
  ClaimClustersDraftArtifact,
  ClaimClustersView,
  FinalCompactedFact,
} from './claimClusterTypes';

const formatViewNumber = (value: number): string =>
  new Intl.NumberFormat('ru-RU').format(Math.max(0, Math.floor(value || 0)));

export const selectClaimClustersView = (
  workflow: WorkbenchWorkflowLiveState | null,
  draftArtifacts: readonly ClaimClustersDraftArtifact[] = [],
): ClaimClustersView => {
  const hasClusters = Array.isArray(workflow?.claim_clusters);
  const clusters = workflow?.claim_clusters ?? [];
  const nestedComparisons = clusters.flatMap((cluster) => cluster.comparisons);
  const hasComparisons =
    Array.isArray(workflow?.claim_compaction_comparisons) ||
    clusters.some((cluster) => Array.isArray(cluster.comparisons));
  const comparisons = workflow?.claim_compaction_comparisons ?? nestedComparisons;
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
  const succeededAttemptCount = llmAttempts.filter(
    (attempt) => normalize(attempt.status) === 'succeeded',
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
      llmAttemptCount: llmAttempts.length,
      succeededAttemptCount,
      runningAttemptCount,
      tokens,
    },
  };
};
