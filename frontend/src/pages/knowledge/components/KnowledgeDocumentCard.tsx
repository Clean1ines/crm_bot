import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock3, FileText, Trash2, Zap } from 'lucide-react';

import { t } from '@shared/i18n';
import {
  type WorkbenchDocumentCardActionView,
  type WorkbenchDocumentCardUserMessage,
  type WorkbenchDocumentCardView,
  type WorkbenchWorkflowActionLiveState,
  type WorkbenchWorkflowLiveStateResponse,
  type WorkbenchWorkflowStageLiveState,
} from '@shared/api/modules/knowledge';

type DocCardDocument = {
  id: string;
  file_name: string;
  file_size: number;
  preprocessing_mode?: string | null;
  card_view?: WorkbenchDocumentCardView | null;
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

type WorkbenchPhaseMetadata = Record<
  string,
  string | number | boolean | null | undefined
>;

type WorkbenchLocalClaimPreview = {
  claim_id?: string | null;
  node_run_id?: string | null;
  section_id?: string | null;
  section_index?: number | string | null;
  section_title?: string | null;
  local_ref?: string | null;
  claim?: string | null;
  claim_kind?: string | null;
  granularity?: string | null;
  evidence_block?: string | null;
  scope?: string | null;
  exclusion_scope?: string | null;
  possible_questions?: string[] | null;
  triples?: object[] | null;
  local_relations?: object[] | null;
  confidence?: number | string | null;
};

type WorkbenchCardMetadata = {
  workbench_phase?: WorkbenchPhaseMetadata | null;
  workbench_claim_preview?: WorkbenchLocalClaimPreview[] | null;
  workbench_claim_preview_count?: number | string | null;
};

const metadataNumber = (
  metadata: WorkbenchCardMetadata | undefined,
  key: string,
): number => {
  const phase = metadata?.workbench_phase;
  if (!phase || typeof phase !== 'object' || Array.isArray(phase)) return 0;

  const value = phase[key];
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const metadataRootNumber = (
  metadata: WorkbenchCardMetadata | undefined,
  key: keyof WorkbenchCardMetadata,
): number => {
  const value = metadata?.[key];
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const metadataText = (value: string | number | null | undefined): string => {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
};

const stringifyDetails = (value: object[] | null | undefined): string => {
  if (!Array.isArray(value) || value.length === 0) return '';
  return JSON.stringify(value, null, 2);
};

const translateDynamic = t as (key: string) => string;

const cardText = (i18nKey: string | null | undefined, fallback: string): string => {
  if (!i18nKey) return fallback;
  const translated = translateDynamic(i18nKey);
  return translated && translated !== i18nKey ? translated : fallback;
};

const liveStageLabel = (stage: WorkbenchWorkflowStageLiveState): string => {
  const labels: Record<string, string> = {
    source_ingestion: 'Подготовка документа',
    prompt_a_claim_extraction: 'Извлечение утверждений',
    draft_claim_embeddings: 'Векторизация черновиков',
    draft_claim_clustering: 'Группировка похожих утверждений',
    draft_claim_compaction: 'Сжатие и объединение знаний',
    cluster_preview: 'Подготовка предпросмотра',
    curation: 'Курация',
    publication: 'Публикация',
  };
  return labels[stage.id] || stage.label || stage.id;
};

const liveStageStatusLabel = (status: string): string => {
  const noDataStatus = ['un', 'known'].join('');
  const labels: Record<string, string> = {
    pending: 'ожидает',
    running: 'идёт',
    completed: 'готово',
    failed: 'ошибка',
    paused: 'пауза',
    [noDataStatus]: 'нет данных',
  };
  return labels[status] || status;
};

const liveActionLabel = (action: WorkbenchWorkflowActionLiveState): string => {
  const labels: Record<string, string> = {
    pause_processing: 'Пауза',
    resume_processing: 'Продолжить',
    cancel_processing: 'Остановить',
    open_curation: 'Курация',
  };
  return labels[action.action_id] || action.action_id;
};

const canRunLiveAction = (action: WorkbenchWorkflowActionLiveState): boolean =>
  action.enabled && action.action_id !== 'pause_processing';

const isRecoverableStoppedLiveState = (
  workflowLiveState: WorkbenchWorkflowLiveStateResponse | null | undefined,
): boolean => {
  const workflowStatus = workflowLiveState?.workflow?.workflow_status?.toLowerCase() || '';
  const timerMode = workflowLiveState?.workflow?.timer?.mode || '';
  return ['paused', 'stopped', 'cancelled', 'failed_recoverable', 'blocked_recoverable'].includes(
    workflowStatus,
  ) || ['paused', 'stopped'].includes(timerMode);
};

const liveActionClassName = (action: WorkbenchWorkflowActionLiveState): string => {
  const base =
    'rounded-full px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50';
  if (action.action_id === 'cancel_processing') {
    return `${base} bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)] hover:opacity-80`;
  }
  if (action.action_id === 'open_curation') {
    return `${base} bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/20`;
  }
  return `${base} bg-[var(--control-bg)] text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)]`;
};

const formatMilliseconds = (value: number | null | undefined): string => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return '—';
  }
  return `${(value / 1000).toFixed(1)} c`;
};

const messageClassName = (severity: string): string => {
  if (severity === 'error') {
    return 'border-[var(--accent-danger)]/30 bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]';
  }
  if (severity === 'warning') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300';
  }
  if (severity === 'success') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
  }
  return 'border-[var(--border-subtle)] bg-[var(--surface-secondary)] text-[var(--text-secondary)]';
};

