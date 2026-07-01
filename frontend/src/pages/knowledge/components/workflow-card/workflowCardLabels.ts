import {
  type WorkbenchWorkflowStageLiveState,
  type WorkbenchClaimClusterClaimLiveState,
} from '@shared/api/modules/knowledge';

export const normalize = (value: string | null | undefined): string =>
  (value || '').trim().toLowerCase();

export const normalizeUpper = (value: string | null | undefined): string =>
  (value || '').trim().toUpperCase();

export const workflowStatusLabel = (status: string | null | undefined): string => {
  const value = normalize(status);
  const labels: Record<string, string> = {
    running: 'Документ обрабатывается',
    active: 'Документ обрабатывается',
    processing: 'Документ обрабатывается',
    paused: 'Обработка на паузе',
    completed: 'Обработка завершена',
    done: 'Обработка завершена',
    failed: 'Нужна проверка',
    cancelled: 'Обработка остановлена',
    blocked: 'Нужна проверка',
  };
  return labels[value] || 'Состояние уточняется';
};

export const phaseLabel = (phase: string | null | undefined): string => {
  const value = normalizeUpper(phase);
  const labels: Record<string, string> = {
    DOCUMENT_ACCEPTED: 'документ принят',
    SOURCE_DOCUMENT_PERSISTED: 'сохраняем документ',
    SOURCE_UNITS_CREATED: 'документ разбит на разделы',
    PROMPT_A_WORK_SCHEDULED: 'готовим извлечение утверждений',
    CLAIM_BUILDER_WORK_SCHEDULING: 'готовим извлечение утверждений',
    CLAIM_BUILDER_SECTION_EXTRACTION: 'извлекаем утверждения из разделов',
    PROMPT_A_WORK_COMPLETED: 'утверждения извлечены',
    PROMPT_A_ARTIFACTS_APPLIED: 'утверждения сохранены',
    DRAFT_EMBEDDINGS_BUILT: 'строим векторы',
    DRAFT_CLUSTERS_BUILT: 'группируем похожие утверждения',
    PROMPT_B_WORK_SCHEDULED: 'готовим объединение знаний',
    PROMPT_B_WORK_COMPLETED: 'объединяем знания',
    FINAL_KNOWLEDGE_PREPARED: 'готовим базу знаний',
    WAITING_FOR_REVIEW: 'ожидает проверки',
    REVIEW_COMPLETED: 'проверка завершена',
    PUBLISHED: 'опубликовано',
    DONE: 'готово',
  };
  return labels[value] || 'идёт обработка';
};

