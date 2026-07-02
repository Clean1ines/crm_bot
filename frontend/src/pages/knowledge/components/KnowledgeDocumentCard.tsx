import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, FileText, Trash2, Zap } from 'lucide-react';

import { visibleWorkflowActions, workflowActionLabel } from '../workflow/workflowActions';
import {
  normalize,
  phaseLabel,
  workflowStageHasStarted,
  workflowStatusLabel,
} from './workflow-card/workflowCardLabels';
import { ClaimBuilderPanel } from './claim-builder/ClaimBuilderPanel';
import { selectClaimBuilderSectionRows } from './claim-builder/claimBuilderSelectors';
import { SourceIngestionProgressPanel } from './source-ingestion/SourceIngestionProgressPanel';
import { selectSourceIngestionProgress } from './source-ingestion/sourceIngestionSelectors';
import { WorkflowStagesPanel } from './workflow-stages/WorkflowStagesPanel';
import { selectWorkflowStageRows } from './workflow-stages/workflowStagesSelectors';
import { WorkflowTimerCard } from './workflow-timer/WorkflowTimerCard';
import type { WorkflowTimerInput } from './workflow-timer/workflowTimerTypes';
import { ClaimClustersPanel } from './claim-clusters/ClaimClustersPanel';
import { selectClaimClustersView } from './claim-clusters/claimClusterSelectors';
import { t } from '@shared/i18n';
import {
  type KnowledgeSourceUnitsResponse,
  type WorkbenchWorkflowActionLiveState,
  type WorkbenchWorkflowLiveStateResponse,
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
  onCardAction: (actionId: string) => Promise<void> | void;
  onOpenCuration: (workflowRunId?: string | null) => void;
  workflowLiveState?: WorkbenchWorkflowLiveStateResponse | null;
  workflowLiveStateLoading?: boolean;
  workflowLiveStateError?: string | null;
  sourceUnitsResponse?: KnowledgeSourceUnitsResponse | null;
  formatSize: (bytes: number) => string;
  knowledgeProcessingModeLabel: (value: string) => string;
};

type ProcessingControlOverride = {
  state: 'running' | 'paused';
  occurredAt: string;
  frozenElapsedSeconds: number;
};

const formatNumber = (value: number): string =>
  new Intl.NumberFormat('ru-RU').format(Math.max(0, Math.floor(value || 0)));

