import React from 'react';
import { Loader2 } from 'lucide-react';

import { type KnowledgeAnswerDraftsResponse, type KnowledgeProcessingReport, type KnowledgeSourceUnitsResponse } from '@shared/api/modules/knowledge';
import { t } from '@shared/i18n';

type MetricsRecord = Record<string, unknown>;

type DocumentLite = {
  id: string;
  preprocessing_metrics?: unknown;
};

const metricObject = (value: unknown): MetricsRecord | null => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as MetricsRecord
    : null
);

const activeMetrics = (
  doc: DocumentLite,
  processingReport: KnowledgeProcessingReport | undefined,
): MetricsRecord | null => (
  metricObject(doc.preprocessing_metrics) ?? metricObject(processingReport?.metrics)
);

const metricNumber = (metrics: MetricsRecord | null | undefined, key: string): number | null => {
  const value = metrics?.[key];
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) return Number(value);
  return null;
};

const metricText = (metrics: MetricsRecord | null | undefined, key: string): string | null => {
  const value = metrics?.[key];
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed || null;
};

const metricBoolean = (metrics: MetricsRecord | null | undefined, key: string): boolean => {
  const value = metrics?.[key];
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return value.trim().toLowerCase() === 'true';
  return false;
};

const formatCounts = (value: unknown): string | null => {
  const record = metricObject(value);
  if (!record) return null;
  const parts = Object.entries(record)
    .filter(([, item]) => typeof item === 'number' && Number.isFinite(item) && item > 0)
    .map(([key, item]) => `${key}: ${item}`);
  return parts.length > 0 ? parts.join(', ') : null;
};

const clampPercent = (value: number): number => Math.max(0, Math.min(100, Math.round(value)));

const faqStageProgressPercent = (metrics: MetricsRecord | null): number | null => {
  const stage = metricText(metrics, 'stage') ?? metricText(metrics, 'faq_surface_stage');
  const sourceUnitCount = metricNumber(metrics, 'source_unit_count');
  const sourceUnitIndex = metricNumber(metrics, 'source_unit_index');
  const candidateCount = metricNumber(metrics, 'candidate_count');
  const candidateIndex = metricNumber(metrics, 'candidate_index');

  if (stage === 'faq_retrieval_surface_compilation_completed') return 100;
  if (stage === 'source_units' || stage === 'faq_surface_graph_parallel_bootstrap') return 5;
  if (stage === 'global_reconciliation') return 90;
  if (stage === 'global_relation_judge') return 95;
  if (stage === 'question_reassignment') return 98;
  if (!sourceUnitCount || sourceUnitCount <= 0 || !sourceUnitIndex || sourceUnitIndex <= 0) return null;

  const completedUnits = Math.max(0, Math.min(sourceUnitCount, sourceUnitIndex - 1));
  const candidateProgress = candidateCount && candidateCount > 0
    ? Math.max(0, Math.min(1, (candidateIndex ?? 0) / candidateCount))
    : 0;

  let unitFraction = 0.1;
  if (stage === 'relation_planning') unitFraction = 0.25;
  if (stage === 'answer_synthesis') unitFraction = 0.25 + 0.35 * candidateProgress;
  if (stage === 'question_ownership') unitFraction = 0.65 + 0.25 * candidateProgress;
  if (stage === 'partial_surface_cards') unitFraction = 1;

  const sourceUnitProgress = Math.max(0, Math.min(1, (completedUnits + unitFraction) / sourceUnitCount));
  return clampPercent(5 + 85 * sourceUnitProgress);
};

const faqProgressLabel = (
  metrics: MetricsRecord | null,
  formatNumber: (value: number) => string,
): string | null => {
  const stage = metricText(metrics, 'stage') ?? metricText(metrics, 'faq_surface_stage');
  const sourceUnitCount = metricNumber(metrics, 'source_unit_count');
  const sourceUnitIndex = metricNumber(metrics, 'source_unit_index');
  const candidateCount = metricNumber(metrics, 'candidate_count');
  const candidateIndex = metricNumber(metrics, 'candidate_index');

  if (!stage) return null;
  if (sourceUnitCount && sourceUnitCount > 0 && sourceUnitIndex && sourceUnitIndex > 0) {
    const sourceText = `source unit ${formatNumber(sourceUnitIndex)} / ${formatNumber(sourceUnitCount)}`;
    if (candidateCount && candidateCount > 0 && candidateIndex && candidateIndex > 0) {
      return `${sourceText}, candidate ${formatNumber(candidateIndex)} / ${formatNumber(candidateCount)}`;
    }
    return sourceText;
  }
  if (stage.startsWith('global_') || stage === 'question_reassignment') return `global stage: ${stage}`;
  return null;
};


