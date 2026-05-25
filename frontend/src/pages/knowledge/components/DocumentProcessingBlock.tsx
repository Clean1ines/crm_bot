import React from 'react';
import { Loader2 } from 'lucide-react';

import { type KnowledgeAnswerDraftsResponse, type KnowledgeProcessingReport, type KnowledgeSourceUnitsResponse } from '@shared/api/modules/knowledge';
import { t } from '@shared/i18n';

type DocumentLite = {
  id: string;
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
  retryPending: boolean;
  retryTarget?: string;
  publishReadyPending: boolean;
  publishReadyTarget?: string;
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
  retryPending,
  retryTarget,
  publishReadyPending,
  publishReadyTarget,
  formatNumber,
  answerResolutionStepId,
  renderDraftsSummary,
  renderSourceUnitsSummary,
  renderAnswerResolutionTracePanel,
}) => (
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
                className={`flex items-start justify-between gap-3 ${step.id === answerResolutionStepId ? 'rounded-lg bg-[var(--control-bg)] px-2 py-1' : ''}`}
              >
                <span className="font-medium text-[var(--text-primary)]">{step.label}</span>
                <span className="text-right">
                  {step.total > 0
                    ? `${formatNumber(step.current)} / ${formatNumber(step.total)}`
                    : step.status}
                </span>
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
                const isRetryingThisDoc = retryPending && retryTarget === doc.id;
                const isPublishingThisDoc = publishReadyPending && publishReadyTarget === doc.id;

                if (canRetry || canPublishReady) {
                  const isPending = canRetry ? isRetryingThisDoc : isPublishingThisDoc;
                  const mutationPending = canRetry ? retryPending : publishReadyPending;
                  return (
                    <button
                      key={action.id}
                      type="button"
                      onClick={canRetry ? onRetryFailedBatches : onPublishReady}
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
            <span>{processingProgressLabel}</span>
          </div>
        )}
        {isDocumentProcessing && processingProgressPercent !== null && (
          <div className="mb-2 h-2 overflow-hidden rounded-full bg-[var(--surface-secondary)]">
            <div
              className="h-full rounded-full bg-[var(--accent-primary)] transition-all"
              style={{ width: `${processingProgressPercent}%` }}
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
