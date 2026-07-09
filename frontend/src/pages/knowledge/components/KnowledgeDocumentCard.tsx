import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
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
import { CurationNotice } from './document-card/CurationNotice';
import { DocumentCardHeader } from './document-card/DocumentCardHeader';
import { DocumentOverviewPanel } from './document-card/DocumentOverviewPanel';
import { LlmUsageCard } from './document-card/LlmUsageCard';
import { ResultSummaryCard } from './document-card/ResultSummaryCard';
import { WorkflowActionsPanel } from './document-card/WorkflowActionsPanel';
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
  workflowProjectionState?: WorkbenchWorkflowLiveStateResponse | null;
  workflowProjectionStateLoading?: boolean;
  workflowProjectionStateError?: string | null;
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

export const KnowledgeDocumentCard: React.FC<KnowledgeDocumentCardProps> = ({
  doc,
  isDeletePending,
  onRequestDelete,
  onCardAction,
  onOpenCuration,
  workflowProjectionState,
  workflowProjectionStateLoading = false,
  workflowProjectionStateError = null,
  sourceUnitsResponse = null,
  formatSize,
  knowledgeProcessingModeLabel,
}) => {
  const workflow = workflowProjectionState?.workflow ?? null;
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

  const backendOpenCurationAction = actions.find(
    (action) =>
      normalize(action.action_id) === 'open_curation' &&
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
  const primaryHeaderActionId =
    backendOpenCurationAction?.action_id ?? primaryProcessingActionId;
  const primaryHeaderActionReason =
    backendOpenCurationAction?.reason_code ?? primaryProcessingAction?.reason_code ?? null;
  const primaryHeaderActionLabel =
    backendOpenCurationAction !== undefined ? 'Открыть проверку' : null;
  const canShowPrimaryProcessingControl =
    Boolean(workflow) && !isTerminalWorkflow && primaryProcessingActionId !== null;
  const canShowPrimaryHeaderControl =
    Boolean(workflow) &&
    (backendOpenCurationAction !== undefined || canShowPrimaryProcessingControl);
  const usage = workflow?.usage ?? null;
  const claimBuilderSectionRows = useMemo(
    () => selectClaimBuilderSectionRows(workflowProjectionState, sourceUnitsResponse),
    [workflowProjectionState, sourceUnitsResponse],
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
    () => selectSourceIngestionProgress(workflowProjectionState),
    [workflowProjectionState],
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
  const startedStageIds = useMemo(() => {
    const ids: string[] = [];

    if (clustersView.hasClusters) {
      ids.push('draft_claim_embeddings', 'draft_claim_clustering');
    }

    if (clustersView.hasComparisons || clustersView.finalFacts.length > 0) {
      ids.push('draft_claim_compaction');
    }

    return ids;
  }, [
    clustersView.hasClusters,
    clustersView.hasComparisons,
    clustersView.finalFacts.length,
  ]);
  const workflowStageRows = useMemo(
    () =>
      selectWorkflowStageRows(stages, {
        hasClaimClusters: clustersView.hasClusters,
        embeddedClaimCount: clustersView.embeddedClaimCount,
        clusteredClaimCount: clustersView.clusteredClaimCount,
        claimClusterCount: clustersView.clusters.length,
        hasCompactionComparisons: clustersView.hasComparisons,
        compactedClusterCount: clustersView.compactedClusterCount,
        finalCompactedFactCount: clustersView.finalFacts.length,
        startedStageIds,
      }),
    [
      stages,
      clustersView.hasClusters,
      clustersView.embeddedClaimCount,
      clustersView.clusteredClaimCount,
      clustersView.clusters.length,
      clustersView.hasComparisons,
      clustersView.compactedClusterCount,
      clustersView.finalFacts.length,
      startedStageIds,
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
    : workflowProjectionStateLoading
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
    if (backendOpenCurationAction !== undefined) {
      handleLiveAction(backendOpenCurationAction);
      return;
    }

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
    if (!action.enabled) return;

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
      <DocumentCardHeader
        workflowStatus={workflowStatus}
        canShowPrimaryProcessingControl={canShowPrimaryHeaderControl}
        primaryProcessingActionId={primaryHeaderActionId}
        primaryProcessingActionReason={primaryHeaderActionReason}
        primaryProcessingActionLabel={primaryHeaderActionLabel}
        isDeletePending={isDeletePending}
        onPrimaryProcessingControl={handlePrimaryProcessingControl}
        onRequestDelete={onRequestDelete}
      />

      <DocumentOverviewPanel
        fileName={doc.file_name}
        fileSizeText={fileSizeText}
        processingModeText={knowledgeProcessingModeLabel(doc.preprocessing_mode || 'faq')}
        headline={headline}
        phaseText={phaseText}
        failedSourceUnitCount={sourceIngestionProgress.failedCount}
        formatNumber={formatNumber}
      />

      <div className="mb-4 space-y-3">
        {workflowProjectionStateError && (
          <div className="flex gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none" />
            <span>{workflowProjectionStateError}</span>
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

          <LlmUsageCard visible={llmUsageVisible} usageText={llmUsageText} />

          <SourceIngestionProgressPanel
            progress={sourceIngestionProgress}
            formatNumber={formatNumber}
          />

          {summary}

          <ResultSummaryCard visible={resultSummaryVisible} summaryText={resultSummaryText} />
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


              <WorkflowActionsPanel actions={actions} onAction={handleLiveAction} />

              <CurationNotice
                available={workflow.curation.available}
                workflowRunId={workflow.curation.workflow_run_id}
              />
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