const economyModeRows = (
  doc: DocumentLite,
  processingReport: KnowledgeProcessingReport | undefined,
  formatNumber: (value: number) => string,
): string[] => {
  const metrics = activeMetrics(doc, processingReport);
  if (!metrics || !metricBoolean(metrics, 'economy_mode')) return [];

  const rows: string[] = ['Economy mode: enabled'];
  const reason = metricText(metrics, 'economy_reason');
  const splitCount = metricNumber(metrics, 'economy_source_unit_split_count')
    ?? metricNumber(metrics, 'economy_subunit_count');
  const completedSubunits = metricNumber(metrics, 'economy_completed_subunit_count');
  const warning = metricText(metrics, 'economy_quality_warning')
    ?? metricText(metrics, 'quality_warning');

  if (reason) rows.push(`Economy reason: ${reason}`);
  if (splitCount !== null) rows.push(`Source unit split count: ${formatNumber(splitCount)}`);
  if (completedSubunits !== null) {
    rows.push(`Instant subunits completed: ${formatNumber(completedSubunits)}`);
  }
  if (warning) rows.push(`Quality warning: ${warning}`);

  return rows;
};

const groqRouteRows = (
  doc: DocumentLite,
  processingReport: KnowledgeProcessingReport | undefined,
  formatNumber: (value: number) => string,
): string[] => {
  const metrics = activeMetrics(doc, processingReport);
  if (!metrics) return [];

  const rows: string[] = [];
  const routeEvents = metricNumber(metrics, 'groq_route_event_count');
  const successes = metricNumber(metrics, 'groq_route_success_count');
  const failures = metricNumber(metrics, 'groq_route_failure_count');
  const cooldowns = metricNumber(metrics, 'groq_route_cooldown_block_count');
  const fallbacks = metricNumber(metrics, 'groq_route_fallback_count');
  const modelCounts = formatCounts(metrics.groq_actual_model_counts);
  const keySlotCounts = formatCounts(metrics.groq_key_slot_counts);
  const fallbackCounts = formatCounts(metrics.groq_fallback_reason_counts);
  const lastRoute = metricObject(metrics.groq_last_route_event);

  if (routeEvents !== null && routeEvents > 0) {
    rows.push(`Groq route events: ${formatNumber(routeEvents)}`);
  }
  if (successes !== null || failures !== null || cooldowns !== null || fallbacks !== null) {
    rows.push(
      `Groq routes: ok ${formatNumber(successes ?? 0)}, failed ${formatNumber(failures ?? 0)}, cooldown ${formatNumber(cooldowns ?? 0)}, fallback ${formatNumber(fallbacks ?? 0)}`,
    );
  }
  if (modelCounts) rows.push(`Groq actual models: ${modelCounts}`);
  if (keySlotCounts) rows.push(`Groq key slots: ${keySlotCounts}`);
  if (fallbackCounts) rows.push(`Groq fallback reasons: ${fallbackCounts}`);

  if (lastRoute) {
    const status = metricText(lastRoute, 'status');
    const keySlot = metricText(lastRoute, 'key_slot_label');
    const requestedModel = metricText(lastRoute, 'requested_model');
    const routedModel = metricText(lastRoute, 'routed_model');
    const fallbackReason = metricText(lastRoute, 'fallback_reason');
    const limitKind = metricText(lastRoute, 'limit_kind');
    const retryAfter = metricNumber(lastRoute, 'retry_after_seconds');
    const promptTokens = metricNumber(lastRoute, 'prompt_tokens');
    const completionTokens = metricNumber(lastRoute, 'completion_tokens');
    const totalTokens = metricNumber(lastRoute, 'total_tokens');

    const modelText = requestedModel && routedModel && requestedModel !== routedModel
      ? `${requestedModel} → ${routedModel}`
      : routedModel || requestedModel;
    const parts = [
      status ? `status ${status}` : null,
      keySlot ? `key ${keySlot}` : null,
      modelText ? `model ${modelText}` : null,
      fallbackReason ? `fallback ${fallbackReason}` : null,
      limitKind ? `limit ${limitKind}` : null,
      retryAfter !== null && retryAfter > 0 ? `retry after ${Math.ceil(retryAfter)}s` : null,
    ].filter(Boolean);
    if (parts.length > 0) rows.push(`Last Groq route: ${parts.join(', ')}`);
    if ((promptTokens ?? 0) > 0 || (completionTokens ?? 0) > 0 || (totalTokens ?? 0) > 0) {
      rows.push(
        `Last Groq tokens: prompt ${formatNumber(promptTokens ?? 0)}, completion ${formatNumber(completionTokens ?? 0)}, total ${formatNumber(totalTokens ?? 0)}`,
      );
    }

    const quotaState = metricObject(lastRoute.quota_state);
    if (quotaState) {
      const remainingRequests = metricNumber(quotaState, 'remaining_requests');
      const remainingTokens = metricNumber(quotaState, 'remaining_tokens');
      const cooldown = metricNumber(quotaState, 'cooldown_remaining_seconds');
      const resetRequestsEpoch = metricNumber(quotaState, 'reset_requests_epoch');
      const resetTokensEpoch = metricNumber(quotaState, 'reset_tokens_epoch');
      const quotaParts = [
        remainingRequests !== null ? `requests left ${formatNumber(remainingRequests)}` : null,
        remainingTokens !== null ? `tokens left ${formatNumber(remainingTokens)}` : null,
        cooldown !== null && cooldown > 0 ? `cooldown ${Math.ceil(cooldown)}s` : null,
        resetRequestsEpoch !== null ? `requests reset ${new Date(resetRequestsEpoch * 1000).toLocaleTimeString()}` : null,
        resetTokensEpoch !== null ? `tokens reset ${new Date(resetTokensEpoch * 1000).toLocaleTimeString()}` : null,
      ].filter(Boolean);
      if (quotaParts.length > 0) rows.push(`Groq quota: ${quotaParts.join(', ')}`);
    }
  }

  return rows;
};

