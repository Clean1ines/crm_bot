import React, { useEffect, useState } from 'react';
import { AlertTriangle, Clock3, FileText, Trash2, Zap } from 'lucide-react';

import { t } from '@shared/i18n';
import {
  type WorkbenchWorkflowActionLiveState,
  type WorkbenchWorkflowLiveStateResponse,
  type WorkbenchWorkflowStageLiveState,
  type WorkbenchWorkflowTimelineEntryLiveState,
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
  return `${(value / 1000).toFixed(1)} c`;
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
  const labels: Record<string, string> = {
    pending: 'ожидает',
    running: 'идёт',
    completed: 'готово',
    failed: 'ошибка',
    paused: 'пауза',
    blocked: 'блокировка',
    deferred: 'отложено',
  };
  return labels[status] || status;
};

const liveTimelineEventLabel = (
  entry: WorkbenchWorkflowTimelineEntryLiveState,
): string => {
  const event = entry.event_type || 'event';
  const phase = entry.phase ? ` · ${entry.phase}` : '';
  return `${event}${phase}`;
};

const liveActionLabel = (action: WorkbenchWorkflowActionLiveState): string => {
  const labels: Record<string, string> = {
    pause_processing: 'Пауза',
    resume_processing: 'Продолжить',
    cancel_processing: 'Остановить',
    open_curation: 'Курация',
    publish_ready: 'Опубликовать',
    open_published_surfaces: 'Опубликованное',
    delete_document: 'Удалить',
  };
  return labels[action.action_id] || action.action_id;
};

const canRunLiveAction = (action: WorkbenchWorkflowActionLiveState): boolean =>
  action.enabled && action.action_id !== 'pause_processing';

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

