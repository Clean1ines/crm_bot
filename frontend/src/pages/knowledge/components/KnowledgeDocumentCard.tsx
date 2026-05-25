import React from 'react';
import { FileText } from 'lucide-react';

import { ImportQualitySummary } from './ImportQualitySummary';
import { PriceFactsSummary } from './PriceFactsSummary';
import { CommercialTruthReviewSummary } from './CommercialTruthReviewSummary';

import { t } from '@shared/i18n';
import { type KnowledgeCommercialTruthReviewPolicy, type KnowledgeCommercialTruthReviewResponse, type KnowledgePriceFact, type KnowledgePriceFactsResponse, type KnowledgeImportQualityReport, type KnowledgeProcessingReport } from '@shared/api/modules/knowledge';

type DocCardDocument = {
  id: string;
  file_name: string;
  file_size: number;
  chunk_count: number;
  structured_entries?: number;
  structured_chunk_count?: number;
  preprocessing_mode?: string | null;
  created_at: string;
  status: string;
  error?: string | null;
};

export const KnowledgeDocumentCard: React.FC<{
  doc: DocCardDocument;
  statusBadge: { className: string; label: string };
  isRetighteningThisDoc: boolean;
  processingReport: KnowledgeProcessingReport | undefined;
  importQualityReport: KnowledgeImportQualityReport | undefined;
  priceFactsResponse: KnowledgePriceFactsResponse | undefined;
  commercialTruthReviewResponse: KnowledgeCommercialTruthReviewResponse | undefined;
  isPriceFactsLoading: boolean;
  isCommercialTruthReviewLoading: boolean;
  mutatingPriceFactId: string | null;
  importQualityLoading: boolean;
  commercialTruthReviewPolicy: KnowledgeCommercialTruthReviewPolicy;
  onPolicyChange: (policy: KnowledgeCommercialTruthReviewPolicy) => void;
  onPublishFact: (fact: KnowledgePriceFact) => void;
  onRejectFact: (fact: KnowledgePriceFact) => void;
  actionsNode: React.ReactNode;
  processingNode: React.ReactNode;
  retightenReportNode: React.ReactNode;
  statusNode: React.ReactNode;
  hasDrafts: boolean;
  draftCount?: number;
  hasSourceUnits: boolean;
  isDocumentProcessing: boolean;
  onOpenDrafts: () => void;
  onOpenSourceUnits: () => void;
  onOpenCuration: () => void;
  onStopProcessing: () => void;
  formatSize: (bytes: number) => string;
  knowledgeProcessingModeLabel: (value: string) => string;
}> = ({
  doc,
  importQualityReport,
  importQualityLoading,
  priceFactsResponse,
  isPriceFactsLoading,
  onPublishFact,
  onRejectFact,
  mutatingPriceFactId,
  commercialTruthReviewResponse,
  isCommercialTruthReviewLoading,
  commercialTruthReviewPolicy,
  onPolicyChange,
  actionsNode,
  processingNode,
  retightenReportNode,
  statusNode,
  hasDrafts,
  draftCount,
  hasSourceUnits,
  isDocumentProcessing,
  onOpenDrafts,
  onOpenSourceUnits,
  onOpenCuration,
  onStopProcessing,
  formatSize,
  knowledgeProcessingModeLabel,
}) => (
  <div
    id={`knowledge-doc-card-${doc.id}`}
    className="rounded-2xl bg-[var(--surface-elevated)] p-4 transition-all hover:shadow-lg sm:p-5 group"
  >
    <div className="mb-4 flex items-start justify-between gap-2">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-secondary)] text-[var(--accent-primary)]">
        <FileText className="h-5 w-5" />
      </div>
      <div className="flex items-center gap-2">
        {isDocumentProcessing ? (
          <button
            type="button"
            onClick={onStopProcessing}
            className="rounded-full bg-[var(--accent-danger-bg)] px-2.5 py-1 text-[10px] font-medium text-[var(--accent-danger-text)] transition-colors hover:opacity-80"
          >
            {t('knowledge.documentCard.primaryAction.stop')}
          </button>
        ) : hasDrafts ? (
          <button
            type="button"
            onClick={onOpenDrafts}
            className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-[10px] font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20"
          >
            {t('knowledge.documentCard.primaryAction.openDrafts')}
          </button>
        ) : hasSourceUnits ? (
          <button
            type="button"
            onClick={onOpenSourceUnits}
            className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-[10px] font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20"
          >
            {t('knowledge.documentCard.primaryAction.openSources')}
          </button>
        ) : (
          <span className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-[10px] font-medium text-[var(--text-muted)]">{t('knowledge.documentCard.primaryAction.details')}</span>
        )}
        <button
          type="button"
          onClick={onOpenCuration}
          className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-[10px] font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20"
        >
          {t('knowledge.documentCard.primaryAction.curation')}
        </button>
      </div>
    </div>

    <h4 className="mb-1 truncate font-semibold text-[var(--text-primary)]" title={doc.file_name}>
      {doc.file_name}
    </h4>
    <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
      <span>{formatSize(doc.file_size)}</span>
      {doc.preprocessing_mode && (
        <>
          <span className="h-1 w-1 rounded-full bg-[var(--border-subtle)]" />
          <span>{knowledgeProcessingModeLabel(doc.preprocessing_mode)}</span>
        </>
      )}
    </div>

    <div className="mb-4 flex flex-wrap gap-1.5 text-[10px]">
      {typeof doc.structured_entries === 'number' && (
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-muted)]">
          {t('knowledge.documentCard.counters.runtimeEntries')}: {doc.structured_entries}
        </span>
      )}
      {typeof draftCount === 'number' && draftCount > 0 && (
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-muted)]">
          {t('knowledge.documentCard.counters.drafts')}: {draftCount}
        </span>
      )}
      {priceFactsResponse && priceFactsResponse.facts.length > 0 && (
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-muted)]">
          {t('knowledge.documentCard.counters.priceFacts')}: {priceFactsResponse.facts.length}
        </span>
      )}
      {commercialTruthReviewResponse && commercialTruthReviewResponse.unresolved_conflict_count > 0 && (
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-muted)]">
          {t('knowledge.documentCard.counters.commercialConflicts')}: {commercialTruthReviewResponse.unresolved_conflict_count}
        </span>
      )}
    </div>

    {statusNode}

    <div className="mt-4 space-y-3">
      {actionsNode}
      <ImportQualitySummary report={importQualityReport} isLoading={importQualityLoading} />
      <PriceFactsSummary response={priceFactsResponse} isLoading={isPriceFactsLoading} onPublishFact={onPublishFact} onRejectFact={onRejectFact} mutatingFactId={mutatingPriceFactId} />
      <CommercialTruthReviewSummary response={commercialTruthReviewResponse} isLoading={isCommercialTruthReviewLoading} policy={commercialTruthReviewPolicy} onPolicyChange={onPolicyChange} />
      {processingNode}
      {retightenReportNode}
    </div>
  </div>
);