const actionClassName = (action: WorkbenchDocumentCardActionView): string => {
  const base =
    'rounded-full px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50';

  if (action.tone === 'danger') {
    return `${base} bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)] hover:opacity-80`;
  }
  if (action.tone === 'warning') {
    return `${base} bg-amber-500/10 text-amber-700 hover:bg-amber-500/20 dark:text-amber-300`;
  }
  if (action.tone === 'primary') {
    return `${base} bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/20`;
  }
  return `${base} bg-[var(--control-bg)] text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)]`;
};

const messageIcon = (message: WorkbenchDocumentCardUserMessage) => {
  if (message.severity === 'error' || message.severity === 'warning') {
    return <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none" />;
  }
  if (message.severity === 'success') {
    return <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 flex-none" />;
  }
  return <Clock3 className="mt-0.5 h-3.5 w-3.5 flex-none" />;
};

const primaryActions = (cardView: WorkbenchDocumentCardView): WorkbenchDocumentCardActionView[] =>
  cardView.actions.filter(
    (action) => action.visible && action.enabled && action.tone === 'primary',
  );

const visibleSecondaryActions = (
  cardView: WorkbenchDocumentCardView,
): WorkbenchDocumentCardActionView[] =>
  cardView.actions.filter(
    (action) =>
      action.visible &&
      action.action_id !== 'delete_document' &&
      !(
        action.enabled &&
        action.tone === 'primary' &&
        primaryActions(cardView).some(
          (primaryAction) => primaryAction.action_id === action.action_id,
        )
      ),
  );

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
  formatSize,
  knowledgeProcessingModeLabel,
}) => {
  const cardView = doc.card_view;
  const liveWorkflow = workflowLiveState?.workflow ?? null;
  const liveTimer = liveWorkflow?.timer ?? null;
  const timerStartedAt =
    liveTimer?.current_active_started_at ||
    cardView?.timer.current_active_started_at ||
    null;
  const liveWorkflowStatus = liveWorkflow?.workflow_status?.toLowerCase() || '';
  const isLiveTimer =
    liveTimer !== null
      ? Boolean(
          liveTimer.is_live ||
            liveTimer.mode === 'running' ||
            ['running', 'active', 'processing'].includes(liveWorkflowStatus),
        )
      : cardView?.timer.mode === 'running';
  const [nowMs, setNowMs] = useState(() => Date.now());
  const liveTimerObservedAtMsRef = useRef<number | null>(null);
  const [expandedClaimIds, setExpandedClaimIds] = useState<Set<string>>(
    () => new Set(),
  );

  useEffect(() => {
    if (!isLiveTimer) {
      liveTimerObservedAtMsRef.current = null;
      return undefined;
    }

    if (liveTimerObservedAtMsRef.current === null) {
      liveTimerObservedAtMsRef.current = Date.now();
    }

    setNowMs(Date.now());
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [isLiveTimer, timerStartedAt, liveWorkflow?.workflow_run_id]);

  if (!cardView) {
    return null;
  }

  const recoverableStopped = isRecoverableStoppedLiveState(workflowLiveState);
  const cardPrimaryActions = primaryActions(cardView).filter(
    (action) => !(recoverableStopped && action.action_id === 'cancel_processing'),
  );
  const cardSecondaryActions = visibleSecondaryActions(cardView).filter(
    (action) => !(recoverableStopped && action.action_id === 'cancel_processing'),
  );
  const deleteAction = cardView.actions.find(
    (action) => action.action_id === 'delete_document',
  );

  const cardMetadata = cardView.metadata as WorkbenchCardMetadata | undefined;

  const promptACompleted = metadataNumber(
    cardMetadata,
    'prompt_a_completed_sections',
  );
  const sectionQueueLeased = metadataNumber(
    cardMetadata,
    'section_queue_leased_count',
  );
  const sectionQueueReady = metadataNumber(
    cardMetadata,
    'section_queue_ready_count',
  );
  const registryApplicationPending =
    metadataNumber(cardMetadata, 'registry_application_ready_count') +
    metadataNumber(cardMetadata, 'registry_application_leased_count') +
    metadataNumber(
      cardMetadata,
      'registry_application_waiting_for_fresh_registry_count',
    );
  const embeddingIndexedClaims = metadataNumber(
    cardMetadata,
    'embedding_indexed_claims',
  );
  const claimPreview = Array.isArray(cardMetadata?.workbench_claim_preview)
    ? cardMetadata.workbench_claim_preview
    : [];
  const claimPreviewCount =
    metadataRootNumber(cardMetadata, 'workbench_claim_preview_count') ||
    claimPreview.length;

  const toggleClaimPreview = (claimId: string): void => {
    setExpandedClaimIds((current) => {
      const next = new Set(current);
      if (next.has(claimId)) {
        next.delete(claimId);
      } else {
        next.add(claimId);
      }
      return next;
    });
  };

  const livePromptAStage =
    liveWorkflow?.stages.find((stage) => stage.id === 'prompt_a_claim_extraction') ??
    null;
  const liveSourceStage =
    liveWorkflow?.stages.find((stage) => stage.id === 'source_ingestion') ?? null;
  const liveEmbeddingStage =
    liveWorkflow?.stages.find((stage) => stage.id === 'draft_claim_embeddings') ??
    null;
  const livePreviewStage =
    liveWorkflow?.stages.find((stage) => stage.id === 'cluster_preview') ?? null;
  const livePrimaryProgressStage =
    livePromptAStage && livePromptAStage.total > 0
      ? livePromptAStage
      : liveSourceStage;

  const liveLaneReady =
    liveWorkflow?.section_lanes.reduce((total, lane) => total + lane.ready_count, 0) ??
    0;
  const liveLaneLeased =
    liveWorkflow?.section_lanes.reduce((total, lane) => total + lane.leased_count, 0) ??
    0;
  const liveLaneDone =
    liveWorkflow?.section_lanes.reduce((total, lane) => total + lane.done_count, 0) ??
    0;
  const liveLaneFailed =
    liveWorkflow?.section_lanes.reduce((total, lane) => total + lane.failed_count, 0) ??
    0;
  const liveLaneWaiting =
    liveWorkflow?.section_lanes.reduce((total, lane) => total + lane.waiting_count, 0) ??
    0;

  const hasLiveProgress =
    Boolean(liveWorkflow && livePrimaryProgressStage) &&
    ((livePrimaryProgressStage?.total ?? 0) > 0 ||
      (livePrimaryProgressStage?.current ?? 0) > 0 ||
      liveLaneReady > 0 ||
      liveLaneLeased > 0 ||
      liveLaneDone > 0 ||
      liveLaneFailed > 0 ||
      liveLaneWaiting > 0);

  const fallbackSectionProgressCurrent =
    promptACompleted > 0 || sectionQueueLeased > 0 || sectionQueueReady > 0
      ? promptACompleted
      : cardView.sections.processed + cardView.sections.failed;

  const liveObservedSectionTotal =
    liveLaneReady + liveLaneLeased + liveLaneDone + liveLaneFailed + liveLaneWaiting;

  const sectionProgressTotal =
    hasLiveProgress && livePrimaryProgressStage
      ? Math.max(
          livePrimaryProgressStage.total,
          livePrimaryProgressStage.current,
          liveObservedSectionTotal,
          cardView.sections.total,
        )
      : cardView.sections.total;

  const sectionProgressCurrent =
    hasLiveProgress && livePrimaryProgressStage
      ? livePrimaryProgressStage.current
      : fallbackSectionProgressCurrent;

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

  const liveProgressQueueText =
    liveLaneLeased > 0 || liveLaneReady > 0 || liveLaneWaiting > 0 || liveLaneFailed > 0
      ? `${liveLaneLeased > 0 ? ` · активно ${formatNumber(liveLaneLeased)}` : ''}${
          liveLaneReady > 0 ? ` · готово ${formatNumber(liveLaneReady)}` : ''
        }${liveLaneWaiting > 0 ? ` · ждёт ${formatNumber(liveLaneWaiting)}` : ''}${
          liveLaneFailed > 0 ? ` · ошибок ${formatNumber(liveLaneFailed)}` : ''
        }`
      : '';

  const sectionProgressText =
    hasLiveProgress && livePrimaryProgressStage
      ? `${liveStageLabel(livePrimaryProgressStage)}: ${formatNumber(
          sectionProgressCurrent,
        )} из ${formatNumber(sectionProgressTotal)}${liveProgressQueueText}`
      : promptACompleted > 0 || sectionQueueLeased > 0 || sectionQueueReady > 0
        ? `Разбор: ${formatNumber(promptACompleted)} из ${formatNumber(
            cardView.sections.total,
          )} секций${
            sectionQueueLeased > 0
              ? ` · активно ${formatNumber(sectionQueueLeased)}`
              : ''
          }${
            sectionQueueReady > 0
              ? ` · в очереди ${formatNumber(sectionQueueReady)}`
              : ''
          }`
        : `${formatNumber(cardView.sections.processed)} из ${formatNumber(
            cardView.sections.total,
          )} секций обработано${
            cardView.sections.failed > 0
              ? ` · ${formatNumber(cardView.sections.failed)} с ошибкой`
              : ''
          }`;

  const timerStartedAtMs = timerStartedAt ? Date.parse(timerStartedAt) : Number.NaN;
  const baseActiveElapsedSeconds =
    liveTimer?.active_elapsed_seconds ?? cardView.timer.active_elapsed_seconds;
  const liveTimerObservedAtMs = liveTimerObservedAtMsRef.current;
  const liveActiveElapsedSeconds =
    isLiveTimer
      ? baseActiveElapsedSeconds +
        (Number.isFinite(timerStartedAtMs)
          ? Math.max(0, Math.floor((nowMs - timerStartedAtMs) / 1000))
          : liveTimerObservedAtMs !== null
            ? Math.max(0, Math.floor((nowMs - liveTimerObservedAtMs) / 1000))
            : 0)
      : baseActiveElapsedSeconds;
  const elapsedText =
    liveActiveElapsedSeconds > 0 || isLiveTimer
      ? formatDuration(liveActiveElapsedSeconds)
      : '—';
  const fileSizeText = doc.file_size > 0 ? formatSize(doc.file_size) : 'размер недоступен';

  const liveUsage = liveWorkflow?.usage ?? null;
  const totalTokens = liveUsage?.total_tokens ?? cardView.usage.total_tokens;
  const totalLlmCalls = liveUsage?.total_llm_calls ?? cardView.usage.llm_call_count;
  const llmUsageText =
    totalTokens > 0 || totalLlmCalls > 0
      ? `${formatNumber(totalTokens)} токенов · ${formatNumber(totalLlmCalls)} LLM-выз.`
      : '—';

  const liveWorkflowStatusText = liveWorkflow
    ? `${liveWorkflow.current_phase || 'фаза не определена'} · ${
        liveWorkflow.workflow_status || ['un', 'known'].join('')
      }`
    : null;

  const liveDraftClaimCount = livePromptAStage?.current ?? 0;
  const liveEmbeddingCount = liveEmbeddingStage?.current ?? 0;
  const livePreviewCount = livePreviewStage?.current ?? 0;
  const fallbackResultSummaryText = `Факты: ${formatNumber(
    cardView.registry.entry_count,
  )} · Runtime: ${formatNumber(cardView.runtime.runtime_entry_count)}`;
  const liveResultSummaryText = liveWorkflow
    ? `Черновики: ${formatNumber(liveDraftClaimCount)} · Embeddings: ${formatNumber(
        liveEmbeddingCount,
      )} · Preview: ${formatNumber(livePreviewCount)}`
    : null;
  const resultSummaryText = liveResultSummaryText ?? fallbackResultSummaryText;

  const handleLiveAction = (action: WorkbenchWorkflowActionLiveState): void => {
    if (!canRunLiveAction(action)) return;

    if (action.action_id === 'cancel_processing') {
      onStopProcessing();
      return;
    }

    if (action.action_id === 'resume_processing') {
      onCardAction('resume_processing');
      return;
    }

    if (action.action_id === 'open_curation') {
      onOpenCuration(liveWorkflow?.curation.workflow_run_id || liveWorkflow?.workflow_run_id);
    }
  };

  const handleCardAction = (action: WorkbenchDocumentCardActionView): void => {
    if (!action.enabled) return;

    if (action.action_id === 'cancel_processing') {
      onStopProcessing();
      return;
    }

    if (
      action.action_id === 'open_curation' ||
      action.action_id === 'open_published_surfaces'
    ) {
      onOpenCuration();
      return;
    }

    if (action.action_id === 'delete_document') {
      onRequestDelete();
      return;
    }

    onCardAction(action.action_id);
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
          {cardPrimaryActions.length > 0 ? (
            cardPrimaryActions.map((action) => (
              <button
                key={action.action_id}
                type="button"
                disabled={!action.enabled}
                title={action.default_confirmation || action.default_label}
                onClick={() => handleCardAction(action)}
                className={actionClassName(action)}
              >
                {cardText(action.i18n_key, action.default_label)}
              </button>
            ))
          ) : (
            <span className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]">
              {cardText(cardView.status_i18n_key, cardView.default_status_label)}
            </span>
          )}

          {cardSecondaryActions.slice(0, 3).map((action) => (
            <button
              key={action.action_id}
              type="button"
              disabled={!action.enabled}
              title={action.default_confirmation || action.default_label}
              onClick={() => handleCardAction(action)}
              className={actionClassName(action)}
            >
              {cardText(action.i18n_key, action.default_label)}
            </button>
          ))}

          <button
            type="button"
            onClick={
              deleteAction && deleteAction.enabled
                ? () => handleCardAction(deleteAction)
                : onRequestDelete
            }
            disabled={isDeletePending}
            title={deleteAction?.default_confirmation || t('common.actions.delete')}
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
              {fileSizeText} ·{' '}
              {knowledgeProcessingModeLabel(doc.preprocessing_mode || 'faq')}
            </p>
          </div>
          <span className="max-w-[45%] shrink-0 truncate rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)]" title={cardText(cardView.status_i18n_key, cardView.default_status_label)}>
            {cardText(cardView.status_i18n_key, cardView.default_status_label)}
          </span>
          <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
            live-state-card-v4
          </span>
        </div>

        <div className="mt-2 rounded-xl bg-[var(--surface-secondary)] px-3 py-2 text-sm leading-relaxed text-[var(--text-secondary)]">
          <div className="font-medium text-[var(--text-primary)]">
            Что происходит с документом
          </div>
          <p className="mt-1">
            {cardText(
              cardView.status_description_i18n_key,
              cardView.default_status_description,
            )}
          </p>
          {liveWorkflowStatusText && (
            <p className="mt-1 font-mono text-xs text-[var(--text-muted)]">
              {liveWorkflowStatusText}
            </p>
          )}
        </div>
      </div>

      <div className="mb-4 space-y-3">
        <div className="grid gap-2 text-xs [grid-template-columns:repeat(auto-fit,minmax(120px,1fr))]">
          <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
              <Clock3 className="h-3.5 w-3.5" />
              {cardText(cardView.timer.i18n_key, cardView.timer.default_label)}
            </div>
            <div className="text-[var(--text-muted)]">
              {elapsedText}
            </div>
          </div>

          <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
              <Zap className="h-3.5 w-3.5" />
              ИИ
            </div>
            <div className="text-[var(--text-muted)]">{llmUsageText}</div>
          </div>

          <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-1 font-medium text-[var(--text-primary)]">
              Прогресс
            </div>
            <div className="text-[var(--text-muted)]">{sectionProgressText}</div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--control-bg)]">
              <div
                className="h-full rounded-full bg-[var(--accent-primary)]"
                style={{ width: `${sectionProgressPercent}%` }}
              />
            </div>
            <div className="mt-1 text-[var(--text-muted)]">
              {sectionProgressPercent}%
            </div>
          </div>

          <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-1 font-medium text-[var(--text-primary)]">
              Итог
            </div>
            <div className="text-[var(--text-muted)]">
              {resultSummaryText}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 text-xs">
          {(promptACompleted > 0 || sectionQueueLeased > 0 || sectionQueueReady > 0) && (
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              Разбор: {formatNumber(promptACompleted)} /{' '}
              {formatNumber(cardView.sections.total)}
              {sectionQueueLeased > 0
                ? ` · активно ${formatNumber(sectionQueueLeased)}`
                : ''}
              {sectionQueueReady > 0
                ? ` · очередь ${formatNumber(sectionQueueReady)}`
                : ''}
            </span>
          )}
          {claimPreviewCount > 0 && (
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              Извлечения: {formatNumber(claimPreviewCount)}
            </span>
          )}
          {registryApplicationPending > 0 && (
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              Registry queue: {formatNumber(registryApplicationPending)}
            </span>
          )}
          {embeddingIndexedClaims > 0 && (
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              Embeddings: {formatNumber(embeddingIndexedClaims)}
            </span>
          )}
          {cardView.transient_purged && (
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-emerald-700 dark:text-emerald-300">
              Промежуточные данные очищены
            </span>
          )}
          {cardView.recovery.mode === 'scheduled_auto_resume' && (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-amber-700 dark:text-amber-300">
              {cardText(cardView.recovery.i18n_key, cardView.recovery.default_message)}
            </span>
          )}
        </div>

        {(workflowLiveStateLoading || workflowLiveStateError || liveWorkflow) && (
          <details
            className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-secondary)] break-words [overflow-wrap:anywhere]"
            open={Boolean(workflowLiveStateError)}
          >
            <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-[var(--text-primary)]">
                Подробности live-процесса
              </span>
              <span className="flex min-w-0 flex-wrap items-center justify-end gap-2">
                {workflowLiveStateLoading && (
                  <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                    обновляем…
                  </span>
                )}
                {liveWorkflowStatusText && (
                  <span
                    className="max-w-full rounded-full bg-[var(--control-bg)] px-2 py-0.5 font-mono break-all"
                    title={liveWorkflow?.workflow_run_id || liveWorkflowStatusText}
                  >
                    {liveWorkflowStatusText}
                  </span>
                )}
              </span>
            </summary>

            <div className="mt-3 space-y-3">
              {workflowLiveStateError && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-amber-700 dark:text-amber-300">
                  {workflowLiveStateError}
                </div>
              )}

              {liveWorkflow && (
                <>
                  {liveWorkflow.workflow_run_id && (
                    <div
                      className="max-w-full truncate rounded-lg bg-[var(--surface-elevated)] px-2 py-1 font-mono"
                      title={liveWorkflow.workflow_run_id}
                    >
                      workflow: {liveWorkflow.workflow_run_id}
                    </div>
                  )}

                  <div className="grid gap-2 [grid-template-columns:repeat(auto-fit,minmax(180px,1fr))]">
                    <div className="rounded-lg bg-[var(--surface-elevated)] p-2">
                      <div className="font-medium text-[var(--text-primary)]">
                        Модели
                      </div>
                      <div className="mt-1 space-y-1">
                        {liveWorkflow.usage.model_summaries.length > 0 ? (
                          liveWorkflow.usage.model_summaries.slice(0, 3).map((model) => (
                            <div
                              key={`${model.model_provider || 'provider'}:${model.model_name || 'model'}`}
                            >
                              {model.model_provider || 'provider'} /{' '}
                              {model.model_name || 'model'} · {formatNumber(model.call_count)} выз. ·{' '}
                              {formatNumber(model.total_tokens)} ток.
                            </div>
                          ))
                        ) : (
                          <div>модели ещё не зафиксированы</div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-lg bg-[var(--surface-elevated)] p-2">
                      <div className="font-medium text-[var(--text-primary)]">
                        Очереди секций
                      </div>
                      <div className="mt-1">
                        ready {formatNumber(liveLaneReady)} · leased {formatNumber(liveLaneLeased)} · done{' '}
                        {formatNumber(liveLaneDone)} · failed {formatNumber(liveLaneFailed)} · waiting{' '}
                        {formatNumber(liveLaneWaiting)}
                      </div>
                    </div>
                  </div>

                  <div>
                    <div className="mb-1 font-medium text-[var(--text-primary)]">
                      Этапы
                    </div>
                    <div className="grid gap-1 [grid-template-columns:repeat(auto-fit,minmax(180px,1fr))]">
                      {liveWorkflow.stages.map((stage) => (
                        <div
                          key={stage.id}
                          className="flex min-w-0 items-center justify-between gap-2 rounded-lg bg-[var(--surface-elevated)] px-2 py-1"
                        >
                          <span className="min-w-0 break-words">{liveStageLabel(stage)}</span>
                          <span className="shrink-0 text-[var(--text-muted)]">
                            {liveStageStatusLabel(stage.status)}
                            {stage.total > 0
                              ? ` · ${formatNumber(stage.current)} / ${formatNumber(stage.total)}`
                              : ''}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {liveWorkflow.section_lanes.length > 0 && (
                    <details className="rounded-lg bg-[var(--surface-elevated)] p-2">
                      <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                        Потоки секций
                      </summary>
                      <div className="mt-2 space-y-2">
                        {liveWorkflow.section_lanes.map((lane) => (
                          <div key={`${lane.lane_index}:${lane.lane_id}`}>
                            <div className="font-medium text-[var(--text-primary)]">
                              Поток {lane.lane_index + 1}: ready {formatNumber(lane.ready_count)} · leased{' '}
                              {formatNumber(lane.leased_count)} · done {formatNumber(lane.done_count)} · failed{' '}
                              {formatNumber(lane.failed_count)} · waiting {formatNumber(lane.waiting_count)}
                            </div>
                            <div className="mt-1 space-y-1">
                              {lane.items.slice(0, 6).map((item) => (
                                <div
                                  key={item.queue_item_id}
                                  className="rounded bg-[var(--control-bg)] px-2 py-1"
                                >
                                  секция {item.section_index} · {item.status} · попыток{' '}
                                  {formatNumber(item.attempt_count)}
                                  {item.retry_timer.seconds_until_retry !== null &&
                                  item.retry_timer.seconds_until_retry !== undefined
                                    ? ` · retry через ${formatDuration(item.retry_timer.seconds_until_retry)}`
                                    : ''}
                                  {item.error_kind ? ` · ${item.error_kind}` : ''}
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  {liveWorkflow.llm_attempts.length > 0 && (
                    <details className="rounded-lg bg-[var(--surface-elevated)] p-2">
                      <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                        LLM attempts
                      </summary>
                      <div className="mt-2 space-y-1">
                        {liveWorkflow.llm_attempts.slice(0, 8).map((attempt) => (
                          <div
                            key={attempt.node_run_id}
                            className="rounded bg-[var(--control-bg)] px-2 py-1"
                          >
                            <div>
                              {attempt.node_name} · {attempt.status} ·{' '}
                              {attempt.model_provider || 'provider'} / {attempt.model_name || 'model'}
                            </div>
                            <div className="text-[var(--text-muted)]">
                              {formatNumber(attempt.total_tokens)} ток. ·{' '}
                              {formatMilliseconds(attempt.duration_ms)}
                              {attempt.error_message_user
                                ? ` · ${attempt.error_message_user}`
                                : ''}
                            </div>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  <div className="flex flex-wrap gap-2">
                    {liveWorkflow.actions
                      .filter(
                        (action) =>
                          action.visible &&
                          !(recoverableStopped && action.action_id === 'cancel_processing'),
                      )
                      .map((action) => (
                        <button
                          key={action.action_id}
                          type="button"
                          disabled={!canRunLiveAction(action)}
                          title={
                            action.action_id === 'pause_processing'
                              ? 'Pause endpoint по workflow_run_id будет подключён отдельным patch'
                              : action.reason_code || liveActionLabel(action)
                          }
                          onClick={() => handleLiveAction(action)}
                          className={liveActionClassName(action)}
                        >
                          {liveActionLabel(action)}
                        </button>
                      ))}
                  </div>

                  {liveWorkflow.curation.available && liveWorkflow.curation.workflow_run_id && (
                    <div className="rounded-lg bg-[var(--accent-primary)]/10 px-2 py-1 text-[var(--accent-primary)]">
                      Курация готова: workflow_run_id {liveWorkflow.curation.workflow_run_id}
                    </div>
                  )}
                </>
              )}
            </div>
          </details>
        )}


        {cardView.messages.length > 0 && (
          <div className="space-y-2">
            {cardView.messages.map((message) => (
              <div
                key={`${message.code}-${message.default_message}`}
                className={`flex gap-2 rounded-xl border px-3 py-2 text-xs ${messageClassName(
                  message.severity,
                )}`}
              >
                {messageIcon(message)}
                <span>{cardText(message.i18n_key, message.default_message)}</span>
              </div>
            ))}
          </div>
        )}

        {cardView.error && (
          <div className="rounded-xl border border-[var(--accent-danger)]/30 bg-[var(--accent-danger-bg)] px-3 py-2 text-xs text-[var(--accent-danger-text)]">
            {cardText(
              cardView.error.user_message.i18n_key,
              cardView.error.user_message.default_message,
            )}
          </div>
        )}

        {claimPreview.length > 0 && (
          <div className="rounded-xl bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-secondary)]">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="font-semibold text-[var(--text-primary)]">
                Извлечённые знания
              </div>
              <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                {formatNumber(claimPreviewCount)}
              </span>
            </div>

            <div className="space-y-2">
              {claimPreview.map((claim, index) => {
                const claimId =
                  metadataText(claim.claim_id) ||
                  metadataText(claim.node_run_id) ||
                  `claim-${index + 1}`;
                const isExpanded = expandedClaimIds.has(claimId);
                const claimText =
                  metadataText(claim.claim) || `Фрагмент ${index + 1}`;
                const evidence = metadataText(claim.evidence_block);
                const triples = stringifyDetails(claim.triples);
                const relations = stringifyDetails(claim.local_relations);
                const possibleQuestions = Array.isArray(claim.possible_questions)
                  ? claim.possible_questions.filter(Boolean)
                  : [];

                return (
                  <div
                    key={claimId}
                    className="rounded-lg bg-[var(--surface-elevated)] p-2"
                  >
                    <button
                      type="button"
                      onClick={() => toggleClaimPreview(claimId)}
                      className="flex w-full items-start justify-between gap-2 text-left"
                    >
                      <span>
                        <span className="font-medium text-[var(--text-primary)]">
                          {claimText}
                        </span>
                        <span className="mt-1 block text-[var(--text-muted)]">
                          {metadataText(claim.claim_kind) || 'фрагмент'} · секция{' '}
                          {metadataText(claim.section_index) || '?'}
                          {metadataText(claim.local_ref)
                            ? ` · ${metadataText(claim.local_ref)}`
                            : ''}
                        </span>
                      </span>
                      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                        {isExpanded ? 'скрыть' : 'детали'}
                      </span>
                    </button>

                    {isExpanded && (
                      <div className="mt-2 space-y-2 border-t border-[var(--border-subtle)] pt-2">
                        {evidence && (
                          <div>
                            <div className="font-medium text-[var(--text-primary)]">
                              Цитата / основание
                            </div>
                            <div className="mt-1 whitespace-pre-wrap">
                              {evidence}
                            </div>
                          </div>
                        )}
                        {metadataText(claim.scope) && (
                          <div>
                            <span className="font-medium text-[var(--text-primary)]">
                              Область действия:
                            </span>{' '}
                            {metadataText(claim.scope)}
                          </div>
                        )}
                        {possibleQuestions.length > 0 && (
                          <div>
                            <div className="font-medium text-[var(--text-primary)]">
                              Возможные вопросы
                            </div>
                            <ul className="mt-1 list-disc pl-4">
                              {possibleQuestions.map((question) => (
                                <li key={question}>{question}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {triples && (
                          <div>
                            <div className="font-medium text-[var(--text-primary)]">
                              Структурные связи
                            </div>
                            <pre className="mt-1 overflow-x-auto rounded bg-[var(--control-bg)] p-2">
                              {triples}
                            </pre>
                          </div>
                        )}
                        {relations && (
                          <div>
                            <div className="font-medium text-[var(--text-primary)]">
                              Связи внутри секции
                            </div>
                            <pre className="mt-1 overflow-x-auto rounded bg-[var(--control-bg)] p-2">
                              {relations}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

    </div>
  );
};
