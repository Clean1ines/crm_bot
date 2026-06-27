import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Clock3, FileText, Trash2, Zap } from 'lucide-react';

import { t } from '@shared/i18n';
import {
  type KnowledgeSourceUnit,
  type KnowledgeSourceUnitsResponse,
  type KnowledgeAnswerDraftsResponse,
  type WorkbenchWorkflowActionLiveState,
  type WorkbenchWorkflowLiveStateResponse,
  type WorkbenchWorkflowStageLiveState,
  type WorkbenchSectionQueueItemLiveState,
  type WorkbenchLlmAttemptLiveState,
  type WorkbenchClaimClusterClaimLiveState,
} from '@shared/api/modules/knowledge';

type DocCardDocument = {
  id: string;
  file_name: string;
  file_size: number;
  preprocessing_mode?: string | null;
};

type KnowledgeDocumentCardProps = {
  doc: DocCardDocument;
  isDeletePending: boolean;
  onRequestDelete: () => void;
  onCardAction: (actionId: string) => void;
  onOpenCuration: (workflowRunId?: string | null) => void;
  workflowLiveState?: WorkbenchWorkflowLiveStateResponse | null;
  workflowLiveStateLoading?: boolean;
  workflowLiveStateError?: string | null;
  sourceUnitsResponse?: KnowledgeSourceUnitsResponse | null;
  answerDraftsResponse?: KnowledgeAnswerDraftsResponse | null;
  onStopProcessing: () => void;
  formatSize: (bytes: number) => string;
  knowledgeProcessingModeLabel: (value: string) => string;
};

type CapacityWindowDebugRow = {
  windowKey: string;
  provider: string;
  accountRef: string;
  modelRef: string;
  status: string;
  remainingMinuteRequests: number | null;
  remainingMinuteTokens: number | null;
  minuteResetAt: string | null;
  remainingDailyRequests: number | null;
  remainingDailyTokens: number | null;
  dailyResetAt: string | null;
  lastAttemptId: string | null;
  lastErrorKind: string | null;
  lastTotalTokens: number;
  lastObservedAtMs: number;
};


const formatNumber = (value: number): string =>
  new Intl.NumberFormat('ru-RU').format(Math.max(0, Math.floor(value || 0)));

