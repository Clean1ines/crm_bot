import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Clock3, FileText, Trash2, Zap } from 'lucide-react';

import { visibleWorkflowActions, workflowActionLabel } from '../workflow/workflowActions';
import {
  attemptRowTone,
  attemptStatusLabel,
  clusterHumanState,
  clusterStatusTitle,
  clusterStatusTone,
  embeddingStatusLabel,
  nodeActivityLabel,
  normalize,
  phaseLabel,
  queueRowTone,
  queueStatusLabel,
  queueStatusTone,
  statusPillTone,
  userErrorLabel,
  workflowStageHasStarted,
  workflowStatusLabel,
} from './workflow-card/workflowCardLabels';
import { ClaimBuilderPanel } from './claim-builder/ClaimBuilderPanel';
import { selectClaimBuilderSectionRows } from './claim-builder/claimBuilderSelectors';
import { SourceIngestionProgressPanel } from './source-ingestion/SourceIngestionProgressPanel';
import { selectSourceIngestionProgress } from './source-ingestion/sourceIngestionSelectors';
import { WorkflowStagesPanel } from './workflow-stages/WorkflowStagesPanel';
import { selectWorkflowStageRows } from './workflow-stages/workflowStagesSelectors';
import { t } from '@shared/i18n';
import {
  type KnowledgeSourceUnitsResponse,
  type WorkbenchWorkflowActionLiveState,
  type WorkbenchWorkflowLiveStateResponse,
  type WorkbenchClaimClusterClaimLiveState,
  WorkbenchCompactedClaimPreviewLiveState,
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
  const timerStartedAt = timer?.current_active_started_at ?? null;
  const timerStartedAtMs = timerStartedAt ? Date.parse(timerStartedAt) : Number.NaN;
  const isLiveTimer = Boolean(timer?.is_live && timerStartedAt);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [optimisticProcessingControl, setOptimisticProcessingControl] = useState<
    'running' | 'paused' | null
  >(null);

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
  const actions = workflow?.actions ?? [];
  const workflowTimerMode = normalize(timer?.mode);
  const workflowState = normalize(workflowStatus);

  useEffect(() => {
    setOptimisticProcessingControl(null);
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
    (action) => normalize(action.action_id) === 'pause_processing',
  );
  const backendResumeAction = actions.find(
    (action) => normalize(action.action_id) === 'resume_processing',
  );
  const effectiveProcessingControlState =
    optimisticProcessingControl ??
    (workflowTimerMode === 'paused' || workflowState === 'paused'
      ? 'paused'
      : 'running');
  const primaryProcessingActionId =
    effectiveProcessingControlState === 'paused'
      ? 'resume_processing'
      : 'pause_processing';
  const primaryProcessingAction =
    primaryProcessingActionId === 'pause_processing'
      ? backendPauseAction
      : backendResumeAction;
  const canShowPrimaryProcessingControl = Boolean(workflow) && !isTerminalWorkflow;
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
        : claimBuilderDraftArtifacts.map((artifact) => ({
            key: artifact.observationRef,
            text: artifact.claim,
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

  const workflowStageRows = useMemo(
    () =>
      selectWorkflowStageRows(stages, {
        hasClaimClusters,
        embeddedClaimCount,
        clusteredClaimCount,
        claimClusterCount: claimClusters.length,
        hasCompactionComparisons,
        compactedClusterCount,
      }),
    [
      stages,
      hasClaimClusters,
      embeddedClaimCount,
      clusteredClaimCount,
      claimClusters.length,
      hasCompactionComparisons,
      compactedClusterCount,
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
    hasClaimClusters ||
    hasCompactionComparisons ||
    finalCompactedFacts.length > 0;

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

  const handlePrimaryProcessingControl = (): void => {
    if (!canShowPrimaryProcessingControl) return;

    const actionId = primaryProcessingActionId;
    setOptimisticProcessingControl(
      actionId === 'pause_processing' ? 'paused' : 'running',
    );
    onCardAction(actionId);
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

  const renderEnrichedCompactedArtifact = (
    compactedClaim: WorkbenchCompactedClaimPreviewLiveState,
  ) => {
    const artifact = compactedClaim.compacted_payload;
    const triples = artifact?.triples ?? [];
    const possibleQuestions: string[] = artifact?.possible_questions ?? [];
    const exclusionScope = artifact?.exclusion_scope?.trim() ?? "";
    const evidenceBlock = artifact?.evidence_block?.trim() ?? "";

    return (
      <details className="mt-2 rounded bg-[var(--control-bg)] p-2" open>
        <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
          Enriched artifact
        </summary>
        <div className="mt-2 space-y-3 text-[var(--text-secondary)]">
          <div>
            <div className="font-medium text-[var(--text-primary)]">Утверждение</div>
            <div>{artifact?.claim || compactedClaim.claim}</div>
          </div>

          <div className="grid gap-1 text-[var(--text-muted)] [grid-template-columns:repeat(auto-fit,minmax(150px,1fr))]">
            <div>Тип: {artifact?.claim_kind || compactedClaim.claim_kind || "—"}</div>
            <div>Гранулярность: {artifact?.granularity || compactedClaim.granularity || "—"}</div>
            <div>Решение: {artifact?.merge_decision || compactedClaim.merge_decision || "—"}</div>
          </div>

          {possibleQuestions.length > 0 && (
            <div>
              <div className="font-medium text-[var(--text-primary)]">
                Возможные вопросы
              </div>
              <ul className="mt-1 list-disc pl-5">
                {possibleQuestions.map((question) => (
                  <li key={question}>{question}</li>
                ))}
              </ul>
            </div>
          )}

          {exclusionScope && (
            <div>
              <div className="font-medium text-[var(--text-primary)]">
                Исключения
              </div>
              <pre className="mt-1 whitespace-pre-wrap rounded bg-[var(--surface-elevated)] p-2 text-[var(--text-secondary)]">
                {exclusionScope}
              </pre>
            </div>
          )}

          {triples.length > 0 && (
            <div>
              <div className="font-medium text-[var(--text-primary)]">Тройки</div>
              <ul className="mt-1 list-disc pl-5">
                {triples.map((triple: NonNullable<NonNullable<WorkbenchCompactedClaimPreviewLiveState["compacted_payload"]>["triples"]>[number], index: number) => (
                  <li key={`${triple.subject ?? "s"}-${triple.predicate ?? "p"}-${triple.object ?? "o"}-${index}`}>
                    {triple.subject || "—"} · {triple.predicate || "—"} · {triple.object || "—"}
                    {(triple.qualifiers ?? []).length > 0
                      ? ` (${(triple.qualifiers ?? []).join(", ")})`
                      : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {evidenceBlock && (
            <div>
              <div className="font-medium text-[var(--text-primary)]">
                Доказательство
              </div>
              <blockquote className="mt-1 whitespace-pre-wrap rounded border-l-2 border-[var(--accent-primary)] bg-[var(--surface-elevated)] p-2">
                {evidenceBlock}
              </blockquote>
            </div>
          )}
        </div>
      </details>
    );
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

        <div className="grid gap-2 text-xs [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
          <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
              <Clock3 className="h-3.5 w-3.5" />
              Активная обработка
            </div>
            <div className="text-[var(--text-muted)]">{elapsedText}</div>
          </div>

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
                        {renderEnrichedCompactedArtifact(fact)}
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

                        {(cluster.batches ?? []).length > 0 && (
                          <div className="mt-2 space-y-1 rounded-lg bg-[var(--surface-elevated)] p-2">
                            <div className="font-medium text-[var(--text-primary)]">
                              Батчи compaction: {formatNumber(cluster.batches?.length ?? 0)}
                            </div>
                            <div className="mt-1 space-y-1">
                              {(cluster.batches ?? []).map((batch, batchIndex) => (
                                <div
                                  key={batch.batch_ref}
                                  className="flex flex-wrap items-center justify-between gap-2 rounded border border-[var(--border-subtle)] bg-[var(--surface-secondary)] px-2 py-1"
                                >
                                  <span className="font-medium text-[var(--text-primary)]">
                                    Batch {formatNumber(batchIndex + 1)}
                                  </span>
                                  <span className="text-[var(--text-muted)]">
                                    утверждений: {formatNumber(batch.member_count)}
                                  </span>
                                  <span className={`rounded-full px-2 py-0.5 font-medium ${statusPillTone(batch.status)}`}>
                                    {queueStatusLabel(batch.status)}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

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
      </div>
    </div>
  );
};
