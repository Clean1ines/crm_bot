import type {
  WorkflowStageCountContext,
  WorkflowStageInput,
  WorkflowStageRowView,
} from './workflowStagesTypes';

const normalize = (value: string | null | undefined): string =>
  (value || '').trim().toLowerCase();

const DOMAIN_SCOPED_STAGE_IDS = new Set([
  'draft_claim_embeddings',
  'draft_claim_clustering',
  'draft_claim_compaction',
]);

const hasGenericProgressEvidence = (stage: WorkflowStageInput): boolean =>
  stage.current > 0 ||
  stage.total > 0 ||
  Boolean(stage.started_at) ||
  Boolean(stage.completed_at);

const workflowStageHasStarted = (
  stage: WorkflowStageInput | null | undefined,
  context: WorkflowStageCountContext,
): boolean => {
  if (!stage) return false;
  if (context.startedStageIds?.includes(stage.id)) return true;

  if (DOMAIN_SCOPED_STAGE_IDS.has(stage.id)) {
    return false;
  }

  const status = normalize(stage.status);
  return (status !== 'pending' && status !== 'unknown') || hasGenericProgressEvidence(stage);
};

const stageTitle = (stage: WorkflowStageInput): string => {
  const labels: Record<string, string> = {
    source_ingestion: 'Подготовка документа',
    prompt_a_claim_extraction: 'Извлечение утверждений',
    draft_claim_embeddings: 'Векторизация утверждений',
    draft_claim_clustering: 'Группировка похожих утверждений',
    draft_claim_compaction: 'Объединение знаний',
    cluster_preview: 'Предпросмотр базы знаний',
    curation: 'Проверка человеком',
    publication: 'Публикация',
  };
  return labels[stage.id] || stage.label || stage.id;
};

const stageStatusLabel = (stage: WorkflowStageInput): string => {
  if (stage.id === 'curation') {
    if (stage.status === 'completed') return 'доступна';
    return 'недоступна до предпросмотра';
  }

  if (stage.id === 'publication') {
    if (stage.status === 'completed') return 'готово к публикации';
    return 'не готово к публикации';
  }

  const labels: Record<string, string> = {
    pending: 'ожидает предыдущий этап',
    running: 'идёт',
    completed: 'завершено',
    failed: 'ошибка',
    paused: 'на паузе',
    blocked: 'требует внимания',
    deferred: 'отложено',
    unknown: 'недоступно до предыдущего этапа',
  };
  return labels[stage.status] || 'состояние уточняется';
};

const stageToneClassName = (stage: WorkflowStageInput): string => {
  const status = normalize(stage.status);
  if (status === 'completed') {
    return 'border-emerald-500/25 bg-emerald-500/10';
  }
  if (status === 'running') {
    return 'border-sky-500/25 bg-sky-500/10';
  }
  if (status === 'paused' || status === 'deferred' || status === 'pending' || status === 'unknown') {
    return 'border-[var(--border-subtle)] bg-[var(--surface-elevated)]';
  }
  if (status === 'blocked') {
    return 'border-amber-500/30 bg-amber-500/10';
  }
  if (status === 'failed') {
    return 'border-rose-500/30 bg-rose-500/10';
  }
  return 'border-[var(--border-subtle)] bg-[var(--surface-elevated)]';
};

const statusPillClassName = (status: string): string => {
  const value = normalize(status);
  if (value === 'completed' || value === 'ready' || value === 'succeeded' || value === 'claim_observations_persisted') {
    return 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
  }
  if (value === 'running' || value === 'leased') {
    return 'bg-sky-500/10 text-sky-700 dark:text-sky-300';
  }
  if (value === 'paused' || value === 'deferred' || value === 'pending' || value === 'unknown') {
    return 'bg-[var(--control-bg)] text-[var(--text-secondary)]';
  }
  if (value === 'retryable_failed' || value === 'blocked' || value === 'user_action_required') {
    return 'bg-amber-500/10 text-amber-700 dark:text-amber-300';
  }
  if (value === 'terminal_failed' || value === 'failed') {
    return 'bg-rose-500/10 text-rose-700 dark:text-rose-300';
  }
  return 'bg-[var(--control-bg)] text-[var(--text-secondary)]';
};

const displayedStageStatus = (
  stage: WorkflowStageInput,
  context: WorkflowStageCountContext,
): string => {
  if (stage.id === 'draft_claim_embeddings' && context.hasClaimClusters) {
    return 'completed';
  }

  if (stage.id === 'draft_claim_clustering' && context.hasClaimClusters) {
    return 'completed';
  }

  if (
    stage.id === 'draft_claim_compaction' &&
    (context.hasCompactionComparisons || context.finalCompactedFactCount > 0)
  ) {
    if (
      context.claimClusterCount > 0 &&
      context.compactedClusterCount >= context.claimClusterCount
    ) {
      return 'completed';
    }
    return 'running';
  }

  return stage.status;
};

const displayedStageCounts = (
  stage: WorkflowStageInput,
  context: WorkflowStageCountContext,
): { current: number; total: number } => {
  if (stage.id === 'draft_claim_embeddings' && context.hasClaimClusters) {
    return {
      current: context.embeddedClaimCount,
      total: context.clusteredClaimCount,
    };
  }

  if (stage.id === 'draft_claim_clustering' && context.hasClaimClusters) {
    return {
      current: context.claimClusterCount,
      total: context.claimClusterCount,
    };
  }

  if (
    stage.id === 'draft_claim_compaction' &&
    (context.hasCompactionComparisons || context.finalCompactedFactCount > 0)
  ) {
    return {
      current: context.compactedClusterCount,
      total: context.claimClusterCount,
    };
  }

  return {
    current: stage.current,
    total: stage.total,
  };
};

export const selectWorkflowStageRows = (
  stages: WorkflowStageInput[],
  context: WorkflowStageCountContext,
): WorkflowStageRowView[] =>
  stages.filter((stage) => workflowStageHasStarted(stage, context)).map((stage) => {
    const counts = displayedStageCounts(stage, context);
    const rowStage = {
      ...stage,
      status: displayedStageStatus(stage, context),
    };

    return {
      id: rowStage.id,
      title: stageTitle(rowStage),
      status: rowStage.status,
      statusLabel: stageStatusLabel(rowStage),
      toneClassName: stageToneClassName(rowStage),
      pillClassName: statusPillClassName(rowStage.status),
      current: counts.current,
      total: counts.total,
      showCounts: counts.total > 0 && rowStage.id !== 'cluster_preview',
      message: rowStage.message?.trim() || null,
    };
  });