const formatDuration = (seconds: number): string => {
  const safeSeconds = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const restSeconds = safeSeconds % 60;

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${restSeconds
      .toString()
      .padStart(2, '0')}`;
  }

  return `${minutes}:${restSeconds.toString().padStart(2, '0')}`;
};

const formatMilliseconds = (value: number | null | undefined): string => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return '—';
  }
  return `${(value / 1000).toFixed(1)} сек.`;
};

const formatNullableNumber = (value: number | null | undefined): string => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return formatNumber(value);
};

const formatResetCountdown = (
  resetAt: string | null | undefined,
  nowMs: number,
): string => {
  if (!resetAt) return 'reset unknown';

  const resetAtMs = Date.parse(resetAt);
  if (!Number.isFinite(resetAtMs)) return 'reset invalid';

  const secondsUntilReset = Math.ceil((resetAtMs - nowMs) / 1000);
  if (secondsUntilReset <= 0) return 'reset due';

  return `reset через ${formatDuration(secondsUntilReset)}`;
};


const normalize = (value: string | null | undefined): string =>
  (value || '').trim().toLowerCase();

const normalizeUpper = (value: string | null | undefined): string =>
  (value || '').trim().toUpperCase();

const workflowStatusLabel = (status: string | null | undefined): string => {
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

const phaseLabel = (phase: string | null | undefined): string => {
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

const liveStageLabel = (stage: WorkbenchWorkflowStageLiveState): string => {
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

const stageStatusLabel = (stage: WorkbenchWorkflowStageLiveState): string => {
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

const stageStatusTone = (stage: WorkbenchWorkflowStageLiveState): string => {
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

const statusPillTone = (status: string): string => {
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

const queueRowTone = (status: string): string => {
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

const attemptRowTone = (status: string): string => {
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


const queueStatusLabel = (status: string): string => {
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

const queueStatusTone = (status: string): string => {
  const value = normalize(status);
  if (value === 'ready') return 'text-[var(--text-muted)]';
  if (value === 'leased') return 'text-[var(--accent-primary)]';
  if (value === 'completed' || value === 'claim_observations_persisted') {
    return 'text-emerald-600 dark:text-emerald-300';
  }
  if (value.includes('failed')) return 'text-amber-700 dark:text-amber-300';
  return 'text-[var(--text-secondary)]';
};

const attemptStatusLabel = (status: string): string => {
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

const clusterStatusLabel = (status: string): string => {
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

const clusterStatusTitle = (status: string): string => {
  const label = clusterStatusLabel(status);
  return `${label.charAt(0).toUpperCase()}${label.slice(1)}`;
};

const clusterStatusTone = (status: string): string => {
  const normalizedStatus = normalize(status);
  if (normalizedStatus === 'compacted') {
    return 'border-emerald-500/30 bg-emerald-500/10';
  }
  if (normalizedStatus === 'failed') {
    return 'border-rose-500/30 bg-rose-500/10';
  }
  if (
    normalizedStatus === 'blocked' ||
    normalizedStatus === 'waiting_user_model_choice'
  ) {
    return 'border-amber-500/30 bg-amber-500/10';
  }
  if (
    normalizedStatus === 'comparing' ||
    normalizedStatus === 'partially_compacted'
  ) {
    return 'border-sky-500/30 bg-sky-500/10';
  }
  return 'border-[var(--border-subtle)] bg-[var(--control-bg)]';
};

const clusterHumanState = (
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

const embeddingStatusLabel = (status: string): string => {
  const labels: Record<string, string> = {
    pending: 'ожидает',
    ready: 'готов',
    completed: 'готов',
    failed: 'ошибка',
    missing: 'нет вектора',
  };
  return labels[normalize(status)] || status || 'состояние уточняется';
};

const nodeActivityLabel = (claim: WorkbenchClaimClusterClaimLiveState): string =>
  claim.node_active ? 'активен' : 'неактивен';


const userErrorLabel = (errorKind: string | null | undefined): string => {
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



const liveActionLabel = (action: WorkbenchWorkflowActionLiveState): string => {
  const labels: Record<string, string> = {
    pause_processing: 'Пауза',
    resume_processing: 'Продолжить',
    cancel_processing: 'Остановить',
    open_curation: 'Открыть проверку',
    publish_ready: 'Опубликовать',
    open_published_surfaces: 'Опубликованное',
    confirm_degraded_fallback: 'Продолжить на упрощённой модели',
    delete_document: 'Удалить',
  };
  return labels[action.action_id] || action.action_id;
};

const disabledActionTitle = (action: WorkbenchWorkflowActionLiveState): string => {
  if (action.enabled) return liveActionLabel(action);

  const labels: Record<string, string> = {
    not_paused: 'Доступно только когда обработка на паузе',
    not_running: 'Сейчас действие недоступно',
    terminal_workflow: 'Обработка уже завершена или остановлена',
    preview_not_ready: 'Проверка будет доступна после подготовки предпросмотра',
    workflow_missing: 'Рабочий процесс ещё не создан',
  };
  return labels[action.reason_code || ''] || 'Сейчас недоступно';
};

const canRunLiveAction = (action: WorkbenchWorkflowActionLiveState): boolean =>
  action.enabled;

const liveActionClassName = (action: WorkbenchWorkflowActionLiveState): string => {
  const base =
    'rounded-full px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50';

  if (action.action_id === 'cancel_processing' || action.action_id === 'delete_document') {
    return `${base} bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)] hover:opacity-80`;
  }

  if (action.action_id === 'open_curation' || action.action_id === 'publish_ready') {
    return `${base} bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/20`;
  }

  if (action.action_id === 'confirm_degraded_fallback') {
    return `${base} bg-amber-500/10 text-amber-700 hover:bg-amber-500/20 dark:text-amber-300`;
  }

  return `${base} bg-[var(--control-bg)] text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)]`;
};

const sourceUnitTitle = (unit: KnowledgeSourceUnit | null): string =>
  unit?.title?.trim() || 'Без заголовка';

const sectionDisplayNumber = (index: number): string => formatNumber(index + 1);


type DraftClaimRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const firstTextField = (
  record: DraftClaimRecord,
  keys: readonly string[],
): string | null => {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
};

const firstStringArrayField = (
  record: DraftClaimRecord,
  keys: readonly string[],
): string[] => {
  for (const key of keys) {
    const value = record[key];
    if (Array.isArray(value)) {
      return value.filter(
        (item): item is string => typeof item === 'string' && item.trim().length > 0,
      );
    }
  }
  return [];
};

const collectDraftClaims = (
  response: KnowledgeAnswerDraftsResponse | null,
): DraftClaimRecord[] => {
  if (!response) return [];

  const payload = response as unknown;
  if (Array.isArray(payload)) {
    return payload.filter(isRecord);
  }

  if (!isRecord(payload)) return [];

  const containers = [
    payload.draft_claims,
    payload.claims,
    payload.items,
    payload.fragments,
    payload.drafts,
    payload.answers,
  ];

  for (const container of containers) {
    if (Array.isArray(container)) {
      return container.filter(isRecord);
    }
  }

  return [];
};

const draftClaimSourceRef = (claim: DraftClaimRecord): string | null =>
  firstTextField(claim, [
    'source_unit_ref',
    'source_unit_id',
    'section_id',
    'source_ref',
    'sourceUnitRef',
    'sourceUnitId',
  ]);

const draftClaimTitle = (claim: DraftClaimRecord, index: number): string =>
  firstTextField(claim, ['title', 'claim_title', 'question', 'canonical_question']) ||
  `Утверждение ${formatNumber(index + 1)}`;

const draftClaimText = (claim: DraftClaimRecord): string =>
  firstTextField(claim, [
    'claim',
    'claim_text',
    'canonical_claim',
    'answer',
    'content',
    'text',
    'body',
  ]) || 'Текст утверждения недоступен';

const draftClaimEvidence = (claim: DraftClaimRecord): string | null =>
  firstTextField(claim, [
    'evidence_block',
    'source_excerpt',
    'evidence',
    'quote',
    'source_quote',
  ]);

const draftClaimQuestions = (claim: DraftClaimRecord): string[] =>
  firstStringArrayField(claim, [
    'possible_questions',
    'questions',
    'similar_questions',
    'queries',
  ]);

const draftClaimKey = (claim: DraftClaimRecord, index: number): string =>
  firstTextField(claim, ['observation_ref', 'id', 'claim_id', 'ref']) ||
  `draft-claim-${index}`;

export const KnowledgeDocumentCard: React.FC<KnowledgeDocumentCardProps> = ({
  doc,
  isDeletePending,
  onRequestDelete,
  onCardAction,
  onOpenCuration,
  onStopProcessing,
  workflowLiveState,
  workflowLiveStateLoading = false,
  workflowLiveStateError = null,
  sourceUnitsResponse = null,
  answerDraftsResponse = null,
  formatSize,
  knowledgeProcessingModeLabel,
}) => {
  const workflow = workflowLiveState?.workflow ?? null;
  const timer = workflow?.timer ?? null;
  const timerStartedAt = timer?.current_active_started_at ?? null;
  const timerStartedAtMs = timerStartedAt ? Date.parse(timerStartedAt) : Number.NaN;
  const isLiveTimer = Boolean(timer?.is_live && timerStartedAt);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!workflow) return undefined;

    setNowMs(Date.now());
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [workflow, timerStartedAt, workflow?.workflow_run_id]);

  const workflowStatus = workflow?.workflow_status ?? null;
  const currentPhase = workflow?.current_phase ?? null;
  const stages = workflow?.stages ?? [];
  const lanes = workflow?.section_lanes ?? [];
  const attempts = workflow?.llm_attempts ?? [];
  const capacityWindowRows = useMemo((): CapacityWindowDebugRow[] => {
    const rows = new Map<string, CapacityWindowDebugRow>();

    for (const attempt of attempts) {
      const provider = attempt.model_provider?.trim() || 'unknown-provider';
      const accountRef = attempt.account_ref?.trim() || 'unknown-account';
      const modelRef = attempt.model_name?.trim() || 'unknown-model';

      if (
        provider === 'unknown-provider' &&
        accountRef === 'unknown-account' &&
        modelRef === 'unknown-model'
      ) {
        continue;
      }

      const windowKey = `${provider}:${accountRef}:${modelRef}`;
      const observedAtMs = Date.parse(
        attempt.completed_at || attempt.started_at || '',
      );
      const safeObservedAtMs = Number.isFinite(observedAtMs) ? observedAtMs : 0;
      const previous = rows.get(windowKey);

      if (previous && previous.lastObservedAtMs > safeObservedAtMs) {
        continue;
      }

      rows.set(windowKey, {
        windowKey,
        provider,
        accountRef,
        modelRef,
        status: attempt.status || 'unknown',
        remainingMinuteRequests:
          typeof attempt.remaining_minute_requests === 'number'
            ? attempt.remaining_minute_requests
            : previous?.remainingMinuteRequests ?? null,
        remainingMinuteTokens:
          typeof attempt.remaining_minute_tokens === 'number'
            ? attempt.remaining_minute_tokens
            : previous?.remainingMinuteTokens ?? null,
        minuteResetAt: attempt.minute_reset_at ?? previous?.minuteResetAt ?? null,
        remainingDailyRequests:
          typeof attempt.remaining_daily_requests === 'number'
            ? attempt.remaining_daily_requests
            : previous?.remainingDailyRequests ?? null,
        remainingDailyTokens:
          typeof attempt.remaining_daily_tokens === 'number'
            ? attempt.remaining_daily_tokens
            : previous?.remainingDailyTokens ?? null,
        dailyResetAt: attempt.daily_reset_at ?? previous?.dailyResetAt ?? null,
        lastAttemptId: (attempt.node_run_id || previous?.lastAttemptId) ?? null,
        lastErrorKind: attempt.error_kind ?? previous?.lastErrorKind ?? null,
        lastTotalTokens: Math.max(0, attempt.total_tokens || 0),
        lastObservedAtMs: safeObservedAtMs,
      });
    }

    return Array.from(rows.values()).sort((left, right) =>
      left.windowKey.localeCompare(right.windowKey),
    );
  }, [attempts]);
  const actions = workflow?.actions ?? [];
  const hasClaimClusters = Array.isArray(workflow?.claim_clusters);
  const claimClusters = workflow?.claim_clusters ?? [];
  const nestedCompactionComparisons = claimClusters.flatMap(
    (cluster) => cluster.comparisons,
  );
  const hasCompactionComparisons =
    Array.isArray(workflow?.claim_compaction_comparisons) ||
    claimClusters.some((cluster) => Array.isArray(cluster.comparisons));
  const compactionComparisons =
    workflow?.claim_compaction_comparisons ?? nestedCompactionComparisons;
  const usage = workflow?.usage ?? null;
  const sourceUnits = sourceUnitsResponse?.source_units ?? [];
  const draftClaims = useMemo(
    () => collectDraftClaims(answerDraftsResponse),
    [answerDraftsResponse],
  );


  const sourceUnitByIndex = useMemo(() => {
    const map = new Map<number, KnowledgeSourceUnit>();
    sourceUnits.forEach((unit) => map.set(unit.source_index, unit));
    return map;
  }, [sourceUnits]);

  const sourceUnitById = useMemo(() => {
    const map = new Map<string, KnowledgeSourceUnit>();
    sourceUnits.forEach((unit) => map.set(unit.id, unit));
    return map;
  }, [sourceUnits]);

  const draftClaimsBySourceRef = useMemo(() => {
    const map = new Map<string, DraftClaimRecord[]>();
    draftClaims.forEach((claim) => {
      const sourceRef = draftClaimSourceRef(claim);
      if (!sourceRef) return;
      const existing = map.get(sourceRef) ?? [];
      existing.push(claim);
      map.set(sourceRef, existing);
    });
    return map;
  }, [draftClaims]);

  const sourceUnitForSection = (
    item: WorkbenchSectionQueueItemLiveState,
  ): KnowledgeSourceUnit | null =>
    sourceUnitById.get(item.section_id) ??
    sourceUnitByIndex.get(item.section_index) ??
    null;

  const draftClaimsForSection = (
    sourceUnit: KnowledgeSourceUnit | null,
    sectionId: string,
  ): DraftClaimRecord[] => {
    const candidates = [
      sourceUnit?.id,
      sectionId,
      sourceUnit ? (sourceUnit as unknown as Record<string, unknown>).unit_ref : null,
      sourceUnit ? (sourceUnit as unknown as Record<string, unknown>).source_unit_ref : null,
    ].filter((value): value is string => typeof value === 'string' && value.trim().length > 0);

    const claims: DraftClaimRecord[] = [];
    const seen = new Set<string>();
    candidates.forEach((candidate) => {
      (draftClaimsBySourceRef.get(candidate) ?? []).forEach((claim, index) => {
        const key = draftClaimKey(claim, index);
        if (seen.has(key)) return;
        seen.add(key);
        claims.push(claim);
      });
    });
    return claims;
  };

  const sourceStage = stages.find((stage) => stage.id === 'source_ingestion') ?? null;
  const claimStage =
    stages.find((stage) => stage.id === 'prompt_a_claim_extraction') ?? null;
  const embeddingStage =
    stages.find((stage) => stage.id === 'draft_claim_embeddings') ?? null;
  const clusterStage =
    stages.find((stage) => stage.id === 'draft_claim_clustering') ?? null;
  const compactionStage =
    stages.find((stage) => stage.id === 'draft_claim_compaction') ?? null;
  const previewStage = stages.find((stage) => stage.id === 'cluster_preview') ?? null;
  const clusteredClaims = claimClusters.flatMap(
    (cluster) => cluster.claims ?? cluster.members,
  );
  const clusteredClaimCount = claimClusters.reduce(
    (total, cluster) => total + cluster.member_count,
    0,
  );
  const embeddedClaimCount = clusteredClaims.filter(
    (claim) =>
      Boolean(claim.embedding_ref) &&
      !['failed', 'missing', 'pending'].includes(normalize(claim.embedding_status)),
  ).length;
  const resolvedComparisonCount = compactionComparisons.filter(
    (comparison) =>
      !['pending', 'waiting_user_model_choice'].includes(normalize(comparison.status)),
  ).length;
  const compactedClusterCount = claimClusters.filter(
    (cluster) => normalize(cluster.status) === 'compacted',
  ).length;
  const compactionReady = claimClusters.reduce(
    (total, cluster) => total + (cluster.ready_work_item_count ?? 0),
    0,
  );
  const compactionLeased = claimClusters.reduce(
    (total, cluster) => total + (cluster.leased_work_item_count ?? 0),
    0,
  );
  const compactionDone = claimClusters.reduce(
    (total, cluster) => total + (cluster.completed_work_item_count ?? 0),
    0,
  );
  const compactionRetry = claimClusters.reduce(
    (total, cluster) => total + (cluster.retryable_failed_work_item_count ?? 0),
    0,
  );
  const compactionFailed = claimClusters.reduce(
    (total, cluster) => total + (cluster.terminal_failed_work_item_count ?? 0),
    0,
  );
  const compactionNeedsDecision = claimClusters.reduce(
    (total, cluster) => total + (cluster.user_action_required_work_item_count ?? 0),
    0,
  );
  const compactedClaimPreviewCount = claimClusters.reduce(
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
        : draftClaims.map((claim, index) => ({
            key: draftClaimKey(claim, index),
            text: draftClaimText(claim),
          }))
      )
        .filter((fact) => fact.text.trim().length > 0)
        .map((fact) => [fact.key, fact]),
    ).values(),
  );
  const finalCompactedFacts = claimClusters.flatMap((cluster) =>
    (cluster.compacted_claims ?? [])
      .filter((claim) => claim.active)
      .map((claim) => ({
        ...claim,
        cluster_ref: cluster.cluster_ref,
      })),
  );
  const compactionProgressPercent =
    claimClusters.length > 0
      ? Math.round((compactedClusterCount / claimClusters.length) * 100)
      : 0;
  const compactionAttention =
    compactionRetry + compactionFailed + compactionNeedsDecision;
  const compactionIsComplete =
    claimClusters.length > 0 && compactedClusterCount === claimClusters.length;
  const compactionPanelTone =
    workflow?.curation.available || compactionIsComplete
      ? 'border-emerald-500/30 bg-emerald-500/10'
      : compactionFailed > 0
        ? 'border-rose-500/30 bg-rose-500/10'
        : compactionAttention > 0
          ? 'border-amber-500/30 bg-amber-500/10'
          : compactionLeased > 0
            ? 'border-sky-500/30 bg-sky-500/10'
            : 'border-[var(--border-strong)] bg-[var(--surface-secondary)]';
  const compactionSummaryText =
    compactionLeased > 0
      ? `Сейчас ИИ объединяет ${formatNumber(compactionLeased)} кластер(а).`
      : compactionReady > 0
        ? `Ждут объединения ${formatNumber(compactionReady)} кластер(а).`
        : compactedClusterCount === claimClusters.length && claimClusters.length > 0
          ? 'Все кластеры объединены.'
          : 'Состояние объединения уточняется.';
  const compactionUserSummary = workflow?.curation.available
    ? 'Объединение завершено — знания готовы к ручной проверке.'
    : compactionFailed > 0
      ? 'Часть кластеров завершилась с ошибкой.'
      : compactionNeedsDecision > 0
        ? 'Для продолжения нужно решение пользователя.'
        : compactionLeased > 0
          ? 'ИИ сейчас объединяет связанные факты.'
          : compactionReady > 0
            ? 'Кластеры ждут своей очереди на объединение.'
            : compactionIsComplete
              ? 'Все кластеры объединены.'
              : compactionSummaryText;
  const compactionLlmAttempts = attempts.filter(
    (attempt) => attempt.node_name === 'knowledge_workbench.draft_claim_compaction',
  );
  const compactionSucceededAttempts = compactionLlmAttempts.filter(
    (attempt) => normalize(attempt.status) === 'succeeded',
  ).length;
  const compactionRunningAttempts = compactionLlmAttempts.filter((attempt) =>
    ['leased', 'running', 'ready'].includes(normalize(attempt.status)),
  ).length;
  const compactionTokens = compactionLlmAttempts.reduce(
    (total, attempt) => total + Math.max(0, attempt.total_tokens || 0),
    0,
  );

  const displayedStageCounts = (
    stage: WorkbenchWorkflowStageLiveState,
  ): { current: number; total: number } => {
    if (stage.id === 'draft_claim_embeddings' && hasClaimClusters) {
      return { current: embeddedClaimCount, total: clusteredClaimCount };
    }
    if (stage.id === 'draft_claim_clustering' && hasClaimClusters) {
      return { current: claimClusters.length, total: claimClusters.length };
    }
    if (stage.id === 'draft_claim_compaction' && hasCompactionComparisons) {
      return {
        current: compactedClusterCount,
        total: claimClusters.length,
      };
    }
    return { current: stage.current, total: stage.total };
  };

  const sectionItems = lanes
    .flatMap((lane) => lane.items)
    .sort((left, right) => left.section_index - right.section_index);

  const laneReady = lanes.reduce((total, lane) => total + lane.ready_count, 0);
  const laneLeased = lanes.reduce((total, lane) => total + lane.leased_count, 0);
  const laneDone = lanes.reduce((total, lane) => total + lane.done_count, 0);
  const laneFailed = lanes.reduce((total, lane) => total + lane.failed_count, 0);
  const laneWaiting = lanes.reduce((total, lane) => total + lane.waiting_count, 0);
  const observedLaneTotal = laneReady + laneLeased + laneDone + laneFailed + laneWaiting;

  const sectionProgressTotal = Math.max(
    claimStage?.total ?? 0,
    sourceStage?.total ?? 0,
    observedLaneTotal,
  );
  const sectionProgressCurrent = Math.max(claimStage?.current ?? 0, laneDone);
  const sectionProgressPercent =
    sectionProgressTotal > 0
      ? Math.max(
          0,
          Math.min(
            100,
            Math.round((sectionProgressCurrent / sectionProgressTotal) * 100),
          ),
        )
      : 0;

  const baseElapsedSeconds = timer?.active_elapsed_seconds ?? 0;
  const activeElapsedSeconds =
    isLiveTimer && Number.isFinite(timerStartedAtMs)
      ? baseElapsedSeconds + Math.max(0, Math.floor((nowMs - timerStartedAtMs) / 1000))
      : baseElapsedSeconds;
  const elapsedText =
    activeElapsedSeconds > 0 || isLiveTimer ? formatDuration(activeElapsedSeconds) : '—';

  const fileSizeText = doc.file_size > 0 ? formatSize(doc.file_size) : 'размер недоступен';
  const attemptPromptTokens = attempts.reduce(
    (total, attempt) => total + Math.max(0, attempt.prompt_tokens || 0),
    0,
  );
  const attemptCompletionTokens = attempts.reduce(
    (total, attempt) => total + Math.max(0, attempt.completion_tokens || 0),
    0,
  );
  const attemptTotalTokens = attempts.reduce(
    (total, attempt) => total + Math.max(0, attempt.total_tokens || 0),
    0,
  );
  const totalLlmCalls = Math.max(usage?.total_llm_calls ?? 0, attempts.length);
  const totalPromptTokens = Math.max(
    usage?.total_prompt_tokens ?? 0,
    attemptPromptTokens,
  );
  const totalCompletionTokens = Math.max(
    usage?.total_completion_tokens ?? 0,
    attemptCompletionTokens,
  );
  const totalTokens = Math.max(
    usage?.total_tokens ?? 0,
    attemptTotalTokens,
    totalPromptTokens + totalCompletionTokens,
  );
  const llmUsageText =
    totalTokens > 0
      ? `${formatNumber(totalTokens)} токенов · ${formatNumber(totalLlmCalls)} выз.`
      : totalLlmCalls > 0
        ? `${formatNumber(totalLlmCalls)} выз. · токены пока не записаны`
        : 'вызовов ещё не было';

  const headline = workflow
    ? workflowStatusLabel(workflowStatus)
    : workflowLiveStateLoading
      ? 'Загружаем состояние обработки'
      : 'Состояние обработки пока недоступно';

  const phaseText = workflow
    ? phaseLabel(currentPhase)
    : 'после загрузки здесь будет показан текущий этап';

  const sectionProgressText =
    sectionProgressTotal > 0
      ? `${formatNumber(sectionProgressCurrent)} из ${formatNumber(sectionProgressTotal)} разделов`
      : 'разделы ещё не подготовлены';

  const resultSummaryText = workflow
    ? hasClaimClusters || hasCompactionComparisons
      ? `Черновики утверждений: ${formatNumber(
          hasClaimClusters ? clusteredClaimCount : claimStage?.current ?? 0,
        )} · Векторы: ${formatNumber(
          hasClaimClusters ? embeddedClaimCount : embeddingStage?.current ?? 0,
        )} · Группы: ${formatNumber(
          hasClaimClusters ? claimClusters.length : clusterStage?.current ?? 0,
        )} · Сравнения: ${formatNumber(
          hasCompactionComparisons
            ? resolvedComparisonCount
            : compactionStage?.current ?? 0,
        )} / ${formatNumber(
          hasCompactionComparisons
            ? compactionComparisons.length
            : compactionStage?.total ?? 0,
        )}`
      : `Черновики утверждений: ${formatNumber(claimStage?.current ?? 0)} · Векторы: ${formatNumber(
          embeddingStage?.current ?? 0,
        )} · Группы: ${formatNumber(clusterStage?.current ?? 0)} · Объединённые знания: ${formatNumber(
          compactionStage?.current ?? 0,
        )} · Предпросмотр: ${
          (previewStage?.current ?? 0) > 0 ? 'готов' : 'ещё не готов'
        }`
    : 'Нет данных обработки';

  const handleLiveAction = (action: WorkbenchWorkflowActionLiveState): void => {
    if (!canRunLiveAction(action)) return;

    if (action.action_id === 'cancel_processing' || action.action_id === 'pause_processing') {
      onStopProcessing();
      return;
    }

    if (action.action_id === 'open_curation') {
      onOpenCuration(workflow?.curation.workflow_run_id ?? workflow?.workflow_run_id ?? null);
      return;
    }

    if (action.action_id === 'delete_document') {
      onRequestDelete();
      return;
    }

    onCardAction(action.action_id);
  };

  const attemptSectionIndex = (attempt: WorkbenchLlmAttemptLiveState): number | null => {
    if (!attempt.section_id) return null;
    const byId = sourceUnitById.get(attempt.section_id);
    if (byId) return byId.source_index;
    const bySection = sectionItems.find((item) => item.section_id === attempt.section_id);
    return bySection?.section_index ?? null;
  };

  return (
    <div
      id={`knowledge-doc-card-${doc.id}`}
      className="group w-full min-w-0 overflow-hidden rounded-2xl bg-[var(--surface-elevated)] p-4 break-words transition-all hover:shadow-lg sm:p-5"
    >
      <div className="mb-4 flex min-w-0 items-start justify-between gap-2">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--surface-secondary)] text-[var(--accent-primary)]">
          <FileText className="h-5 w-5" />
        </div>

        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          <span className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]">
            {workflowStatusLabel(workflowStatus)}
          </span>
          <button
            type="button"
            onClick={onRequestDelete}
            disabled={isDeletePending}
            title={t('common.actions.delete')}
            className="rounded-lg p-2 text-[var(--accent-danger-text)] transition-colors hover:bg-[var(--accent-danger-bg)] disabled:cursor-wait disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mb-3">
        <div className="flex min-w-0 items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="truncate font-semibold text-[var(--text-primary)]" title={doc.file_name}>
              {doc.file_name}
            </h3>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              {fileSizeText} · {knowledgeProcessingModeLabel(doc.preprocessing_mode || 'faq')}
            </p>
          </div>
        </div>

        <div className="mt-2 rounded-xl bg-[var(--surface-secondary)] px-3 py-2 text-sm leading-relaxed text-[var(--text-secondary)]">
          <div className="font-medium text-[var(--text-primary)]">Что происходит с документом</div>
          <p className="mt-1">
            {headline}. Сейчас: {phaseText}.
          </p>
          {laneFailed > 0 && (
            <p className="mt-1 text-amber-700 dark:text-amber-300">
              {formatNumber(laneFailed)} раздела требуют повторной обработки.
            </p>
          )}
        </div>
      </div>

      <div className="mb-4 space-y-3">
        {workflowLiveStateError && (
          <div className="flex gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none" />
            <span>{workflowLiveStateError}</span>
          </div>
        )}

        <div className="grid gap-2 text-xs [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
          <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
              <Clock3 className="h-3.5 w-3.5" />
              Активная обработка
            </div>
            <div className="text-[var(--text-muted)]">{elapsedText}</div>
          </div>

          <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
              <Zap className="h-3.5 w-3.5" />
              ИИ
            </div>
            <div className="text-[var(--text-muted)]">{llmUsageText}</div>
          </div>

          <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-1 font-medium text-[var(--text-primary)]">Прогресс</div>
            <div className="text-[var(--text-muted)]">
              Извлечение утверждений: {sectionProgressText}
              {laneLeased > 0 ? ` · сейчас обрабатывается ${formatNumber(laneLeased)}` : ''}
              {laneReady > 0 ? ` · ожидает ${formatNumber(laneReady)}` : ''}
              {laneWaiting > 0 ? ` · отложено ${formatNumber(laneWaiting)}` : ''}
              {laneFailed > 0 ? ` · ошибок ${formatNumber(laneFailed)}` : ''}
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--control-bg)]">
              <div
                className="h-full rounded-full bg-[var(--accent-primary)]"
                style={{ width: `${sectionProgressPercent}%` }}
              />
            </div>
            <div className="mt-1 text-[var(--text-muted)]">{sectionProgressPercent}%</div>
          </div>

          {claimClusters.length > 0 ? (
            <div className={`min-w-0 rounded-xl border p-3 ${compactionPanelTone}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="font-medium text-[var(--text-primary)]">
                    Объединение знаний
                  </div>
                  <div className="mt-1 text-[var(--text-secondary)]">
                    {compactionUserSummary}
                  </div>
                </div>
                <div className="rounded-full bg-[var(--surface-elevated)] px-2.5 py-1 font-medium text-[var(--text-primary)]">
                  {formatNumber(compactionProgressPercent)}% кластеров готово
                </div>
              </div>

              <div className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--surface-elevated)]">
                <div
                  className="h-full rounded-full bg-emerald-500 transition-[width]"
                  style={{ width: `${compactionProgressPercent}%` }}
                />
              </div>

              <div className="mt-3 grid gap-2 [grid-template-columns:repeat(auto-fit,minmax(120px,1fr))]">
                {[
                  ['В очереди', compactionReady, 'text-slate-600 dark:text-slate-300'],
                  ['Обрабатывается', compactionLeased, 'text-sky-700 dark:text-sky-300'],
                  ['Готово', compactedClusterCount, 'text-emerald-700 dark:text-emerald-300'],
                  ['Нужно внимание', compactionAttention, 'text-amber-700 dark:text-amber-300'],
                ].map(([label, value, tone]) => (
                  <div
                    key={String(label)}
                    className="rounded-lg bg-[var(--surface-elevated)] px-2.5 py-2"
                  >
                    <div className={`font-medium ${String(tone)}`}>{label}</div>
                    <div className="mt-0.5 text-lg font-semibold text-[var(--text-primary)]">
                      {formatNumber(Number(value))}
                    </div>
                  </div>
                ))}
              </div>

              {extractedFacts.length > 0 && (
                <section className="mt-3 rounded-lg bg-[var(--surface-elevated)] p-3">
                  <div className="font-medium text-[var(--text-primary)]">
                    Извлечённые факты: {formatNumber(extractedFacts.length)}
                  </div>
                  <div className="mt-2 max-h-64 space-y-2 overflow-y-auto pr-1">
                    {extractedFacts.map((fact, index) => (
                      <div
                        key={fact.key}
                        className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] px-3 py-2 text-[var(--text-secondary)]"
                      >
                        <span className="mr-2 text-[var(--text-muted)]">
                          {formatNumber(index + 1)}.
                        </span>
                        {fact.text}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {finalCompactedFacts.length > 0 && (
                <section className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
                  <div className="font-medium text-[var(--text-primary)]">
                    Итоговые факты: {formatNumber(finalCompactedFacts.length)}
                  </div>
                  <div className="mt-2 max-h-64 space-y-2 overflow-y-auto pr-1">
                    {finalCompactedFacts.map((fact, index) => (
                      <div
                        key={`${fact.cluster_ref}:${fact.node_ref}`}
                        className="rounded-lg bg-[var(--surface-elevated)] px-3 py-2"
                      >
                        <div className="text-[var(--text-primary)]">
                          <span className="mr-2 text-emerald-700 dark:text-emerald-300">
                            {formatNumber(index + 1)}.
                          </span>
                          {fact.claim}
                        </div>
                        <div className="mt-1 text-[11px] text-[var(--text-muted)]">
                          {fact.source_claim_refs.length > 1
                            ? `Объединено из ${formatNumber(fact.source_claim_refs.length)} фактов`
                            : 'Сохранён как отдельный факт'}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <div className="mt-3 text-[11px] text-[var(--text-muted)]">
                Кластеров: {formatNumber(claimClusters.length)}
                {' · '}завершено задач: {formatNumber(compactionDone)}
                {' · '}итоговых фактов: {formatNumber(compactedClaimPreviewCount)}
                {compactionLlmAttempts.length > 0
                  ? ` · запросов ИИ: ${formatNumber(compactionLlmAttempts.length)}`
                  : ''}
                {compactionSucceededAttempts > 0
                  ? ` · успешно ${formatNumber(compactionSucceededAttempts)}`
                  : ''}
                {compactionRunningAttempts > 0
                  ? ` · выполняется ${formatNumber(compactionRunningAttempts)}`
                  : ''}
                {compactionTokens > 0 ? ` · ${formatNumber(compactionTokens)} токенов` : ''}
              </div>
            </div>
          ) : null}

          {capacityWindowRows.length > 0 ? (
            <div className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="font-medium text-[var(--text-primary)]">
                    Capacity windows
                  </div>
                  <div className="text-[11px] text-[var(--text-muted)]">
                    Provider/account/model · остаток окна · таймер reset
                  </div>
                </div>
                <div className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
                  {formatNumber(capacityWindowRows.length)} окон
                </div>
              </div>

              <div className="space-y-1.5">
                {capacityWindowRows.map((row) => (
                  <div
                    key={row.windowKey}
                    className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="break-all font-mono text-[11px] text-[var(--text-primary)]">
                          {row.windowKey}
                        </div>
                        <div className="mt-1 text-[11px] text-[var(--text-muted)]">
                          status: {attemptStatusLabel(row.status)}
                          {row.lastErrorKind ? ` · error: ${row.lastErrorKind}` : ''}
                          {row.lastAttemptId ? ` · attempt: ${row.lastAttemptId}` : ''}
                        </div>
                      </div>
                      <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${statusPillTone(row.status)}`}>
                        {row.status}
                      </span>
                    </div>

                    <div className="mt-2 grid gap-1.5 text-[11px] [grid-template-columns:repeat(auto-fit,minmax(145px,1fr))]">
                      <div className="rounded-md bg-[var(--control-bg)] px-2 py-1">
                        TPM left:{' '}
                        <span className="font-semibold text-[var(--text-primary)]">
                          {formatNullableNumber(row.remainingMinuteTokens)}
                        </span>
                      </div>
                      <div className="rounded-md bg-[var(--control-bg)] px-2 py-1">
                        RPM left:{' '}
                        <span className="font-semibold text-[var(--text-primary)]">
                          {formatNullableNumber(row.remainingMinuteRequests)}
                        </span>
                      </div>
                      <div className="rounded-md bg-[var(--control-bg)] px-2 py-1">
                        minute:{' '}
                        <span className="font-semibold text-[var(--text-primary)]">
                          {formatResetCountdown(row.minuteResetAt, nowMs)}
                        </span>
                      </div>
                      <div className="rounded-md bg-[var(--control-bg)] px-2 py-1">
                        daily tokens:{' '}
                        <span className="font-semibold text-[var(--text-primary)]">
                          {formatNullableNumber(row.remainingDailyTokens)}
                        </span>
                      </div>
                      <div className="rounded-md bg-[var(--control-bg)] px-2 py-1">
                        daily req:{' '}
                        <span className="font-semibold text-[var(--text-primary)]">
                          {formatNullableNumber(row.remainingDailyRequests)}
                        </span>
                      </div>
                      <div className="rounded-md bg-[var(--control-bg)] px-2 py-1">
                        last total:{' '}
                        <span className="font-semibold text-[var(--text-primary)]">
                          {formatNullableNumber(row.lastTotalTokens)}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-1 font-medium text-[var(--text-primary)]">Итог</div>
            <div className="text-[var(--text-muted)]">{resultSummaryText}</div>
          </div>
        </div>

        {workflow && (
          <details
            className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-secondary)] break-words [overflow-wrap:anywhere]"
            open
          >
            <summary className="cursor-pointer list-none font-semibold text-[var(--text-primary)]">
              Подробности обработки
            </summary>

            <div className="mt-3 space-y-3">
              <section>
                <div className="mb-2 font-medium text-[var(--text-primary)]">
                  Этапы обработки
                </div>
                <div className="space-y-1.5">
                  {stages.map((stage, stageIndex) => {
                    const stageCounts = displayedStageCounts(stage);
                    return (
                      <details
                        key={stage.id}
                        className={`rounded-lg border px-3 py-2 ${stageStatusTone(stage)}`}
                      >
                        <summary className="cursor-pointer list-none">
                          <span className="flex flex-wrap items-center justify-between gap-2">
                            <span className="min-w-0">
                              <span className="font-semibold text-[var(--text-primary)]">
                                {formatNumber(stageIndex + 1)}. {liveStageLabel(stage)}
                              </span>
                              <span className="ml-2 text-[var(--text-muted)]">
                                {stageStatusLabel(stage)}
                                {stageCounts.total > 0 && stage.id !== 'cluster_preview'
                                  ? ` · ${formatNumber(stageCounts.current)} / ${formatNumber(
                                      stageCounts.total,
                                    )}`
                                  : ''}
                              </span>
                            </span>
                            <span className={`rounded-full px-2.5 py-1 font-medium ${statusPillTone(stage.status)}`}>
                              {stageStatusLabel(stage)}
                            </span>
                          </span>
                        </summary>
                        {stage.message && (
                          <div className="mt-2 text-[var(--text-secondary)]">
                            {stage.message}
                          </div>
                        )}
                      </details>
                    );
                  })}
                </div>
              </section>

              {hasClaimClusters && (
                <details className="rounded-lg bg-[var(--surface-elevated)] p-2" open>
                  <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                    Кластеры утверждений: {formatNumber(claimClusters.length)}
                  </summary>
                  <div className="mt-2 space-y-2">
                    {claimClusters.length === 0 && (
                      <div className="text-[var(--text-muted)]">
                        Кластеры ещё не сформированы.
                      </div>
                    )}
                    {claimClusters.map((cluster, clusterIndex) => (
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
                                {clusterHumanState(cluster)} · утверждений:{' '}
                                {formatNumber(cluster.member_count)}
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
                          <div>
                            compacted-узлов:{' '}
                            {formatNumber(cluster.active_compacted_node_count)}
                          </div>
                          <div>
                            сравнений: {formatNumber(cluster.comparison_count)} · ожидают:{' '}
                            {formatNumber(cluster.pending_comparison_count)}
                          </div>
                          <div>work items: {formatNumber(cluster.work_item_count)}</div>
                        </div>
                        <div className="mt-2 space-y-2">
                          {(cluster.claims ?? cluster.members).map((claim) => (
                            <details
                              key={claim.observation_ref}
                              className="rounded bg-[var(--surface-elevated)] p-2"
                            >
                              <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                                {claim.claim}
                              </summary>
                              <div className="mt-2 space-y-2 text-[var(--text-secondary)]">
                                <div>
                                  <span className="font-medium text-[var(--text-primary)]">
                                    Гранулярность:
                                  </span>{' '}
                                  {claim.granularity}
                                </div>
                                <div>
                                  <div className="font-medium text-[var(--text-primary)]">
                                    Возможные вопросы
                                  </div>
                                  {claim.possible_questions.length > 0 ? (
                                    <ul className="mt-1 list-disc pl-5">
                                      {claim.possible_questions.map((question) => (
                                        <li key={question}>{question}</li>
                                      ))}
                                    </ul>
                                  ) : (
                                    <div className="mt-1 text-[var(--text-muted)]">—</div>
                                  )}
                                </div>
                                <div>
                                  <div className="font-medium text-[var(--text-primary)]">
                                    Исключения
                                  </div>
                                  {claim.exclusion_scope.length > 0 ? (
                                    <ul className="mt-1 list-disc pl-5">
                                      {claim.exclusion_scope.map((exclusion) => (
                                        <li key={exclusion}>{exclusion}</li>
                                      ))}
                                    </ul>
                                  ) : (
                                    <div className="mt-1 text-[var(--text-muted)]">—</div>
                                  )}
                                </div>
                                <div>
                                  <div className="font-medium text-[var(--text-primary)]">
                                    Источник
                                  </div>
                                  <div>{claim.source_unit_ref}</div>
                                  <div className="text-[var(--text-muted)]">
                                    документ: {claim.source_document_ref}
                                  </div>
                                </div>
                                <div>
                                  <div className="font-medium text-[var(--text-primary)]">
                                    Embedding
                                  </div>
                                  <div>
                                    {claim.embedding_model_id || 'модель не указана'}
                                    {claim.embedding_dimensions
                                      ? ` · ${formatNumber(claim.embedding_dimensions)} изм.`
                                      : ''}
                                    {' · '}
                                    {embeddingStatusLabel(claim.embedding_status)}
                                  </div>
                                  {claim.embedding_ref && (
                                    <div className="font-mono text-[11px] text-[var(--text-muted)]">
                                      {claim.embedding_ref}
                                    </div>
                                  )}
                                </div>
                                <div>
                                  <div className="font-medium text-[var(--text-primary)]">
                                    Узел compaction
                                  </div>
                                  <div>
                                    {claim.node_kind || 'тип не указан'} ·{' '}
                                    {nodeActivityLabel(claim)} · {claim.node_status}
                                  </div>
                                  {claim.node_ref && (
                                    <div className="font-mono text-[11px] text-[var(--text-muted)]">
                                      {claim.node_ref}
                                    </div>
                                  )}
                                </div>
                              </div>
                            </details>
                          ))}
                        </div>
                      </details>
                    ))}
                  </div>
                </details>
              )}

              {sectionItems.length > 0 && (
                <details className="rounded-lg bg-[var(--surface-elevated)] p-2" open>
                  <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                    Разделы документа: {formatNumber(sectionItems.length)}
                  </summary>
                  <div className="mt-2 space-y-1">
                    {sectionItems.map((item) => {
                      const sourceUnit = sourceUnitForSection(item);
                      const sectionClaims = draftClaimsForSection(sourceUnit, item.section_id);
                      return (
                        <details
                          key={item.queue_item_id}
                          className={`rounded-lg border px-3 py-2 ${queueRowTone(item.status)}`}
                        >
                          <summary className="cursor-pointer list-none">
                            <span className="font-medium text-[var(--text-primary)]">
                              Раздел {sectionDisplayNumber(item.section_index)}
                            </span>
                            <span className={`ml-2 ${queueStatusTone(item.status)}`}>
                              {queueStatusLabel(item.status)}
                            </span>
                            {item.attempt_count > 0 && (
                              <span className="ml-2 text-[var(--text-muted)]">
                                попыток: {formatNumber(item.attempt_count)}
                              </span>
                            )}
                          </summary>

                          <div className="mt-2 space-y-2">
                            {item.error_kind && (
                              <div className="rounded bg-amber-500/10 px-2 py-1 text-amber-700 dark:text-amber-300">
                                {userErrorLabel(item.error_kind)}
                              </div>
                            )}

                            {sourceUnit ? (
                              <div>
                                <div className="mb-1 font-medium text-[var(--text-primary)]">
                                  {sourceUnitTitle(sourceUnit)}
                                </div>
                                <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-[var(--control-bg)] p-2 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                                  {sourceUnit.content}
                                </pre>
                              </div>
                            ) : (
                              <div className="text-[var(--text-muted)]">
                                Текст раздела ещё не загружен.
                              </div>
                            )}
                            {sectionClaims.length > 0 && (
                              <details className="rounded bg-[var(--control-bg)] p-2">
                                <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                                  Извлечённые утверждения: {formatNumber(sectionClaims.length)}
                                </summary>
                                <div className="mt-2 space-y-2">
                                  {sectionClaims.map((claim, claimIndex) => (
                                    <details
                                      key={draftClaimKey(claim, claimIndex)}
                                      className="rounded bg-[var(--surface-elevated)] p-2"
                                    >
                                      <summary className="cursor-pointer text-[var(--text-primary)]">
                                        {draftClaimTitle(claim, claimIndex)}
                                      </summary>
                                      <div className="mt-2 space-y-2 text-[var(--text-secondary)]">
                                        <div>{draftClaimText(claim)}</div>
                                        {draftClaimQuestions(claim).length > 0 && (
                                          <div>
                                            <div className="font-medium text-[var(--text-primary)]">
                                              Возможные вопросы
                                            </div>
                                            <ul className="mt-1 list-disc pl-5">
                                              {draftClaimQuestions(claim).map((question) => (
                                                <li key={question}>{question}</li>
                                              ))}
                                            </ul>
                                          </div>
                                        )}
                                        {draftClaimEvidence(claim) && (
                                          <div>
                                            <div className="font-medium text-[var(--text-primary)]">
                                              Дословное доказательство
                                            </div>
                                            <blockquote className="mt-1 rounded border-l-2 border-[var(--accent-primary)] bg-[var(--control-bg)] p-2">
                                              {draftClaimEvidence(claim)}
                                            </blockquote>
                                          </div>
                                        )}
                                      </div>
                                    </details>
                                  ))}
                                </div>
                              </details>
                            )}
                          </div>
                        </details>
                      );
                    })}
                  </div>
                </details>
              )}

              {attempts.length > 0 && (
                <section>
                  <details className="rounded-lg bg-[var(--surface-elevated)] p-2" open>
                    <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                      Попытки обработки ИИ: {formatNumber(attempts.length)}
                    </summary>
                    <div className="mt-2 space-y-1">
                    {attempts.map((attempt) => {
                      const sectionIndex = attemptSectionIndex(attempt);
                      return (
                        <details
                          key={attempt.node_run_id}
                          className={`rounded-lg border px-3 py-2 ${attemptRowTone(attempt.status)}`}
                        >
                          <summary className="cursor-pointer list-none">
                            <span className="flex flex-wrap items-center justify-between gap-2">
                              <span>
                                <span className="font-semibold text-[var(--text-primary)]">
                                  {sectionIndex !== null
                                    ? `Раздел ${sectionDisplayNumber(sectionIndex)}`
                                    : 'Раздел не определён'}
                                </span>
                                <span className="ml-2 text-[var(--text-muted)]">
                                  {attempt.model_name || attempt.model_provider || 'модель не определена'}
                                </span>
                              </span>
                              <span className={`rounded-full px-2.5 py-1 font-medium ${statusPillTone(attempt.status)}`}>
                                {attemptStatusLabel(attempt.status)}
                              </span>
                            </span>
                          </summary>
                          <div className="mt-1 text-[var(--text-muted)]">
                            Время: {formatMilliseconds(attempt.duration_ms)}
                            {attempt.total_tokens > 0
                              ? ` · токены: ${formatNumber(attempt.total_tokens)}`
                              : ''}
                          </div>
                          {(attempt.error_message_user || attempt.error_kind) && (
                            <div className="mt-1 rounded bg-amber-500/10 px-2 py-1 text-amber-700 dark:text-amber-300">
                              {userErrorLabel(attempt.error_message_user || attempt.error_kind)}
                            </div>
                          )}
                        </details>
                      );
                    })}
                    </div>
                  </details>
                </section>
              )}

              {actions.filter((action) => action.visible).length > 0 && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {actions
                    .filter((action) => action.visible)
                    .map((action) => (
                      <button
                        key={action.action_id}
                        type="button"
                        disabled={!canRunLiveAction(action)}
                        title={disabledActionTitle(action)}
                        onClick={() => handleLiveAction(action)}
                        className={liveActionClassName(action)}
                      >
                        {liveActionLabel(action)}
                      </button>
                    ))}
                </div>
              )}

              {workflow.curation.available && workflow.curation.workflow_run_id && (
                <div className="rounded-lg bg-[var(--accent-primary)]/10 px-2 py-1 text-[var(--accent-primary)]">
                  Проверка человеком доступна.
                </div>
              )}
            </div>
          </details>
        )}
      </div>
    </div>
  );
};
