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
  type WorkbenchWorkflowTimelineEntryLiveState,
  type WorkbenchSectionQueueItemLiveState,
  type WorkbenchLlmAttemptLiveState,
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

const timelineLabel = (entry: WorkbenchWorkflowTimelineEntryLiveState): string => {
  const labels: Record<string, string> = {
    SourceDocumentPersisted: 'Документ сохранён',
    SourceUnitsCreated: 'Документ разбит на разделы',
    ScheduleClaimBuilderSectionWork: 'Запланирована обработка разделов',
    ClaimBuilderSectionWorkScheduled: 'Разделы поставлены в очередь',
    PrepareClaimBuilderDispatchBatch: 'Подготовлен запуск ИИ',
    ClaimBuilderSectionExtracted: 'Утверждения извлечены из раздела',
    ClaimBuilderSectionExtractionRetryableFailed:
      'Ответ ИИ отклонён проверкой, нужна повторная попытка',
    ClaimBuilderSectionExtractionTerminalFailed:
      'Раздел не удалось обработать автоматически',
    WorkflowManuallyPaused: 'Обработка поставлена на паузу',
    WorkflowManuallyResumed: 'Обработка возобновлена',
  };
  return labels[entry.event_type] || 'Событие обработки';
};

const timelineMessage = (entry: WorkbenchWorkflowTimelineEntryLiveState): string => {
  const event = entry.event_type;
  if (event === 'ClaimBuilderSectionExtracted') {
    return 'Секция обработана, результат сохранён.';
  }
  if (event === 'ClaimBuilderSectionExtractionRetryableFailed') {
    return 'Ответ модели не прошёл строгую проверку. Секция останется в очереди на повторную попытку.';
  }
  if (event === 'WorkflowManuallyPaused') {
    return 'Обработка остановлена пользователем. Уже полученные результаты сохранены.';
  }
  if (event === 'WorkflowManuallyResumed') {
    return 'Обработка продолжена с текущего места.';
  }
  return entry.message || 'Событие записано.';
};

const liveActionLabel = (action: WorkbenchWorkflowActionLiveState): string => {
  const labels: Record<string, string> = {
    pause_processing: 'Пауза',
    resume_processing: 'Продолжить',
    cancel_processing: 'Остановить',
    open_curation: 'Открыть проверку',
    publish_ready: 'Опубликовать',
    open_published_surfaces: 'Опубликованное',
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

  return `${base} bg-[var(--control-bg)] text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)]`;
};

const sourceUnitTitle = (unit: KnowledgeSourceUnit | null): string =>
  unit?.title?.trim() || 'Без заголовка';

const sectionDisplayNumber = (index: number): string => formatNumber(index + 1);

const technicalId = (value: string | null | undefined): string =>
  value && value.trim() ? value : '—';


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
    if (!isLiveTimer) return undefined;

    setNowMs(Date.now());
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [isLiveTimer, timerStartedAt, workflow?.workflow_run_id]);

  const workflowStatus = workflow?.workflow_status ?? null;
  const currentPhase = workflow?.current_phase ?? null;
  const stages = workflow?.stages ?? [];
  const lanes = workflow?.section_lanes ?? [];
  const attempts = workflow?.llm_attempts ?? [];
  const timeline = workflow?.timeline ?? [];
  const actions = workflow?.actions ?? [];
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
    ? `Черновики утверждений: ${formatNumber(claimStage?.current ?? 0)} · Векторы: ${formatNumber(
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

        <div className="grid gap-2 text-xs [grid-template-columns:repeat(auto-fit,minmax(140px,1fr))]">
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
                <div className="mb-1 font-medium text-[var(--text-primary)]">Этапы</div>
                <div className="grid gap-1 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]">
                  {stages.map((stage) => (
                    <div
                      key={stage.id}
                      className="rounded-lg bg-[var(--surface-elevated)] px-2 py-1"
                    >
                      <div className="font-medium text-[var(--text-primary)]">
                        {liveStageLabel(stage)}
                      </div>
                      <div className="text-[var(--text-muted)]">
                        {stageStatusLabel(stage)}
                        {stage.total > 0 && stage.id !== 'cluster_preview'
                          ? ` · ${formatNumber(stage.current)} / ${formatNumber(stage.total)}`
                          : ''}
                      </div>
                    </div>
                  ))}
                </div>
              </section>

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
                          className="rounded-lg bg-[var(--surface-elevated)] px-2 py-1"
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
                          className="rounded-lg bg-[var(--surface-elevated)] px-2 py-1"
                        >
                          <summary className="cursor-pointer list-none">
                            <span className="font-medium text-[var(--text-primary)]">
                              {sectionIndex !== null
                                ? `Раздел ${sectionDisplayNumber(sectionIndex)}`
                                : 'Раздел не определён'}
                            </span>
                            <span className="ml-2 text-[var(--text-muted)]">
                              {attempt.model_name || attempt.model_provider || 'модель не определена'} · {attemptStatusLabel(attempt.status)}
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

              {timeline.length > 0 && (
                <section>
                  <div className="mb-1 font-medium text-[var(--text-primary)]">
                    Хронология обработки
                  </div>
                  <div className="space-y-1">
                    {timeline.map((entry) => (
                      <details
                        key={entry.timeline_entry_id}
                        className="rounded-lg bg-[var(--surface-elevated)] px-2 py-1"
                      >
                        <summary className="cursor-pointer list-none font-medium text-[var(--text-primary)]">
                          {timelineLabel(entry)}
                        </summary>
                        <div className="mt-1 text-[var(--text-muted)]">
                          {timelineMessage(entry)}
                        </div>
                      </details>
                    ))}
                  </div>
                </section>
              )}

              <details className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-2">
                <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                  Технические детали
                </summary>
                <div className="mt-2 space-y-2 font-mono text-[11px] text-[var(--text-muted)]">
                  <div>workflow: {technicalId(workflow.workflow_run_id)}</div>
                  <div>phase: {technicalId(workflow.current_phase)}</div>
                  <div>status: {technicalId(workflow.workflow_status)}</div>
                  {timeline.slice(0, 8).map((entry) => (
                    <div key={`tech:${entry.timeline_entry_id}`} className="rounded bg-[var(--control-bg)] p-2">
                      <div>{entry.event_type} · {entry.phase}</div>
                      <div>work_item: {technicalId(entry.work_item_id)}</div>
                      <div>attempt: {technicalId(entry.attempt_id)}</div>
                    </div>
                  ))}
                </div>
              </details>

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