const disabledActionTitle = (action: WorkbenchWorkflowActionLiveState): string => {
  if (action.enabled) return workflowActionLabel(action);

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

export const KnowledgeDocumentCard: React.FC<KnowledgeDocumentCardProps> = ({
  doc,
  isDeletePending,
  onRequestDelete,
  onCardAction,
  onOpenCuration,
  workflowLiveState,
  workflowLiveStateLoading = false,
  workflowLiveStateError = null,
  sourceUnitsResponse = null,
  formatSize,
  knowledgeProcessingModeLabel,
}) => {
  const workflow = workflowLiveState?.workflow ?? null;
  const timer = workflow?.timer ?? null;
  const [processingControlOverride, setProcessingControlOverride] =
    useState<ProcessingControlOverride | null>(null);

  const workflowStatus = workflow?.workflow_status ?? null;
  const currentPhase = workflow?.current_phase ?? null;
  const stages = workflow?.stages ?? [];
  const lanes = workflow?.section_lanes ?? [];
  const attempts = workflow?.llm_attempts ?? [];
  const actions = workflow?.actions ?? [];
  const workflowTimerMode = normalize(timer?.mode);
  const workflowState = normalize(workflowStatus);

  useEffect(() => {
    setProcessingControlOverride(null);
  }, [workflowTimerMode, workflowState, workflow?.workflow_run_id]);

  const isTerminalWorkflow = [
    'completed',
    'done',
    'published',
    'failed',
    'cancelled',
    'stopped',
  ].includes(workflowState) || [
    'completed',
    'published',
    'stopped',
  ].includes(workflowTimerMode);
  const backendPauseAction = actions.find(
    (action) =>
      normalize(action.action_id) === 'pause_processing' &&
      action.visible &&
      action.enabled,
  );
  const backendResumeAction = actions.find(
    (action) =>
      normalize(action.action_id) === 'resume_processing' &&
      action.visible &&
      action.enabled,
  );

  const primaryProcessingAction =
    processingControlOverride?.state === 'paused'
      ? backendResumeAction
      : processingControlOverride?.state === 'running'
        ? backendPauseAction
        : backendResumeAction ?? backendPauseAction ?? null;
  const primaryProcessingActionId =
    processingControlOverride?.state === 'paused'
      ? 'resume_processing'
      : processingControlOverride?.state === 'running'
        ? 'pause_processing'
        : primaryProcessingAction?.action_id ?? null;
  const canShowPrimaryProcessingControl =
    Boolean(workflow) && !isTerminalWorkflow && primaryProcessingActionId !== null;
  const usage = workflow?.usage ?? null;
  const claimBuilderSectionRows = useMemo(
    () => selectClaimBuilderSectionRows(workflowLiveState, sourceUnitsResponse),
    [workflowLiveState, sourceUnitsResponse],
  );
  const claimBuilderDraftArtifacts = useMemo(
    () =>
      claimBuilderSectionRows.flatMap((row) =>
        row.attempts.flatMap((attempt) => attempt.artifacts),
      ),
    [claimBuilderSectionRows],
  );
  const clustersView = useMemo(
    () => selectClaimClustersView(workflow, claimBuilderDraftArtifacts),
    [workflow, claimBuilderDraftArtifacts],
  );

  const sourceIngestionProgress = useMemo(
    () => selectSourceIngestionProgress(workflowLiveState),
    [workflowLiveState],
  );
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
  const workflowStageRows = useMemo(
    () =>
      selectWorkflowStageRows(stages, {
        hasClaimClusters: clustersView.hasClusters,
        embeddedClaimCount: clustersView.embeddedClaimCount,
        clusteredClaimCount: clustersView.clusteredClaimCount,
        claimClusterCount: clustersView.clusters.length,
        hasCompactionComparisons: clustersView.hasComparisons,
        compactedClusterCount: clustersView.compactedClusterCount,
      }),
    [
      stages,
      clustersView.hasClusters,
      clustersView.embeddedClaimCount,
      clustersView.clusteredClaimCount,
      clustersView.clusters.length,
      clustersView.hasComparisons,
      clustersView.compactedClusterCount,
    ],
  );

  const sectionItems = lanes
    .flatMap((lane) => lane.items)
    .sort((left, right) => left.section_index - right.section_index);

  const llmUsageVisible =
    attempts.length > 0 ||
    workflowStageHasStarted(claimStage) ||
    workflowStageHasStarted(embeddingStage) ||
    workflowStageHasStarted(clusterStage) ||
    workflowStageHasStarted(compactionStage);
  const resultSummaryVisible =
    workflowStageHasStarted(previewStage) ||
    workflow?.curation.available ||
    clustersView.hasClusters ||
    clustersView.hasComparisons ||
    clustersView.finalFacts.length > 0;

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

  const resultSummaryText = workflow
    ? clustersView.hasClusters || clustersView.hasComparisons
      ? `Черновики утверждений: ${formatNumber(
          clustersView.hasClusters ? clustersView.clusteredClaimCount : claimStage?.current ?? 0,
        )} · Векторы: ${formatNumber(
          clustersView.hasClusters ? clustersView.embeddedClaimCount : embeddingStage?.current ?? 0,
        )} · Группы: ${formatNumber(
          clustersView.hasClusters ? clustersView.clusters.length : clusterStage?.current ?? 0,
        )} · Сравнения: ${formatNumber(
          clustersView.hasComparisons
            ? clustersView.resolvedComparisonCount
            : compactionStage?.current ?? 0,
        )} / ${formatNumber(
          clustersView.hasComparisons
            ? clustersView.comparisons.length
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

  const timerTimestampMs = (value: string | null | undefined): number | null => {
    if (!value) return null;
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const timerSafeSeconds = (value: number | null | undefined): number => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
    return Math.max(0, Math.floor(value));
  };

  const elapsedSecondsAt = (
    inputTimer: WorkflowTimerInput,
    nowMs: number,
  ): number => {
    const baseElapsedSeconds = timerSafeSeconds(inputTimer?.active_elapsed_seconds);
    if (!inputTimer?.is_live) return baseElapsedSeconds;

    const activeStartedAtMs = timerTimestampMs(inputTimer.current_active_started_at);
    if (activeStartedAtMs === null) return baseElapsedSeconds;

    return baseElapsedSeconds + Math.max(0, Math.floor((nowMs - activeStartedAtMs) / 1000));
  };

  const effectiveWorkflowStatus =
    processingControlOverride?.state === 'paused'
      ? 'PAUSED'
      : processingControlOverride?.state === 'running'
        ? 'RUNNING'
        : workflowStatus;

  const effectiveTimer: WorkflowTimerInput =
    processingControlOverride?.state === 'paused'
      ? {
          ...(timer ?? {}),
          mode: 'paused',
          active_elapsed_seconds: processingControlOverride.frozenElapsedSeconds,
          is_live: false,
          current_active_started_at: null,
        }
      : processingControlOverride?.state === 'running'
        ? {
            ...(timer ?? {}),
            mode: 'running',
            active_elapsed_seconds: processingControlOverride.frozenElapsedSeconds,
            is_live: true,
            current_active_started_at: processingControlOverride.occurredAt,
          }
        : timer;

  const handlePrimaryProcessingControl = async (): Promise<void> => {
    if (!canShowPrimaryProcessingControl || primaryProcessingActionId === null) {
      return;
    }

    const actionId = primaryProcessingActionId;
    try {
      await onCardAction(actionId);
    } catch {
      return;
    }

    const occurredAt = new Date().toISOString();
    const frozenElapsedSeconds = elapsedSecondsAt(effectiveTimer, Date.parse(occurredAt));

    if (actionId === 'pause_processing') {
      setProcessingControlOverride({
        state: 'paused',
        occurredAt,
        frozenElapsedSeconds,
      });
      return;
    }

    if (actionId === 'resume_processing') {
      setProcessingControlOverride({
        state: 'running',
        occurredAt,
        frozenElapsedSeconds,
      });
    }
  };

  const handleLiveAction = (action: WorkbenchWorkflowActionLiveState): void => {
    if (!canRunLiveAction(action)) return;

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
          {canShowPrimaryProcessingControl && (
            <button
              type="button"
              onClick={handlePrimaryProcessingControl}
              title={primaryProcessingAction?.reason_code || undefined}
              className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20"
            >
              {primaryProcessingActionId === 'pause_processing' ? 'Пауза' : 'Продолжить'}
            </button>
          )}
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
          {sourceIngestionProgress.failedCount > 0 && (
            <p className="mt-1 text-amber-700 dark:text-amber-300">
              {formatNumber(sourceIngestionProgress.failedCount)} раздела требуют повторной обработки.
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

        <ClaimClustersPanel view={clustersView} formatNumber={formatNumber}>
          {({ summary, details }) => (
            <>
              <div className="grid gap-2 text-xs [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
          <WorkflowTimerCard
            timer={effectiveTimer}
            workflowStatus={effectiveWorkflowStatus}
          />

          {llmUsageVisible && (
            <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
              <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
                <Zap className="h-3.5 w-3.5" />
                ИИ
              </div>
              <div className="text-[var(--text-muted)]">{llmUsageText}</div>
            </div>
          )}

          <SourceIngestionProgressPanel
            progress={sourceIngestionProgress}
            formatNumber={formatNumber}
          />

          {summary}

          {resultSummaryVisible && (
            <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
              <div className="mb-1 font-medium text-[var(--text-primary)]">Итог</div>
              <div className="text-[var(--text-muted)]">{resultSummaryText}</div>
            </div>
          )}
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
              <WorkflowStagesPanel
                rows={workflowStageRows}
                formatNumber={formatNumber}
              />

              {details}

              {sectionItems.length > 0 && (
                <ClaimBuilderPanel sectionRows={claimBuilderSectionRows} />
              )}


              {visibleWorkflowActions(actions).filter(
                (action) =>
                  normalize(action.action_id) !== 'pause_processing' &&
                  normalize(action.action_id) !== 'resume_processing',
              ).length > 0 && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {visibleWorkflowActions(actions).filter(
                    (action) =>
                      normalize(action.action_id) !== 'pause_processing' &&
                      normalize(action.action_id) !== 'resume_processing',
                  ).map((action) => (
                      <button
                        key={action.action_id}
                        type="button"
                        disabled={!canRunLiveAction(action)}
                        title={disabledActionTitle(action)}
                        onClick={() => handleLiveAction(action)}
                        className={liveActionClassName(action)}
                      >
                        {workflowActionLabel(action)}
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
            </>
          )}
        </ClaimClustersPanel>
      </div>
    </div>
  );
};