export const liveStageLabel = (stage: WorkbenchWorkflowStageLiveState): string => {
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

export const stageStatusLabel = (stage: WorkbenchWorkflowStageLiveState): string => {
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

export const stageStatusTone = (stage: WorkbenchWorkflowStageLiveState): string => {
  const status = normalize(stage.status);
  if (status === 'completed') return 'border-emerald-500/25 bg-emerald-500/10';
  if (status === 'running') return 'border-sky-500/25 bg-sky-500/10';
  if (status === 'paused' || status === 'deferred' || status === 'pending' || status === 'unknown') {
    return 'border-[var(--border-subtle)] bg-[var(--surface-elevated)]';
  }
  if (status === 'blocked') return 'border-amber-500/30 bg-amber-500/10';
  if (status === 'failed') return 'border-rose-500/30 bg-rose-500/10';
  return 'border-[var(--border-subtle)] bg-[var(--surface-elevated)]';
};

export const workflowStageHasStarted = (
  stage: WorkbenchWorkflowStageLiveState | null | undefined,
): boolean => {
  if (!stage) return false;

  const status = normalize(stage.status);
  if (!['pending', 'unknown'].includes(status)) return true;
  if ((stage.current ?? 0) > 0) return true;
  if ((stage.total ?? 0) > 0 && status !== 'unknown') return true;
  if (stage.started_at || stage.completed_at) return true;

  return false;
};

export const statusPillTone = (status: string): string => {
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

export const queueRowTone = (status: string): string => {
  const value = normalize(status);
  if (value === 'completed' || value === 'claim_observations_persisted') {
    return 'border-emerald-500/25 bg-emerald-500/10';
  }
  if (value === 'leased') return 'border-sky-500/25 bg-sky-500/10';
  if (value === 'ready' || value === 'deferred') {
    return 'border-[var(--border-subtle)] bg-[var(--surface-elevated)]';
  }
  if (value === 'retryable_failed' || value === 'user_action_required') {
    return 'border-amber-500/30 bg-amber-500/10';
  }
  if (value === 'terminal_failed' || value === 'failed') {
    return 'border-rose-500/30 bg-rose-500/10';
  }
  return 'border-[var(--border-subtle)] bg-[var(--surface-elevated)]';
};

export const attemptRowTone = (status: string): string => {
  const value = normalize(status);
  if (value === 'succeeded' || value === 'completed') {
    return 'border-emerald-500/25 bg-emerald-500/10';
  }
  if (value === 'leased' || value === 'running') {
    return 'border-sky-500/25 bg-sky-500/10';
  }
  if (value === 'ready') return 'border-[var(--border-subtle)] bg-[var(--surface-elevated)]';
  if (value === 'retryable_failed') return 'border-amber-500/30 bg-amber-500/10';
  if (value === 'terminal_failed' || value === 'failed') return 'border-rose-500/30 bg-rose-500/10';
  return 'border-[var(--border-subtle)] bg-[var(--surface-elevated)]';
};

export const queueStatusLabel = (status: string): string => {
  const value = normalize(status);
  const labels: Record<string, string> = {
    ready: 'ожидает обработки',
    leased: 'обрабатывается сейчас',
    completed: 'готова',
    claim_observations_persisted: 'готова',
    retryable_failed: 'нужна повторная попытка',
    terminal_failed: 'ошибка',
    failed: 'ошибка',
    deferred: 'отложена',
    user_action_required: 'требует решения',
  };
  return labels[value] || 'состояние уточняется';
};

export const queueStatusTone = (status: string): string => {
  const value = normalize(status);
  if (value === 'ready') return 'text-[var(--text-muted)]';
  if (value === 'leased') return 'text-[var(--accent-primary)]';
  if (value === 'completed' || value === 'claim_observations_persisted') {
    return 'text-emerald-600 dark:text-emerald-300';
  }
  if (value.includes('failed')) return 'text-amber-700 dark:text-amber-300';
  return 'text-[var(--text-secondary)]';
};

export const attemptStatusLabel = (status: string): string => {
  const value = normalize(status);
  const labels: Record<string, string> = {
    succeeded: 'ответ принят',
    completed: 'ответ принят',
    retryable_failed: 'ответ не принят, будет повторная попытка',
    terminal_failed: 'ответ не принят окончательно',
    failed: 'ошибка',
    leased: 'выполняется',
    running: 'выполняется',
    ready: 'ожидает запуска',
  };
  return labels[value] || 'состояние уточняется';
};

export const clusterStatusLabel = (status: string): string => {
  const labels: Record<string, string> = {
    planned: 'ещё не начинали',
    ready: 'ждёт обработки',
    comparing: 'сейчас объединяется',
    partially_compacted: 'частично готов',
    compacted: 'готов',
    blocked: 'нужно решение',
    failed: 'ошибка',
    waiting_user_model_choice: 'ждёт выбора модели',
  };
  return labels[normalize(status)] || status || 'состояние уточняется';
};

export const clusterStatusTitle = (status: string): string => {
  const label = clusterStatusLabel(status);
  return `${label.charAt(0).toUpperCase()}${label.slice(1)}`;
};

export const clusterStatusTone = (status: string): string => {
  const normalizedStatus = normalize(status);
  if (normalizedStatus === 'compacted') return 'border-emerald-500/30 bg-emerald-500/10';
  if (normalizedStatus === 'failed') return 'border-rose-500/30 bg-rose-500/10';
  if (normalizedStatus === 'blocked' || normalizedStatus === 'waiting_user_model_choice') {
    return 'border-amber-500/30 bg-amber-500/10';
  }
  if (normalizedStatus === 'comparing' || normalizedStatus === 'partially_compacted') {
    return 'border-sky-500/30 bg-sky-500/10';
  }
  return 'border-[var(--border-subtle)] bg-[var(--control-bg)]';
};

export const clusterHumanState = (
  cluster: {
    status: string;
    ready_work_item_count?: number;
    leased_work_item_count?: number;
    completed_work_item_count?: number;
    retryable_failed_work_item_count?: number;
    terminal_failed_work_item_count?: number;
    user_action_required_work_item_count?: number;
    active_compacted_node_count: number;
    member_count: number;
  },
): string => {
  if ((cluster.leased_work_item_count ?? 0) > 0) return 'ИИ прямо сейчас объединяет этот кластер';
  if ((cluster.terminal_failed_work_item_count ?? 0) > 0) return 'ошибка: этот кластер не удалось объединить';
  if ((cluster.user_action_required_work_item_count ?? 0) > 0) return 'нужно решение перед продолжением';
  if ((cluster.retryable_failed_work_item_count ?? 0) > 0) return 'была ошибка, кластер ждёт повторной попытки';
  if (normalize(cluster.status) === 'compacted') return 'готовый объединённый результат уже есть';
  if ((cluster.ready_work_item_count ?? 0) > 0) return 'ждёт очереди на объединение';
  if (cluster.active_compacted_node_count > 0) return 'часть результата уже готова';
  return 'подготовлен к объединению';
};

export const embeddingStatusLabel = (status: string): string => {
  const labels: Record<string, string> = {
    pending: 'ожидает',
    ready: 'готов',
    completed: 'готов',
    failed: 'ошибка',
    missing: 'нет вектора',
  };
  return labels[normalize(status)] || status || 'состояние уточняется';
};

export const nodeActivityLabel = (claim: WorkbenchClaimClusterClaimLiveState): string =>
  claim.node_active ? 'активен' : 'неактивен';

export const userErrorLabel = (errorKind: string | null | undefined): string => {
  const value = normalize(errorKind);
  const labels: Record<string, string> = {
    claim_builder_output_validation_failed:
      'ИИ вернул ответ, который не прошёл проверку качества',
    latin_text_not_supported_by_evidence:
      'В ответе появилась латиница, которой нет в процитированном фрагменте',
    evidence_block_not_source_excerpt:
      'Доказательство не является дословным фрагментом исходного текста',
    output_too_large: 'Ответ ИИ оказался слишком большим',
    input_too_large: 'Раздел слишком большой для текущей модели',
    rate_limited: 'Достигнут временный лимит ИИ-сервиса',
  };
  return labels[value] || (errorKind ? 'Нужна повторная обработка' : '—');
};
