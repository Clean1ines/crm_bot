export const formatClaimBuilderNumber = (value: number): string =>
  new Intl.NumberFormat('ru-RU').format(Math.max(0, Math.floor(value || 0)));

export const formatClaimBuilderMilliseconds = (
  value: number | null | undefined,
): string => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return '—';
  }
  return `${(value / 1000).toFixed(1)} сек.`;
};

const normalize = (value: string | null | undefined): string =>
  (value || '').trim().toLowerCase();

export const claimBuilderSectionStatusLabel = (status: string): string => {
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
  return labels[normalize(status)] || 'состояние уточняется';
};

export const claimBuilderSectionStatusTone = (status: string): string => {
  const value = normalize(status);
  if (value === 'ready') return 'text-[var(--text-muted)]';
  if (value === 'leased') return 'text-[var(--accent-primary)]';
  if (value === 'completed' || value === 'claim_observations_persisted') {
    return 'text-emerald-600 dark:text-emerald-300';
  }
  if (value.includes('failed')) return 'text-amber-700 dark:text-amber-300';
  return 'text-[var(--text-secondary)]';
};

export const claimBuilderSectionRowTone = (status: string): string => {
  const value = normalize(status);
  if (value === 'completed' || value === 'claim_observations_persisted') {
    return 'border-emerald-500/25 bg-emerald-500/10';
  }
  if (value === 'leased') {
    return 'border-sky-500/25 bg-sky-500/10';
  }
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

export const claimBuilderAttemptStatusLabel = (status: string): string => {
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
  return labels[normalize(status)] || 'состояние уточняется';
};

export const claimBuilderAttemptRowTone = (status: string): string => {
  const value = normalize(status);
  if (value === 'succeeded' || value === 'completed') {
    return 'border-emerald-500/25 bg-emerald-500/10';
  }
  if (value === 'leased' || value === 'running') {
    return 'border-sky-500/25 bg-sky-500/10';
  }
  if (value === 'ready') {
    return 'border-[var(--border-subtle)] bg-[var(--surface-elevated)]';
  }
  if (value === 'retryable_failed') {
    return 'border-amber-500/30 bg-amber-500/10';
  }
  if (value === 'terminal_failed' || value === 'failed') {
    return 'border-rose-500/30 bg-rose-500/10';
  }
  return 'border-[var(--border-subtle)] bg-[var(--surface-elevated)]';
};

export const claimBuilderUserErrorLabel = (
  errorKind: string | null | undefined,
): string => {
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
  return labels[normalize(errorKind)] || (errorKind ? 'Нужна повторная обработка' : '—');
};