const workflowStatusLabel = (status: string | null | undefined): string => {
  const value = (status || '').toLowerCase();
  const labels: Record<string, string> = {
    running: 'Обрабатывается',
    active: 'Обрабатывается',
    processing: 'Обрабатывается',
    paused: 'Пауза',
    completed: 'Готово',
    done: 'Готово',
    failed: 'Ошибка',
    cancelled: 'Остановлено',
    blocked: 'Блокировка',
  };
  return labels[value] || status || 'Состояние неизвестно';
};

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

  const sourceStage =
    stages.find((stage) => stage.id === 'source_ingestion') ?? null;
  const claimStage =
    stages.find((stage) => stage.id === 'prompt_a_claim_extraction') ?? null;
  const embeddingStage =
    stages.find((stage) => stage.id === 'draft_claim_embeddings') ?? null;
  const clusterStage =
    stages.find((stage) => stage.id === 'draft_claim_clustering') ?? null;
  const compactionStage =
    stages.find((stage) => stage.id === 'draft_claim_compaction') ?? null;
  const previewStage =
    stages.find((stage) => stage.id === 'cluster_preview') ?? null;

  const primaryProgressStage =
    claimStage && claimStage.total > 0
      ? claimStage
      : sourceStage && sourceStage.total > 0
        ? sourceStage
        : stages.find((stage) => stage.total > 0) ?? null;

  const laneReady = lanes.reduce((total, lane) => total + lane.ready_count, 0);
  const laneLeased = lanes.reduce((total, lane) => total + lane.leased_count, 0);
  const laneDone = lanes.reduce((total, lane) => total + lane.done_count, 0);
  const laneFailed = lanes.reduce((total, lane) => total + lane.failed_count, 0);
  const laneWaiting = lanes.reduce((total, lane) => total + lane.waiting_count, 0);
  const observedLaneTotal = laneReady + laneLeased + laneDone + laneFailed + laneWaiting;

  const sectionProgressTotal = primaryProgressStage
    ? Math.max(
        primaryProgressStage.total,
        primaryProgressStage.current,
        observedLaneTotal,
      )
    : observedLaneTotal;
  const sectionProgressCurrent = primaryProgressStage
    ? primaryProgressStage.current
    : laneDone;
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
  const totalTokens = usage?.total_tokens ?? 0;
  const totalLlmCalls = usage?.total_llm_calls ?? 0;
  const llmUsageText =
    totalTokens > 0 || totalLlmCalls > 0
      ? `${formatNumber(totalTokens)} токенов · ${formatNumber(totalLlmCalls)} LLM-выз.`
      : '—';

  const sectionProgressText = primaryProgressStage
    ? `${liveStageLabel(primaryProgressStage)}: ${formatNumber(
        sectionProgressCurrent,
      )} из ${formatNumber(sectionProgressTotal)}${
        laneLeased > 0 ? ` · активно ${formatNumber(laneLeased)}` : ''
      }${laneReady > 0 ? ` · готово ${formatNumber(laneReady)}` : ''}${
        laneWaiting > 0 ? ` · ждёт ${formatNumber(laneWaiting)}` : ''
      }${laneFailed > 0 ? ` · ошибок ${formatNumber(laneFailed)}` : ''}`
    : workflow
      ? `Ожидаем детализацию очереди${
          laneLeased > 0 ? ` · активно ${formatNumber(laneLeased)}` : ''
        }${laneReady > 0 ? ` · готово ${formatNumber(laneReady)}` : ''}`
      : 'Live-state ещё не загружен';

  const resultSummaryText = workflow
    ? `Черновики: ${formatNumber(claimStage?.current ?? 0)} · Embeddings: ${formatNumber(
        embeddingStage?.current ?? 0,
      )} · Clusters: ${formatNumber(clusterStage?.current ?? 0)} · Compaction: ${formatNumber(
        compactionStage?.current ?? 0,
      )} · Preview: ${formatNumber(previewStage?.current ?? 0)}`
    : 'Нет данных live-state';

  const handleLiveAction = (action: WorkbenchWorkflowActionLiveState): void => {
    if (!canRunLiveAction(action)) return;

    if (action.action_id === 'cancel_processing') {
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
          <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
            runtime-card-v1
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
          <div className="font-medium text-[var(--text-primary)]">
            Что происходит с документом
          </div>
          <p className="mt-1">
            {workflow
              ? `Сага обработки активна: ${currentPhase || 'фаза не определена'} · ${workflowStatus || 'статус не определён'}`
              : workflowLiveStateLoading
                ? 'Загружаем live-state обработки…'
                : 'Live-state обработки пока недоступен.'}
          </p>
          {workflow?.workflow_run_id && (
            <p className="mt-1 font-mono text-xs text-[var(--text-muted)]">
              workflow: {workflow.workflow_run_id}
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

        <div className="grid gap-2 text-xs [grid-template-columns:repeat(auto-fit,minmax(120px,1fr))]">
          <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
              <Clock3 className="h-3.5 w-3.5" />
              Таймер
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
            <div className="text-[var(--text-muted)]">{sectionProgressText}</div>
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
            open={timeline.length > 0}
          >
            <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-[var(--text-primary)]">
                Подробности live-процесса
              </span>
              <span className="max-w-full rounded-full bg-[var(--control-bg)] px-2 py-0.5 font-mono break-all">
                {currentPhase || 'phase'} · {workflowStatus || 'status'}
              </span>
            </summary>

            <div className="mt-3 space-y-3">
              <div className="grid gap-2 [grid-template-columns:repeat(auto-fit,minmax(180px,1fr))]">
                <div className="rounded-lg bg-[var(--surface-elevated)] p-2">
                  <div className="font-medium text-[var(--text-primary)]">Модели</div>
                  <div className="mt-1 space-y-1">
                    {usage && usage.model_summaries.length > 0 ? (
                      usage.model_summaries.slice(0, 3).map((model) => (
                        <div
                          key={`${model.model_provider || 'provider'}:${model.model_name || 'model'}`}
                        >
                          {model.model_provider || 'provider'} / {model.model_name || 'model'} ·{' '}
                          {formatNumber(model.call_count)} выз. · {formatNumber(model.total_tokens)} ток.
                        </div>
                      ))
                    ) : (
                      <div>модели ещё не зафиксированы</div>
                    )}
                  </div>
                </div>

                <div className="rounded-lg bg-[var(--surface-elevated)] p-2">
                  <div className="font-medium text-[var(--text-primary)]">Очереди секций</div>
                  <div className="mt-1">
                    ready {formatNumber(laneReady)} · leased {formatNumber(laneLeased)} · done{' '}
                    {formatNumber(laneDone)} · failed {formatNumber(laneFailed)} · waiting{' '}
                    {formatNumber(laneWaiting)}
                  </div>
                </div>
              </div>

              <div>
                <div className="mb-1 font-medium text-[var(--text-primary)]">Этапы</div>
                <div className="grid gap-1 [grid-template-columns:repeat(auto-fit,minmax(180px,1fr))]">
                  {stages.map((stage) => (
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

              {timeline.length > 0 && (
                <details className="rounded-lg bg-[var(--surface-elevated)] p-2" open>
                  <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                    Последние события
                  </summary>
                  <div className="mt-2 space-y-1">
                    {timeline.slice(0, 8).map((entry) => (
                      <div
                        key={entry.timeline_entry_id}
                        className="rounded bg-[var(--control-bg)] px-2 py-1"
                      >
                        <div className="font-medium text-[var(--text-primary)]">
                          {liveTimelineEventLabel(entry)}
                        </div>
                        <div className="text-[var(--text-muted)]">
                          {entry.message}
                          {entry.work_item_id ? ` · ${entry.work_item_id}` : ''}
                          {entry.attempt_id ? ` · ${entry.attempt_id}` : ''}
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              )}

              {lanes.length > 0 && (
                <details className="rounded-lg bg-[var(--surface-elevated)] p-2">
                  <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                    Потоки секций
                  </summary>
                  <div className="mt-2 space-y-2">
                    {lanes.map((lane) => (
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

              {attempts.length > 0 && (
                <details className="rounded-lg bg-[var(--surface-elevated)] p-2">
                  <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                    LLM attempts
                  </summary>
                  <div className="mt-2 space-y-1">
                    {attempts.slice(0, 8).map((attempt) => (
                      <div
                        key={attempt.node_run_id}
                        className="rounded bg-[var(--control-bg)] px-2 py-1"
                      >
                        <div>
                          {attempt.node_name} · {attempt.status} · {attempt.model_provider || 'provider'} /{' '}
                          {attempt.model_name || 'model'}
                        </div>
                        <div className="text-[var(--text-muted)]">
                          {formatNumber(attempt.total_tokens)} ток. · {formatMilliseconds(attempt.duration_ms)}
                          {attempt.error_message_user ? ` · ${attempt.error_message_user}` : ''}
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              )}

              {actions.filter((action) => action.visible).length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {actions
                    .filter((action) => action.visible)
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
              )}

              {workflow.curation.available && workflow.curation.workflow_run_id && (
                <div className="rounded-lg bg-[var(--accent-primary)]/10 px-2 py-1 text-[var(--accent-primary)]">
                  Курация готова: workflow_run_id {workflow.curation.workflow_run_id}
                </div>
              )}
            </div>
          </details>
        )}
      </div>
    </div>
  );
};