export const DocumentProcessingBlock: React.FC<{
  doc: DocumentLite;
  processingReport: KnowledgeProcessingReport | undefined;
  isDocumentProcessing: boolean;
  showCompletedElapsed: boolean;
  processingProgressLabel: string;
  processingProgressPercent: number | null;
  processingStatusMessage: string;
  processingModelLabel: string;
  processingElapsedLabel: string;
  processingDetailRows: string[];
  sourceChunkCount: number | null;
  incomingAnswerCandidateCount: number | null;
  answerResolutionCount: number | null;
  documentLlmTokenText: string | null;
  documentLlmModels: string | null;
  answerDraftsResponse: KnowledgeAnswerDraftsResponse | undefined;
  answerDraftsLoading: boolean;
  showDraftSummary: boolean;
  onOpenDrafts: () => void;
  sourceUnitsResponse: KnowledgeSourceUnitsResponse | undefined;
  sourceUnitsLoading: boolean;
  showSourceUnitsSummary: boolean;
  onOpenSourceUnits: () => void;
  onRetryFailedBatches: () => void;
  onPublishReady: () => void;
  onResumeProcessing: () => void;
  retryPending: boolean;
  retryTarget?: string;
  publishReadyPending: boolean;
  publishReadyTarget?: string;
  resumePending: boolean;
  resumeTarget?: string;
  formatNumber: (value: number) => string;
  answerResolutionStepId: string;
  renderDraftsSummary: (params: { response: KnowledgeAnswerDraftsResponse | undefined; isLoading: boolean; onOpen: () => void; }) => React.ReactNode;
  renderSourceUnitsSummary: (params: { response: KnowledgeSourceUnitsResponse | undefined; isLoading: boolean; onOpen: () => void; }) => React.ReactNode;
  renderAnswerResolutionTracePanel?: (report: KnowledgeProcessingReport) => React.ReactNode;
}> = ({
  doc,
  processingReport,
  isDocumentProcessing,
  showCompletedElapsed,
  processingProgressLabel,
  processingProgressPercent,
  processingStatusMessage,
  processingModelLabel,
  processingElapsedLabel,
  processingDetailRows,
  sourceChunkCount,
  incomingAnswerCandidateCount,
  answerResolutionCount,
  documentLlmTokenText,
  documentLlmModels,
  answerDraftsResponse,
  answerDraftsLoading,
  showDraftSummary,
  onOpenDrafts,
  sourceUnitsResponse,
  sourceUnitsLoading,
  showSourceUnitsSummary,
  onOpenSourceUnits,
  onRetryFailedBatches,
  onPublishReady,
  onResumeProcessing,
  retryPending,
  retryTarget,
  publishReadyPending,
  publishReadyTarget,
  resumePending,
  resumeTarget,
  formatNumber,
  answerResolutionStepId,
  renderDraftsSummary,
  renderSourceUnitsSummary,
  renderAnswerResolutionTracePanel,
}) => {
  const metrics = activeMetrics(doc, processingReport);
  const effectiveProgressPercent = processingProgressPercent ?? faqStageProgressPercent(metrics);
  const effectiveProgressLabel = faqProgressLabel(metrics, formatNumber) ?? processingProgressLabel;

  return (
    <>
      {processingReport && (
        <div className="mb-4 rounded-xl bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-muted)]">
          <div className="mb-1 font-semibold text-[var(--text-primary)]">
            {processingReport.title}
          </div>
          <p className="leading-relaxed">{processingReport.message}</p>
          {processingReport.steps.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {processingReport.steps.map((step) => (
                <div
                  key={step.id}
                  className={`rounded-lg ${step.id === answerResolutionStepId ? 'bg-[var(--control-bg)] px-2 py-1' : ''}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="font-medium text-[var(--text-primary)]">{step.label}</span>
                    <span className="text-right">
                      {step.total > 0
                        ? `${formatNumber(step.current)} / ${formatNumber(step.total)}`
                        : step.status}
                    </span>
                  </div>
                  {step.message && (
                    <div className="mt-0.5 leading-relaxed text-[var(--text-muted)]">
                      {step.message}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {showDraftSummary && renderDraftsSummary({
            response: answerDraftsResponse,
            isLoading: answerDraftsLoading,
            onOpen: onOpenDrafts,
          })}

          {showSourceUnitsSummary && renderSourceUnitsSummary({
            response: sourceUnitsResponse,
            isLoading: sourceUnitsLoading,
            onOpen: onOpenSourceUnits,
          })}

          {renderAnswerResolutionTracePanel?.(processingReport)}

          {processingReport.actions.length > 0 && (
            <div className="mt-3 border-t border-[var(--border-subtle)] pt-2">
              <div className="mb-1 font-medium text-[var(--text-primary)]">
                {t('knowledge.processReport.nextActions')}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {processingReport.actions.map((action) => {
                  const canRetry = action.id === 'retry_failed_batches' && action.enabled;
                  const canPublishReady = action.id === 'publish_ready' && action.enabled;
                  const canResume = action.id === 'resume_processing' && action.enabled;
                  const isRetryingThisDoc = retryPending && retryTarget === doc.id;
                  const isPublishingThisDoc = publishReadyPending && publishReadyTarget === doc.id;
                  const isResumingThisDoc = resumePending && resumeTarget === doc.id;

                  if (canRetry || canPublishReady || canResume) {
                    const isPending = canRetry
                      ? isRetryingThisDoc
                      : canPublishReady
                        ? isPublishingThisDoc
                        : isResumingThisDoc;
                    const mutationPending = canRetry
                      ? retryPending
                      : canPublishReady
                        ? publishReadyPending
                        : resumePending;
                    const onClick = canRetry
                      ? onRetryFailedBatches
                      : canPublishReady
                        ? onPublishReady
                        : onResumeProcessing;
                    return (
                      <button
                        key={action.id}
                        type="button"
                        onClick={onClick}
                        disabled={mutationPending}
                        className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-1 text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20 disabled:cursor-wait disabled:opacity-60"
                      >
                        {isPending ? t('common.states.loading') : action.label}
                      </button>
                    );
                  }

                  return null;
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {(isDocumentProcessing || showCompletedElapsed) && (
        <div className="mb-4 rounded-xl bg-[var(--accent-primary)]/10 p-3">
          {isDocumentProcessing && (
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-[var(--accent-primary)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{effectiveProgressLabel}</span>
            </div>
          )}
          {isDocumentProcessing && effectiveProgressPercent !== null && (
            <div className="mb-2 h-2 overflow-hidden rounded-full bg-[var(--surface-secondary)]">
              <div
                className="h-full rounded-full bg-[var(--accent-primary)] transition-all"
                style={{ width: `${effectiveProgressPercent}%` }}
              />
            </div>
          )}
          <div className="space-y-1 text-xs text-[var(--text-muted)]">
            {isDocumentProcessing && <div className="text-[var(--text-primary)]">{processingStatusMessage}</div>}
            <div>{t('knowledge.document.processingModelPrefix')} {processingModelLabel}</div>
            <div>{t('knowledge.document.elapsedPrefix')} {processingElapsedLabel}</div>
            {processingDetailRows.map((row) => (
              <div key={row}>{row}</div>
            ))}
            {groqRouteRows(doc, processingReport, formatNumber).map((row) => (
              <div key={row}>{row}</div>
            ))}
            {economyModeRows(doc, processingReport, formatNumber).map((row) => (
              <div key={row}>{row}</div>
            ))}
            {sourceChunkCount !== null && (
              <div>{t('knowledge.document.sourceChunksPrefix')} {formatNumber(sourceChunkCount ?? 0)}</div>
            )}
            {incomingAnswerCandidateCount !== null && (
              <div>{t('knowledge.document.incomingAnswersPrefix')} {formatNumber(incomingAnswerCandidateCount ?? 0)}</div>
            )}
            {answerResolutionCount !== null && (
              <div>
                Answer resolver calls: {formatNumber(answerResolutionCount ?? 0)}
              </div>
            )}
            {documentLlmTokenText !== null && (
              <div>{t('knowledge.document.llmTokensPrefix')} {documentLlmTokenText}</div>
            )}
            {documentLlmModels !== null && (
              <div>{t('knowledge.document.llmModelsPrefix')} {documentLlmModels}</div>
            )}
          </div>
        </div>
      )}
    </>
  );
};
