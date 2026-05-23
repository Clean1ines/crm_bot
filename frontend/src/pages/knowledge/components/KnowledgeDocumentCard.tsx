import React from 'react';
import { FileText } from 'lucide-react';

import { type KnowledgeCommercialTruthReviewPolicy, type KnowledgeCommercialTruthReviewResponse, type KnowledgePriceFact, type KnowledgePriceFactsResponse, type KnowledgeImportQualityReport, type KnowledgeProcessingReport } from '@shared/api/modules/knowledge';

type DocCardDocument = {
  id: string;
  file_name: string;
  file_size: number;
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
  formatSize: (bytes: number) => string;
  knowledgeProcessingModeLabel: (value: string) => string;
  ImportQualitySummary: React.ComponentType<{ report?: KnowledgeImportQualityReport; isLoading: boolean }>;
  PriceFactsSummary: React.ComponentType<{
    response: KnowledgePriceFactsResponse | undefined;
    isLoading: boolean;
    onPublishFact: (fact: KnowledgePriceFact) => void;
    onRejectFact: (fact: KnowledgePriceFact) => void;
    mutatingFactId: string | null;
  }>;
  CommercialTruthReviewSummary: React.ComponentType<{
    response: KnowledgeCommercialTruthReviewResponse | undefined;
    isLoading: boolean;
    policy: KnowledgeCommercialTruthReviewPolicy;
    onPolicyChange: (policy: KnowledgeCommercialTruthReviewPolicy) => void;
  }>;
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
  formatSize,
  knowledgeProcessingModeLabel,
  ImportQualitySummary,
  PriceFactsSummary,
  CommercialTruthReviewSummary,
}) => (
  <div
    className="rounded-2xl bg-[var(--surface-elevated)] p-4 transition-all hover:shadow-lg sm:p-5 group"
  >
    <div className="mb-4 flex items-start justify-between">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-secondary)] text-[var(--accent-primary)]">
        <FileText className="h-5 w-5" />
      </div>
      {actionsNode}
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

    <ImportQualitySummary
      report={importQualityReport}
      isLoading={importQualityLoading}
    />

    <PriceFactsSummary
      response={priceFactsResponse}
      isLoading={isPriceFactsLoading}
      onPublishFact={onPublishFact}
      onRejectFact={onRejectFact}
      mutatingFactId={mutatingPriceFactId}
    />
    <CommercialTruthReviewSummary
      response={commercialTruthReviewResponse}
      isLoading={isCommercialTruthReviewLoading}
      policy={commercialTruthReviewPolicy}
      onPolicyChange={onPolicyChange}
    />

    {processingNode}
    {retightenReportNode}
    {statusNode}
  </div>
);
