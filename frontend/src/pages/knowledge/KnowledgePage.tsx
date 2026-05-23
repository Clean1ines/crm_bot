import React, { useEffect, useState } from 'react';
import {
  BookOpen,
  Upload,
  Search,
  TestTube2,
  Loader2,
} from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';
import { getErrorMessage } from '@shared/api/core/errors';
import { knowledgeDocumentStatusLabel } from '@shared/lib/uiLabels';

import {
  KNOWLEDGE_PREPROCESSING_MODE_OPTIONS,
  knowledgeApi,
  type KnowledgePreprocessingMode,
  type KnowledgeUsageBreakdown,
  type KnowledgeUsageResponse,
  type KnowledgePreviewResponse,
  type KnowledgePreviewResult,
  type KnowledgeProcessingReport,
  type KnowledgeImportQualityReport,
  type KnowledgeAnswerDraftsResponse,
  type KnowledgeSourceUnitsResponse,
  type KnowledgePriceFact,
  type KnowledgePriceFactsResponse,
  type KnowledgeCommercialTruthReviewResponse,
  type KnowledgeCommercialTruthReviewPolicy,
} from '@shared/api/modules/knowledge';
import { BaseModal } from '@shared/ui';
import { t } from '@shared/i18n';
import { CommercialTruthReviewSummary } from './components/CommercialTruthReviewSummary';
import { DraftsSummary } from './components/DraftsSummary';
import { DraftsModal } from './components/DraftsModal';
import { SourceUnitsSummary } from './components/SourceUnitsSummary';
import { SourceUnitsModal } from './components/SourceUnitsModal';
import { DocumentStatusBlock } from './components/DocumentStatusBlock';
import { KnowledgeDocumentCard } from './components/KnowledgeDocumentCard';
import { DocumentProcessingBlock } from './components/DocumentProcessingBlock';
import { DocumentActionsBlock } from './components/DocumentActionsBlock';

type KnowledgeProcessingMetrics = Record<string, unknown>;

type KnowledgeProcessingReportByDocument = Record<string, KnowledgeProcessingReport>;
type KnowledgeImportQualityByDocument = Record<string, KnowledgeImportQualityReport>;
type KnowledgeAnswerDraftsByDocument = Record<string, KnowledgeAnswerDraftsResponse>;
type KnowledgeSourceUnitsByDocument = Record<string, KnowledgeSourceUnitsResponse>;
type KnowledgePriceFactsByDocument = Record<string, KnowledgePriceFactsResponse>;
type KnowledgeCommercialTruthReviewsByDocument = Record<string, KnowledgeCommercialTruthReviewResponse>;

type PriceFactActionVariables = {
  documentId: string;
  factId: string;
  reason?: string;
};


interface Document {
  id: string;
  file_name: string;
  file_size: number;
  status: 'pending' | 'processing' | 'processed' | 'error' | 'cancelled' | string;
  error?: string | null;
  chunk_count: number;
  created_at: string;
  updated_at?: string | null;
  preprocessing_mode?: KnowledgePreprocessingMode | string | null;
  preprocessing_status?: 'not_requested' | 'processing' | 'completed' | 'failed' | 'cancelled' | string | null;
  preprocessing_error?: string | null;
  preprocessing_model?: string | null;
  preprocessing_prompt_version?: string | null;
  preprocessing_metrics?: KnowledgeProcessingMetrics | null;
  structured_entries?: number;
  structured_chunk_count?: number;
  llm_tokens_input?: number;
  llm_tokens_output?: number;
  llm_tokens_total?: number;
  llm_usage_events_count?: number;
  llm_models?: string | null;
}

interface UsageSummaryCardProps {
  usage: KnowledgeUsageResponse;
}

const formatSize = (bytes: number) => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
};

const confidenceLabel = (score: number): string => {
  if (score >= 0.75) return t('knowledge.confidence.high');
  if (score >= 0.45) return t('knowledge.confidence.medium');
  return t('knowledge.confidence.low');
};


const previewTraceLabel = (value: string): string => {
  const labels: Record<string, string> = {
    title: t('knowledge.preview.trace.field.title'),
    questions: t('knowledge.preview.trace.field.questions'),
    synonyms: t('knowledge.preview.trace.field.synonyms'),
    tags: t('knowledge.preview.trace.field.tags'),
    answer: t('knowledge.preview.trace.field.answer'),
    search_text: t('knowledge.preview.trace.field.searchText'),
    embedding_text: t('knowledge.preview.trace.field.embeddingText'),
    exact: t('knowledge.preview.trace.field.exact'),
    embedding: t('knowledge.preview.trace.field.embedding'),
  };

  return labels[value] || value;
};

const formatPreviewScore = (value: number): string => (
  Number.isFinite(value) ? value.toFixed(3) : '0.000'
);


const DRAFT_FETCH_LIMIT = 1000;
const SOURCE_UNIT_FETCH_LIMIT = 1000;





const STOPPED_BY_USER_ISSUE_NEEDLE = '\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u043c';

const formatNumber = (value: number): string => new Intl.NumberFormat('ru-RU').format(value);

const formatUsd = (value: number): string => new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
}).format(value);

const LLM_USAGE_TYPE = 'llm';

const USER_ANSWER_USAGE_SOURCES = new Set([
  'client_response',
  'user_response',
  'agent_response',
  'conversation_answer',
]);

const KNOWLEDGE_UPLOAD_USAGE_SOURCES = new Set([
  'knowledge_preprocessing',
  'knowledge_upload',
]);

const RAG_EVAL_USAGE_SOURCES = new Set([
  'rag_eval',
  'rag_eval_dataset',
  'rag_eval_judge',
  'rag_search',
]);

const llmUsageBreakdown = (
  breakdown: KnowledgeUsageBreakdown[],
): KnowledgeUsageBreakdown[] => (
  breakdown.filter((item) => item.usage_type === LLM_USAGE_TYPE)
);

const usageBySources = (
  breakdown: KnowledgeUsageBreakdown[],
  sources: Set<string>,
): KnowledgeUsageBreakdown[] => (
  breakdown.filter((item) => sources.has(item.source))
);

const sumUsageTokens = (breakdown: KnowledgeUsageBreakdown[]): number => (
  breakdown.reduce((acc, item) => acc + item.tokens_total, 0)
);

const sumUsageCost = (breakdown: KnowledgeUsageBreakdown[]): number => (
  breakdown.reduce((acc, item) => acc + item.estimated_cost_usd, 0)
);

const usageModelRows = (breakdown: KnowledgeUsageBreakdown[]): string[] => {
  const events = breakdown.reduce((acc, item) => acc + item.events_count, 0);
  return events > 0 ? [t('knowledge.metrics.operations', { count: formatNumber(events) })] : [];
};





const shouldFetchPriceFactsForDocument = (
  doc: Document,
  report: KnowledgeProcessingReport | undefined,
): boolean => {
  if (doc.preprocessing_mode === 'price_list') return true;

  const candidateCount = report
    ? metricNumber(report.metrics, 'price_acquisition_fact_candidate_count')
    : null;
  const reviewFactCount = report
    ? metricNumber(report.metrics, 'price_review_fact_count')
    : null;

  return (candidateCount ?? 0) > 0 || (reviewFactCount ?? 0) > 0;
};

const metricNumber = (
  metrics: KnowledgeProcessingMetrics | null | undefined,
  key: string,
): number | null => {
  const value = metrics?.[key];
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const isLikelyEmbeddingModel = (model: string): boolean => {
  const normalized = model.toLowerCase();

  return (
    normalized.includes('embedding')
    || normalized.includes('voyage')
    || normalized.includes('jina')
    || normalized.includes('minilm')
    || normalized.includes('e5')
    || normalized.includes('bge')
  );
};

const processingModelLabel = (doc: Document): string => {
  const candidates = [
    metricText(doc.preprocessing_metrics, 'model'),
    doc.preprocessing_model,
  ].filter((value): value is string => Boolean(value && value.trim()));

  return candidates.find((model) => !isLikelyEmbeddingModel(model))
    || t('knowledge.processing.modelPending');
};

const metricText = (
  metrics: KnowledgeProcessingMetrics | null | undefined,
  key: string,
): string | null => {
  const value = metrics?.[key];
  return typeof value === 'string' && value.trim() !== '' ? value : null;
};

const rawDocumentIssueText = (doc: Document): string | null => {
  const message = doc.preprocessing_error?.trim() || doc.error?.trim() || '';

  return message || null;
};

const documentIssueText = (doc: Document): string | null => {
  const message = rawDocumentIssueText(doc);
  if (!message) return null;

  return getErrorMessage(
    message,
    t('knowledge.document.failureAdvice'),
  );
};

const isDocumentCancelled = (doc: Document): boolean => {
  const issueText = rawDocumentIssueText(doc)?.toLowerCase() || '';

  return (
    doc.status === 'cancelled'
    || doc.preprocessing_status === 'cancelled'
    || issueText.includes(STOPPED_BY_USER_ISSUE_NEEDLE)
    || issueText.includes('cancelled')
    || issueText.includes('canceled')
  );
};

const isDocumentFailed = (doc: Document): boolean => (
  doc.status === 'error'
  || doc.preprocessing_status === 'failed'
);

const isDocumentProcessing = (doc: Document): boolean => (
  !isDocumentCancelled(doc)
  && !isDocumentFailed(doc)
  && (
    doc.status === 'pending'
    || doc.status === 'processing'
    || doc.preprocessing_status === 'processing'
  )
);

const isDocumentRetightenable = (doc: Document): boolean => (
  doc.status === 'processed'
  && !isDocumentProcessing(doc)
  && !isDocumentFailed(doc)
  && !isDocumentCancelled(doc)
);

const knowledgeProcessingModeLabel = (mode: string | null | undefined): string => (
  KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.find((option) => option.value === mode)?.label
  || mode
  || t('knowledge.common.unspecified')
);

const processingProgressPercent = (doc: Document): number | null => {
  const current = metricNumber(doc.preprocessing_metrics, 'technical_chunk_processed_count')
    ?? metricNumber(doc.preprocessing_metrics, 'technical_compiler_call_count');
  const total = metricNumber(doc.preprocessing_metrics, 'technical_chunk_total_count')
    ?? metricNumber(doc.preprocessing_metrics, 'technical_compiler_total_count');

  if (current === null || total === null || total <= 0) return null;

  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
};

const processingProgressLabel = (doc: Document): string => {
  const metrics = doc.preprocessing_metrics;
  const current = metricNumber(metrics, 'technical_chunk_processed_count')
    ?? metricNumber(metrics, 'technical_compiler_call_count');
  const total = metricNumber(metrics, 'technical_chunk_total_count')
    ?? metricNumber(metrics, 'technical_compiler_total_count');

  if (current !== null && total !== null && total > 0) {
    return t('knowledge.progress.stepOf', { current: formatNumber(current), total: formatNumber(total) });
  }

  if (doc.status === 'pending') return t('knowledge.document.pendingProcessing');
  return t('knowledge.document.preparingProcessing');
};

const answerResolutionCount = (doc: Document): number | null => (
  metricNumber(doc.preprocessing_metrics, 'answer_resolution_call_count')
);


const metricObject = (
  metrics: KnowledgeProcessingMetrics | null | undefined,
  key: string,
): KnowledgeProcessingMetrics | null => {
  const value = metrics?.[key];
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as KnowledgeProcessingMetrics
    : null;
};

const retightenMetrics = (doc: Document): KnowledgeProcessingMetrics | null => (
  metricObject(doc.preprocessing_metrics, 'answer_resolution')
);

const retightenStatusText = (metrics: KnowledgeProcessingMetrics): string | null => {
  const status = metricText(metrics, 'status');
  const reason = metricText(metrics, 'reason');

  if (!status && !reason) return null;
  if (status && reason) return `${status}: ${reason}`;
  return status || reason;
};

const metricObjectArray = (
  metrics: KnowledgeProcessingMetrics | null | undefined,
  key: string,
): KnowledgeProcessingMetrics[] => {
  const value = metrics?.[key];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is KnowledgeProcessingMetrics => (
    item !== null && typeof item === 'object' && !Array.isArray(item)
  ));
};


const retightenReportRows = (doc: Document): string[] => {
  const metrics = retightenMetrics(doc);
  if (!metrics) return [];

  const rows: string[] = [];
  const statusText = retightenStatusText(metrics);
  const before = metricNumber(metrics, 'entry_count_before');
  const after = metricNumber(metrics, 'entry_count_after');
  const groups = metricNumber(metrics, 'candidate_case_count');
  const decisions = metricNumber(metrics, 'decision_count');
  const resolvedAnswers = metricNumber(metrics, 'resolved_answer_count');
  const rejectedNoisyResolutions = metricNumber(metrics, 'rejected_noisy_resolved_answer_count');
  const combinedEntries = metricNumber(metrics, 'collapsed_entry_count');
  const llmCalls = metricNumber(metrics, 'llm_call_count');
  const cleanupOriginalUnits = metricNumber(metrics, 'retighten_cleanup_original_unit_count');
  const cleanupRemovedUnits = metricNumber(metrics, 'retighten_cleanup_removed_unit_count');
  const deterministicCombined = metricNumber(metrics, 'deterministic_collapsed_entry_count');
  const deterministicExactAnswer = metricNumber(metrics, 'deterministic_exact_answer_merge_count');
  const deterministicContainment = metricNumber(metrics, 'deterministic_answer_containment_merge_count');
  const dedupedQuestions = metricNumber(metrics, 'deduped_question_variant_count');
  const suspiciousMeta = metricNumber(metrics, 'suspicious_meta_entry_count');
  const answerResolutionCombined = metricNumber(metrics, 'llm_resolved_entry_count');

  if (statusText) {
    rows.push(t('knowledge.retightenReport.status', { status: statusText }));
  }
  if (before !== null && after !== null) {
    rows.push(t('knowledge.retightenReport.entries', {
      before: formatNumber(before),
      after: formatNumber(after),
    }));
  }
  if (combinedEntries !== null) {
    rows.push(t('knowledge.retightenReport.combinedEntries', { count: formatNumber(combinedEntries) }));
  }
  if (deterministicCombined !== null) {
    rows.push(t('knowledge.retightenReport.deterministicCombined', { count: formatNumber(deterministicCombined) }));
  }
  if (deterministicExactAnswer !== null) {
    rows.push(t('knowledge.retightenReport.deterministicExactAnswer', { count: formatNumber(deterministicExactAnswer) }));
  }
  if (deterministicContainment !== null) {
    rows.push(t('knowledge.retightenReport.deterministicContainment', { count: formatNumber(deterministicContainment) }));
  }
  if (answerResolutionCombined !== null) {
    rows.push(t('knowledge.retightenReport.answerResolutionCombined', { count: formatNumber(answerResolutionCombined) }));
  }
  if (dedupedQuestions !== null) {
    rows.push(t('knowledge.retightenReport.dedupedQuestions', { count: formatNumber(dedupedQuestions) }));
  }
  if (suspiciousMeta !== null) {
    rows.push(t('knowledge.retightenReport.suspiciousMeta', { count: formatNumber(suspiciousMeta) }));
  }
  if (groups !== null) {
    rows.push(t('knowledge.retightenReport.groups', { count: formatNumber(groups) }));
  }
  if (decisions !== null) {
    rows.push(t('knowledge.retightenReport.decisions', { count: formatNumber(decisions) }));
  }
  if (resolvedAnswers !== null) {
    rows.push(t('knowledge.retightenReport.resolvedAnswers', { count: formatNumber(resolvedAnswers) }));
  }
  if (rejectedNoisyResolutions !== null) {
    rows.push(t('knowledge.retightenReport.rejectedNoisyResolutions', {
      count: formatNumber(rejectedNoisyResolutions),
    }));
  }
  if (llmCalls !== null) {
    rows.push(t('knowledge.retightenReport.llmCalls', { count: formatNumber(llmCalls) }));
  }
  if (cleanupOriginalUnits !== null) {
    rows.push(t('knowledge.retightenReport.cleanupOriginalUnits', {
      count: formatNumber(cleanupOriginalUnits),
    }));
  }
  if (cleanupRemovedUnits !== null) {
    rows.push(t('knowledge.retightenReport.cleanupRemovedUnits', {
      count: formatNumber(cleanupRemovedUnits),
    }));
  }

  return rows;
};

const ANSWER_RESOLUTION_STEP_ID = 'answer_resolution';

const positiveMetric = (value: number | null): number | null => (
  value !== null && value > 0 ? value : null
);

const sourceChunkCount = (doc: Document): number | null => (
  positiveMetric(metricNumber(doc.preprocessing_metrics, 'raw_source_chunk_count'))
  ?? positiveMetric(metricNumber(doc.preprocessing_metrics, 'source_chunk_count'))
  ?? (Number.isFinite(doc.chunk_count) && doc.chunk_count > 0 ? doc.chunk_count : null)
);

const incomingAnswerCandidateCount = (doc: Document): number | null => (
  metricNumber(doc.preprocessing_metrics, 'incoming_entry_count')
  ?? metricNumber(doc.preprocessing_metrics, 'answer_candidate_count')
);


const processingDetailRows = (doc: Document): string[] => {
  const metrics = doc.preprocessing_metrics;
  const rows: string[] = [];
  const totalParts = metricNumber(metrics, 'technical_chunk_total_count')
    ?? metricNumber(metrics, 'technical_compiler_total_count');
  const completedParts = metricNumber(metrics, 'technical_chunk_processed_count')
    ?? metricNumber(metrics, 'technical_compiler_call_count');
  const failedParts = metricNumber(metrics, 'failed_part_count');
  const rawDrafts = metricNumber(metrics, 'raw_draft_count')
    ?? metricNumber(metrics, 'draft_answer_count');
  const safelyCombined = metricNumber(metrics, 'duplicates_collapsed_safely_count')
    ?? metricNumber(metricObject(metrics, 'deterministic_cleanup'), 'exact_duplicate_candidate_collapse_count');
  const answerResolution = metricObject(metrics, 'answer_resolution');
  const resolutionPasses = answerResolution ? 1 : metricNumber(metrics, 'answer_resolution_pass_count');
  const answerResolutionCases = metricNumber(answerResolution, 'candidate_case_count');
  const appliedAnswerResolutions = metricNumber(answerResolution, 'resolved_answer_count');
  const keptSeparate = metricNumber(answerResolution, 'kept_separate_count');
  const invalidResolverOutputs = metricNumber(answerResolution, 'invalid_resolution_output_count');
  const publishedEntries = metricNumber(metrics, 'canonical_entry_count')
    ?? metricNumber(metrics, 'published_entry_count');

  if (totalParts !== null) rows.push(t('knowledge.document.technicalPartsTotal', { total: formatNumber(totalParts) }));
  if (completedParts !== null && totalParts !== null) {
    rows.push(t('knowledge.document.extractedPartsProgress', { current: formatNumber(completedParts), total: formatNumber(totalParts) }));
  }
  if (failedParts !== null) rows.push(t('knowledge.document.failedParts', { count: formatNumber(failedParts) }));
  if (rawDrafts !== null) rows.push(t('knowledge.document.rawDraftsSaved', { count: formatNumber(rawDrafts) }));
  if (safelyCombined !== null) rows.push(t('knowledge.document.duplicateAnswersCombinedSafely', { count: formatNumber(safelyCombined) }));
  if (resolutionPasses !== null) rows.push(t('knowledge.document.answerResolutionPasses', { count: formatNumber(resolutionPasses) }));
  if (answerResolutionCases !== null) rows.push(t('knowledge.document.answerResolverCases', { count: formatNumber(answerResolutionCases) }));
  if (appliedAnswerResolutions !== null) rows.push(t('knowledge.document.answerResolutionsApplied', { count: formatNumber(appliedAnswerResolutions) }));
  if (keptSeparate !== null) rows.push(t('knowledge.document.keptSeparateByResolver', { count: formatNumber(keptSeparate) }));
  if (invalidResolverOutputs !== null) rows.push(t('knowledge.document.rejectedInvalidResolverOutputs', { count: formatNumber(invalidResolverOutputs) }));
  if (publishedEntries !== null) rows.push(t('knowledge.document.publishedEntries', { count: formatNumber(publishedEntries) }));

  return rows;
};

const processingStatusMessage = (doc: Document): string => {
  const message = metricText(doc.preprocessing_metrics, 'status_message');
  if (message) return message;
  if (isDocumentProcessing(doc)) return t('knowledge.document.draftStatus.processing');
  if (doc.status === 'error') return t('knowledge.document.draftStatus.error');
  return t('knowledge.document.draftStatus.ready');
};

const documentLlmTokenText = (doc: Document): string | null => {
  const total = doc.llm_tokens_total
    ?? metricNumber(doc.preprocessing_metrics, 'llm_tokens_total');
  if (total === null || total <= 0) return null;

  return t('knowledge.progress.processingUnits', { total: formatNumber(total) });
};

const documentLlmModels = (doc: Document): string | null => {
  const models = doc.llm_models?.trim();
  return models || null;
};

const formatDurationSeconds = (seconds: number): string => {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const restSeconds = safeSeconds % 60;

  if (hours > 0) {
    return t('knowledge.duration.hoursMinutesSeconds', { hours, minutes: minutes.toString().padStart(2, '0'), seconds: restSeconds.toString().padStart(2, '0') });
  }
  if (minutes > 0) {
    return t('knowledge.duration.minutesSeconds', { minutes, seconds: restSeconds.toString().padStart(2, '0') });
  }
  return t('knowledge.duration.seconds', { seconds: restSeconds });
};

const processingElapsedSeconds = (doc: Document, nowMs: number): number => {
  const metricElapsed = metricNumber(doc.preprocessing_metrics, 'elapsed_seconds') ?? 0;
  const startedAt = Date.parse(doc.created_at || doc.updated_at || '');

  if (!Number.isFinite(startedAt) || !isDocumentProcessing(doc)) {
    return metricElapsed;
  }

  const localElapsed = Math.max(0, (nowMs - startedAt) / 1000);
  return Math.max(metricElapsed, localElapsed);
};

const PreviewResultCard: React.FC<{
  title: string;
  result: KnowledgePreviewResult;
  compact?: boolean;
}> = ({ title, result, compact = false }) => (
  <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
    <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
      <span className="inline-flex w-fit items-center rounded-full bg-[var(--accent-muted)] px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)]">
        {confidenceLabel(result.score)}
      </span>
    </div>
    <p className={`text-sm leading-relaxed text-[var(--text-primary)] ${compact ? 'line-clamp-3' : ''}`}>
      {result.answer || result.content}
    </p>
    <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-muted)]">
      <span>{t('knowledge.preview.matchFound')}</span>
      {result.source && <span>{t('knowledge.preview.sourcePrefix')} {result.source}</span>}
      {result.document_status && <span>{t('knowledge.preview.documentPrefix')} {knowledgeDocumentStatusLabel(result.document_status)}</span>}
      {result.entry_kind && <span>entry: {result.entry_kind}</span>}
      {result.trace && (
        <span>
          {t('knowledge.preview.trace.summary', {
            fields: result.trace.matched_fields.map(previewTraceLabel).join(', ') || t('knowledge.preview.trace.none'),
            lexical: formatPreviewScore(result.trace.lexical_score),
            vector: formatPreviewScore(result.trace.vector_score),
            final: formatPreviewScore(result.trace.final_score),
            field: previewTraceLabel(result.trace.displayed_field),
          })}
          {' · '}{result.trace.is_production_safe
            ? t('knowledge.preview.trace.productionSafe')
            : t('knowledge.preview.trace.notProductionSafe')}
          {result.trace.title_match ? ` · ${t('knowledge.preview.trace.titleMatch')}` : ''}
          {result.trace.exact_question_match ? ` · ${t('knowledge.preview.trace.questionMatch')}` : ''}
          {result.trace.length_penalty > 0
            ? ` · ${t('knowledge.preview.trace.penalty', { penalty: formatPreviewScore(result.trace.length_penalty) })}`
            : ''}
        </span>
      )}
    </div>
  </div>
);

const UsageScenarioCard: React.FC<{
  title: string;
  description: string;
  breakdown: KnowledgeUsageBreakdown[];
  emptyText: string;
}> = ({ title, description, breakdown, emptyText }) => {
  const tokens = sumUsageTokens(breakdown);
  const modelRows = usageModelRows(breakdown);

  return (
    <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {title}
      </div>
      <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
        {formatNumber(tokens)}
      </div>
      <p className="mt-1 text-xs leading-relaxed text-[var(--text-muted)]">
        {description}
      </p>
      <div className="mt-3 space-y-1 text-xs text-[var(--text-muted)]">
        {modelRows.length > 0 ? (
          modelRows.map((row) => (
            <div key={row}>{row}</div>
          ))
        ) : (
          <div>{emptyText}</div>
        )}
      </div>
    </div>
  );
};














const answerResolutionTraceRows = (
  report: KnowledgeProcessingReport | undefined,
): KnowledgeProcessingMetrics[] => {
  const answerResolutionMetrics = metricObject(report?.metrics, 'answer_resolution');
  return metricObjectArray(answerResolutionMetrics, 'decision_trace');
};

const AnswerResolutionTracePanel: React.FC<{
  report: KnowledgeProcessingReport;
}> = ({ report }) => {
  const traceRows = answerResolutionTraceRows(report);
  if (traceRows.length === 0) return null;

  return (
    <div className="mt-3 border-t border-[var(--border-subtle)] pt-2 text-xs">
      <div className="mb-2 font-medium text-[var(--text-primary)]">
        {t('knowledge.answerResolutionTrace.title', { count: formatNumber(traceRows.length) })}
      </div>
      <div className="max-h-52 space-y-2 overflow-y-auto pr-1">
        {traceRows.map((row, index) => {
          const caseId = metricText(row, 'case_id') || `case-${index + 1}`;
          const action = metricText(row, 'action') || 'unknown';
          const questionIntent = metricText(row, 'question_intent') || caseId;
          const canonicalAnswerPreview = metricText(row, 'canonical_answer_preview');
          const candidates = Array.isArray(row.candidates)
            ? row.candidates.filter((item): item is KnowledgeProcessingMetrics => (
              item !== null && typeof item === 'object' && !Array.isArray(item)
            ))
            : [];

          return (
            <details key={`${caseId}-${index}`} className="rounded-lg bg-[var(--control-bg)] p-2">
              <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                {action} · {questionIntent}
              </summary>
              <div className="mt-2 space-y-2 text-[var(--text-muted)]">
                <div>case_id: {caseId}</div>
                {canonicalAnswerPreview && (
                  <div className="whitespace-pre-wrap">
                    {t('knowledge.answerResolutionTrace.finalAnswer', { answer: canonicalAnswerPreview })}
                  </div>
                )}
                {candidates.length > 0 && (
                  <div>
                    <div className="mb-1 font-medium text-[var(--text-primary)]">{t('knowledge.answerResolutionTrace.compressed')}</div>
                    <ul className="list-disc space-y-1 pl-5">
                      {candidates.map((candidate, candidateIndex) => {
                        const title = metricText(candidate, 'title') || metricText(candidate, 'candidate_id') || `candidate-${candidateIndex + 1}`;
                        const preview = metricText(candidate, 'answer_preview');
                        return (
                          <li key={`${caseId}-${candidateIndex}`}>
                            <span className="text-[var(--text-primary)]">{title}</span>
                            {preview ? <span> — {preview}</span> : null}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </div>
            </details>
          );
        })}
      </div>
    </div>
  );
};


const UsageSummaryCard: React.FC<UsageSummaryCardProps> = ({ usage }) => {
  const llmBreakdown = llmUsageBreakdown(usage.breakdown);
  const answerBreakdown = usageBySources(llmBreakdown, USER_ANSWER_USAGE_SOURCES);
  const uploadBreakdown = usageBySources(llmBreakdown, KNOWLEDGE_UPLOAD_USAGE_SOURCES);
  const ragEvalBreakdown = usageBySources(llmBreakdown, RAG_EVAL_USAGE_SOURCES);
  const totalTokens = sumUsageTokens(llmBreakdown);
  const totalCost = sumUsageCost(llmBreakdown);

  return (
    <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5 lg:p-6">
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
          <BookOpen className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {t('knowledge.usage.title')}
          </h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            {t('knowledge.usage.description')}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <UsageScenarioCard
          title={t('knowledge.usage.totalTitle')}
          description={t('knowledge.usage.totalDescription', { cost: formatUsd(totalCost) })}
          breakdown={llmBreakdown}
          emptyText={t('knowledge.usage.totalEmpty')}
        />
        <UsageScenarioCard
          title={t('knowledge.usage.clientAnswersTitle')}
          description={t('knowledge.usage.clientAnswersDescription')}
          breakdown={answerBreakdown}
          emptyText={t('knowledge.usage.clientAnswersEmpty')}
        />
        <UsageScenarioCard
          title={t('knowledge.usage.knowledgeProcessingTitle')}
          description={t('knowledge.usage.knowledgeProcessingDescription')}
          breakdown={uploadBreakdown}
          emptyText={t('knowledge.usage.knowledgeProcessingEmpty')}
        />
        <UsageScenarioCard
          title={t('knowledge.usage.qualityChecksTitle')}
          description={t('knowledge.usage.qualityChecksDescription')}
          breakdown={ragEvalBreakdown}
          emptyText={t('knowledge.usage.qualityChecksEmpty')}
        />
      </div>

      <div className="mt-4 text-sm text-[var(--text-muted)]">
        {t('knowledge.usage.monthlyVolume', { total: formatNumber(totalTokens) })}
      </div>
    </section>
  );
};

export const KnowledgePage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [previewQuestion, setPreviewQuestion] = useState('');
  const [preprocessingMode, setPreprocessingMode] = useState<KnowledgePreprocessingMode>('faq');
  const [isClearModalOpen, setIsClearModalOpen] = useState(false);
  const [draftsDocumentId, setDraftsDocumentId] = useState<string | null>(null);
  const [sourceUnitsDocumentId, setSourceUnitsDocumentId] = useState<string | null>(null);
  const [draftFiltersByDocument, setDraftFiltersByDocument] = useState<Record<string, string>>({});
  const [sourceUnitFiltersByDocument, setSourceUnitFiltersByDocument] = useState<Record<string, string>>({});
  const [expandedDraftIdsByDocument, setExpandedDraftIdsByDocument] = useState<Record<string, string[]>>({});
  const [expandedSourceUnitIdsByDocument, setExpandedSourceUnitIdsByDocument] = useState<Record<string, string[]>>({});

  const documentsQuery = useQuery({
    queryKey: ['knowledge-documents', projectId],
    queryFn: async () => {
      if (!projectId) return [];
      const { data } = await knowledgeApi.list(projectId);

      const payload = data && typeof data === 'object' ? data as Record<string, unknown> : {};
      const list = Array.isArray(payload.documents)
        ? payload.documents
        : Array.isArray(payload.items)
          ? payload.items
          : [];

      return list as Document[];
    },
    enabled: !!projectId,
    refetchInterval: (query) => {
      const docs = Array.isArray(query.state.data) ? query.state.data as Document[] : [];
      return docs.some(isDocumentProcessing) ? 3000 : false;
    },
  });

  const documents = Array.isArray(documentsQuery.data) ? documentsQuery.data : [];
  const hasProcessingDocuments = documents.some(isDocumentProcessing);
  const reportableDocuments = documents.filter((doc) => (
    isDocumentProcessing(doc) || isDocumentFailed(doc) || isDocumentCancelled(doc) || Boolean(doc.structured_entries)
  ));
  const reportableDocumentIds = reportableDocuments.map((doc) => doc.id).sort();
  const processingReportsQuery = useQuery({
    queryKey: ['knowledge-processing-reports', projectId, reportableDocumentIds.join(',')],
    queryFn: async () => {
      if (!projectId || reportableDocumentIds.length === 0) return {};

      const reports = await Promise.all(
        reportableDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.progress(projectId, documentId);
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return reports.reduce<KnowledgeProcessingReportByDocument>((acc, item) => {
        if (item !== null) {
          acc[item[0]] = item[1];
        }
        return acc;
      }, {});
    },
    enabled: !!projectId && reportableDocumentIds.length > 0,
    retry: false,
    refetchInterval: hasProcessingDocuments ? 3000 : false,
  });
  const processingReports = processingReportsQuery.data || {};
  const importQualityDocumentIds = documents.map((doc) => doc.id).sort();
  const importQualityReportsQuery = useQuery({
    queryKey: ['knowledge-import-quality-reports', projectId, importQualityDocumentIds.join(',')],
    queryFn: async () => {
      if (!projectId || importQualityDocumentIds.length === 0) return {};

      const reports = await Promise.all(
        importQualityDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.importQuality(projectId, documentId);
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return reports.reduce<KnowledgeImportQualityByDocument>((acc, item) => {
        if (item !== null) {
          acc[item[0]] = item[1];
        }
        return acc;
      }, {});
    },
    enabled: !!projectId && importQualityDocumentIds.length > 0,
    retry: false,
    refetchInterval: hasProcessingDocuments ? 3000 : false,
  });
  const importQualityReports = importQualityReportsQuery.data || {};
  const draftPreviewDocumentIds = Object.values(processingReports)
    .filter((report) => {
      const document = documents.find((doc) => doc.id === report.document_id);
      const draftCount = metricNumber(report.metrics, 'raw_draft_count')
        ?? metricNumber(report.metrics, 'draft_answer_count')
        ?? 0;
      const publishedCount = metricNumber(report.metrics, 'published_answer_count') ?? 0;
      return Boolean(document && isDocumentProcessing(document)) || draftCount > publishedCount;
    })
    .map((report) => report.document_id)
    .sort();
  const answerDraftsQuery = useQuery({
    queryKey: ['knowledge-answer-drafts', projectId, draftPreviewDocumentIds.join(','), DRAFT_FETCH_LIMIT],
    queryFn: async () => {
      if (!projectId || draftPreviewDocumentIds.length === 0) return {};

      const drafts = await Promise.all(
        draftPreviewDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.fragments(projectId, documentId, DRAFT_FETCH_LIMIT);
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return drafts.reduce<KnowledgeAnswerDraftsByDocument>((acc, item) => {
        if (item !== null) {
          acc[item[0]] = item[1];
        }
        return acc;
      }, {});
    },
    enabled: !!projectId && draftPreviewDocumentIds.length > 0,
    retry: false,
    refetchInterval: hasProcessingDocuments ? 3000 : false,
  });
  const answerDrafts = answerDraftsQuery.data || {};
  const sourceUnitDocumentIds = Object.values(processingReports)
    .filter((report) => {
      const document = documents.find((doc) => doc.id === report.document_id);
      const sourceCount = metricNumber(report.metrics, 'raw_source_chunk_count')
        ?? metricNumber(report.metrics, 'source_chunk_count')
        ?? (document && Number.isFinite(document.chunk_count) ? document.chunk_count : 0);
      return Boolean(document && isDocumentProcessing(document)) || sourceCount > 0;
    })
    .map((report) => report.document_id)
    .sort();
  const sourceUnitsQuery = useQuery({
    queryKey: ['knowledge-source-units', projectId, sourceUnitDocumentIds.join(','), SOURCE_UNIT_FETCH_LIMIT],
    queryFn: async () => {
      if (!projectId || sourceUnitDocumentIds.length === 0) return {};

      const sourceUnits = await Promise.all(
        sourceUnitDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.sourceUnits(projectId, documentId, SOURCE_UNIT_FETCH_LIMIT);
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return sourceUnits.reduce<KnowledgeSourceUnitsByDocument>((acc, item) => {
        if (item !== null) {
          acc[item[0]] = item[1];
        }
        return acc;
      }, {});
    },
    enabled: !!projectId && sourceUnitDocumentIds.length > 0,
    retry: false,
    refetchInterval: hasProcessingDocuments ? 3000 : false,
  });
  const sourceUnits = sourceUnitsQuery.data || {};
  const priceFactDocumentIds = documents
    .filter((doc) => shouldFetchPriceFactsForDocument(doc, processingReports[doc.id]))
    .map((doc) => doc.id)
    .sort();
  const priceFactsQuery = useQuery({
    queryKey: ['knowledge-price-facts', projectId, priceFactDocumentIds.join(',')],
    queryFn: async () => {
      if (!projectId || priceFactDocumentIds.length === 0) return {};

      const priceFacts = await Promise.all(
        priceFactDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.priceFacts(projectId, documentId);
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return priceFacts.reduce<KnowledgePriceFactsByDocument>((acc, item) => {
        if (item !== null) {
          acc[item[0]] = item[1];
        }
        return acc;
      }, {});
    },
    enabled: !!projectId && priceFactDocumentIds.length > 0,
    retry: false,
    refetchInterval: hasProcessingDocuments ? 3000 : false,
  });
  const priceFacts = priceFactsQuery.data || {};
  const [commercialTruthReviewPolicy, setCommercialTruthReviewPolicy] = useState<KnowledgeCommercialTruthReviewPolicy>('manual_review');
  const projectCommercialTruthReviewQuery = useQuery({
    queryKey: ['project-commercial-truth-review', projectId, commercialTruthReviewPolicy],
    queryFn: async () => {
      if (!projectId) return undefined;

      const { data } = await knowledgeApi.projectCommercialTruthReview(
        projectId,
        commercialTruthReviewPolicy,
      );
      return data;
    },
    enabled: !!projectId,
    retry: false,
    refetchInterval: hasProcessingDocuments ? 3000 : false,
  });
  const commercialTruthReviewQuery = useQuery({
    queryKey: ['knowledge-commercial-truth-review', projectId, priceFactDocumentIds.join(','), commercialTruthReviewPolicy],
    queryFn: async () => {
      if (!projectId || priceFactDocumentIds.length === 0) return {};

      const reviews = await Promise.all(
        priceFactDocumentIds.map(async (documentId) => {
          try {
            const { data } = await knowledgeApi.commercialTruthReview(projectId, documentId, commercialTruthReviewPolicy);
            return [documentId, data] as const;
          } catch {
            return null;
          }
        }),
      );

      return reviews.reduce<KnowledgeCommercialTruthReviewsByDocument>((acc, item) => {
        if (item !== null) {
          acc[item[0]] = item[1];
        }
        return acc;
      }, {});
    },
    enabled: !!projectId && priceFactDocumentIds.length > 0,
    retry: false,
    refetchInterval: hasProcessingDocuments ? 3000 : false,
  });
  const commercialTruthReviews = commercialTruthReviewQuery.data || {};
  const draftsDocument = draftsDocumentId
    ? documents.find((doc) => doc.id === draftsDocumentId) ?? null
    : null;
  const draftsModalResponse = draftsDocumentId ? answerDrafts[draftsDocumentId] : undefined;
  const draftsModalFilter = draftsDocumentId ? draftFiltersByDocument[draftsDocumentId] || '' : '';
  const draftsModalExpandedIds = draftsDocumentId ? expandedDraftIdsByDocument[draftsDocumentId] || [] : [];
  const sourceUnitsDocument = sourceUnitsDocumentId
    ? documents.find((doc) => doc.id === sourceUnitsDocumentId) ?? null
    : null;
  const sourceUnitsModalResponse = sourceUnitsDocumentId ? sourceUnits[sourceUnitsDocumentId] : undefined;
  const sourceUnitsModalFilter = sourceUnitsDocumentId ? sourceUnitFiltersByDocument[sourceUnitsDocumentId] || '' : '';
  const sourceUnitsModalExpandedIds = sourceUnitsDocumentId ? expandedSourceUnitIdsByDocument[sourceUnitsDocumentId] || [] : [];
  const openDraftsModal = (documentId: string): void => {
    setDraftsDocumentId(documentId);
  };
  const openSourceUnitsModal = (documentId: string): void => {
    setSourceUnitsDocumentId(documentId);
  };
  const setDraftFilter = (documentId: string, value: string): void => {
    setDraftFiltersByDocument((current) => ({ ...current, [documentId]: value }));
  };
  const setSourceUnitFilter = (documentId: string, value: string): void => {
    setSourceUnitFiltersByDocument((current) => ({ ...current, [documentId]: value }));
  };
  const toggleDraftExpanded = (documentId: string, draftId: string): void => {
    setExpandedDraftIdsByDocument((current) => {
      const currentIds = current[documentId] || [];
      const nextIds = currentIds.includes(draftId)
        ? currentIds.filter((item) => item !== draftId)
        : [...currentIds, draftId];
      return { ...current, [documentId]: nextIds };
    });
  };
  const toggleSourceUnitExpanded = (documentId: string, sourceUnitId: string): void => {
    setExpandedSourceUnitIdsByDocument((current) => {
      const currentIds = current[documentId] || [];
      const nextIds = currentIds.includes(sourceUnitId)
        ? currentIds.filter((item) => item !== sourceUnitId)
        : [...currentIds, sourceUnitId];
      return { ...current, [documentId]: nextIds };
    });
  };
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [processingNowMs, setProcessingNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!hasProcessingDocuments) return undefined;

    const timer = window.setInterval(() => {
      setProcessingNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, [hasProcessingDocuments]);

  const usageQuery = useQuery({
    queryKey: ['knowledge-usage', projectId],
    queryFn: async () => {
      if (!projectId) return null;
      const { data } = await knowledgeApi.usage(projectId);
      return data;
    },
    enabled: !!projectId,
    retry: false,
    refetchInterval: hasProcessingDocuments ? 5000 : false,
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!projectId) throw new Error(t('knowledge.errors.projectIdMissing'));

      const response = await knowledgeApi.upload(projectId, file, preprocessingMode);

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(getErrorMessage(errData, t('knowledge.feedback.uploadDocumentFailed')));
      }

      return await response.json();
    },
    onSuccess: async () => {
      toast.success(t('knowledge.feedback.documentQueued'));
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-usage', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-processing-reports', projectId] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t('knowledge.feedback.uploadError')));
    },
  });

  const previewMutation = useMutation<KnowledgePreviewResponse, unknown, string>({
    mutationFn: async (question: string) => {
      if (!projectId) throw new Error(t('knowledge.errors.projectIdMissing'));
      const { data } = await knowledgeApi.preview(projectId, question, 5);
      return data;
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t('knowledge.feedback.previewFailed')));
    },
  });

  const clearMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error(t('knowledge.errors.projectIdMissing'));
      await knowledgeApi.clear(projectId);
    },
    onSuccess: async () => {
      setIsClearModalOpen(false);
      setPreviewQuestion('');
      previewMutation.reset();
      toast.success(t('knowledge.feedback.cleared'));
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-usage', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-processing-reports', projectId] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t('knowledge.feedback.clearFailed')));
    },
  });


  const cancelProcessingMutation = useMutation({
    mutationFn: async (documentId: string) => {
      if (!projectId) throw new Error(t('knowledge.errors.projectIdMissing'));
      await knowledgeApi.cancel(projectId, documentId);
    },
    onSuccess: async () => {
      toast.success(t('knowledge.feedback.processingStopped'));
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-usage', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-processing-reports', projectId] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t('knowledge.feedback.stopFailed')));
    },
  });

  const retightenMutation = useMutation({
    mutationFn: async (documentId: string) => {
      if (!projectId) throw new Error(t('knowledge.errors.projectIdMissing'));
      await knowledgeApi.retighten(projectId, documentId);
    },
    onSuccess: async () => {
      toast.success(t('knowledge.feedback.retightenQueued'));
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-usage', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-processing-reports', projectId] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t('knowledge.feedback.retightenFailed')));
    },
  });

  const retryFailedBatchesMutation = useMutation({
    mutationFn: async (documentId: string) => {
      if (!projectId) throw new Error(t('knowledge.errors.projectIdMissing'));
      await knowledgeApi.retryFailedBatches(projectId, documentId);
    },
    onSuccess: async () => {
      toast.success(t('knowledge.feedback.retryFailedBatchesQueued'));
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-usage', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-processing-reports', projectId] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t('knowledge.feedback.retryFailedBatchesFailed')));
    },
  });

  const publishReadyMutation = useMutation({
    mutationFn: async (documentId: string) => {
      if (!projectId) throw new Error(t('knowledge.errors.projectIdMissing'));
      await knowledgeApi.publishReady(projectId, documentId);
    },
    onSuccess: async () => {
      toast.success(t('knowledge.feedback.publishReadyQueued'));
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-usage', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-processing-reports', projectId] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t('knowledge.feedback.publishReadyFailed')));
    },
  });


  const priceFactActionMutation = useMutation<
    'publish' | 'reject',
    unknown,
    PriceFactActionVariables
  >({
    mutationFn: async ({ documentId, factId, reason }) => {
      if (!projectId) throw new Error(t('knowledge.errors.projectIdMissing'));

      if (reason !== undefined) {
        await knowledgeApi.rejectPriceFacts(projectId, documentId, {
          fact_ids: [factId],
          reason,
        });
        return 'reject';
      }

      await knowledgeApi.publishPriceFacts(projectId, documentId, {
        fact_ids: [factId],
      });
      return 'publish';
    },
    onSuccess: async (action) => {
      toast.success(
        action === 'reject'
          ? t('knowledge.priceFacts.actions.rejectSuccess')
          : t('knowledge.priceFacts.actions.publishSuccess'),
      );
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-price-facts', projectId],
      });
    },
    onError: (err: unknown, variables) => {
      toast.error(
        getErrorMessage(
          err,
          variables.reason !== undefined
            ? t('knowledge.priceFacts.actions.rejectFailed')
            : t('knowledge.priceFacts.actions.publishFailed'),
        ),
      );
    },
  });


  const handlePublishPriceFact = (documentId: string, fact: KnowledgePriceFact): void => {
    priceFactActionMutation.mutate({
      documentId,
      factId: fact.id,
    });
  };

  const handleRejectPriceFact = (documentId: string, fact: KnowledgePriceFact): void => {
    const reason = window.prompt(
      t('knowledge.priceFacts.actions.reasonPlaceholder'),
      '',
    );
    if (reason === null) return;

    const cleanedReason = reason.trim();
    if (!cleanedReason) {
      toast.error(t('knowledge.priceFacts.actions.rejectReasonRequired'));
      return;
    }

    priceFactActionMutation.mutate({
      documentId,
      factId: fact.id,
      reason: cleanedReason,
    });
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  };

  const triggerUpload = () => {
    fileInputRef.current?.click();
  };

  const handlePreviewSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = previewQuestion.trim();
    if (!question) {
      toast.error(t('knowledge.feedback.enterClientQuestion'));
      return;
    }
    previewMutation.mutate(question);
  };

  const handleDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
  };

  const handleDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();

    const file = event.dataTransfer.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  };

  if (documentsQuery.isLoading) {
    return (
      <div className="flex justify-center p-4 text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">
        {t('knowledge.loading')}
      </div>
    );
  }

  const filteredDocuments = documents.filter((doc) => (
    doc.file_name.toLowerCase().includes(searchQuery.trim().toLowerCase())
  ));

  const previewResult = previewMutation.data;
  const usage = usageQuery.data;

  const getStatusBadge = (doc: Document) => {
    const status = doc.status;

    if (isDocumentCancelled(doc)) {
      return {
        label: t('knowledge.status.stopped'),
        className: 'bg-[var(--accent-warning-bg)] text-[var(--accent-warning)]',
      };
    }
    if (isDocumentFailed(doc)) {
      return {
        label: t('knowledge.status.error'),
        className: 'bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]',
      };
    }
    if (isDocumentProcessing(doc)) {
      return {
        label: t('knowledge.status.processing'),
        className: 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]',
      };
    }
    if (status === 'processed') {
      return {
        label: t('knowledge.status.processed'),
        className: 'bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]',
      };
    }
    return {
      label: t('knowledge.status.queued'),
      className: 'bg-[var(--accent-warning-bg)] text-[var(--accent-warning)]',
    };
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        className="hidden"
        accept=".pdf,.json,.md,.txt"
      />

      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="mb-2 text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">
            {t('knowledge.title')}
          </h1>
          <p className="text-[var(--text-muted)]">
            {t('knowledge.description')}
          </p>
        </div>
        <div className="flex w-full flex-col gap-3 sm:flex-row lg:w-auto">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
            <input
              type="text"
              placeholder={t('knowledge.search.placeholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] py-2 pl-10 pr-4 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-all focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 lg:w-64"
            />
          </div>
          <button
            type="button"
            onClick={() => setIsClearModalOpen(true)}
            className="inline-flex min-h-10 items-center justify-center rounded-lg bg-[var(--accent-danger-bg)] px-4 py-2 text-sm font-medium text-[var(--accent-danger-text)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--accent-danger-bg)]/80"
          >
            {t('knowledge.actions.clear')}
          </button>
        </div>
      </div>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5 lg:p-6">
        <div className="mb-4 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              {t('knowledge.upload.title')}
            </h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t('knowledge.upload.description')}
            </p>
          </div>

          <label className="flex w-full flex-col gap-2 lg:w-80">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              {t('knowledge.upload.preprocessingMode')}
            </span>
            <select
              value={preprocessingMode}
              onChange={(event) => setPreprocessingMode(event.target.value as KnowledgePreprocessingMode)}
              disabled={uploadMutation.isPending}
              className="min-h-11 rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 disabled:cursor-wait disabled:opacity-60"
            >
              {KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="text-xs leading-relaxed text-[var(--text-muted)]">
              {KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.find((option) => option.value === preprocessingMode)?.description}
            </span>
          </label>
        </div>

        {hasProcessingDocuments && (
          <div className="mb-4 rounded-2xl bg-[var(--accent-primary)]/10 p-4 text-sm text-[var(--text-primary)]">
            <div className="flex items-start gap-3">
              <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-[var(--accent-primary)]" />
              <div>
                <div className="font-semibold">{t('knowledge.processing.title')}</div>
                <p className="mt-1 leading-relaxed text-[var(--text-muted)]">
                  {t('knowledge.processing.descriptionLine1')}
                  {t('knowledge.processing.descriptionLine2')}
                  {t('knowledge.processing.descriptionLine3')}
                </p>
              </div>
            </div>
          </div>
        )}

        <div
          onClick={triggerUpload}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl bg-[var(--surface-card)] p-6 shadow-sm transition-colors group sm:p-8 lg:p-12 ${
            uploadMutation.isPending
              ? 'border-[var(--accent-primary)] bg-[var(--accent-primary)]/5 cursor-wait'
              : 'border-[var(--border-subtle)] hover:bg-[var(--surface-secondary)]'
          }`}
        >
          <div className={`mb-4 flex h-14 w-14 items-center justify-center rounded-full transition-transform sm:h-16 sm:w-16 ${
            uploadMutation.isPending ? 'bg-[var(--accent-primary)]/20 animate-pulse' : 'bg-[var(--accent-primary)]/10 group-hover:scale-110'
          }`}>
            <Upload className="h-7 w-7 text-[var(--accent-primary)] sm:h-8 sm:w-8" />
          </div>
          <h3 className="text-center text-base font-semibold text-[var(--text-primary)] sm:text-lg">
            {uploadMutation.isPending ? t('common.states.loading') : t('knowledge.upload.dropzoneText')}
          </h3>
          <p className="mt-1 text-center text-sm text-[var(--text-muted)]">
            {t('knowledge.upload.acceptedFormats')} · {KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.find((option) => option.value === preprocessingMode)?.label}
          </p>
        </div>
      </section>

      {usage && usage.counter_enabled && <UsageSummaryCard usage={usage} />}

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5 lg:p-6">
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <TestTube2 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              {t('knowledge.preview.title')}
            </h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t('knowledge.preview.description')}
            </p>
          </div>
        </div>

        <form onSubmit={handlePreviewSubmit} className="flex flex-col gap-3 lg:flex-row">
          <textarea
            value={previewQuestion}
            onChange={(event) => setPreviewQuestion(event.target.value)}
            placeholder={t('knowledge.preview.placeholder')}
            rows={3}
            className="min-h-24 flex-1 resize-y rounded-xl bg-[var(--control-bg)] px-4 py-3 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          />
          <button
            type="submit"
            disabled={previewMutation.isPending}
            className="min-h-11 rounded-xl bg-[var(--accent-primary)] px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-wait disabled:opacity-60 lg:self-start"
          >
            {previewMutation.isPending ? t('knowledge.preview.checking') : t('knowledge.preview.check')}
          </button>
        </form>

        {previewResult && (
          <div className="mt-5 space-y-4">
            {previewResult.is_empty || !previewResult.best_result ? (
              <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
                {t('knowledge.preview.noResults')}
              </div>
            ) : (
              <>
                <PreviewResultCard title={t('knowledge.preview.bestAnswer')} result={previewResult.best_result} />
                {previewResult.top_results.length > 1 && (
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                      {t('knowledge.preview.topMatches')}
                    </h3>
                    {previewResult.top_results.slice(1).map((result) => (
                      <PreviewResultCard
                        key={result.id}
                        title={t('knowledge.preview.additionalMatch')}
                        result={result}
                        compact
                      />
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </section>

      {documents.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl bg-[var(--surface-secondary)] p-6 text-center sm:p-10 lg:p-16">
          <BookOpen className="mb-4 h-12 w-12 text-[var(--border-subtle)] sm:h-16 sm:w-16" />
          <h3 className="text-lg font-semibold text-[var(--text-primary)] sm:text-xl">
            {t('knowledge.empty.title')}
          </h3>
          <p className="mt-2 text-[var(--text-muted)]">
            {t('knowledge.empty.description')}
          </p>
        </div>
      ) : (
        <>
          <CommercialTruthReviewSummary
            response={projectCommercialTruthReviewQuery.data}
            isLoading={
              projectCommercialTruthReviewQuery.isLoading
              || (projectCommercialTruthReviewQuery.isFetching && !projectCommercialTruthReviewQuery.data)
            }
            policy={commercialTruthReviewPolicy}
            onPolicyChange={setCommercialTruthReviewPolicy}
          />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 lg:gap-6">
          {filteredDocuments.map((doc) => {
            const statusBadge = getStatusBadge(doc);
            const isRetighteningThisDoc = retightenMutation.isPending && retightenMutation.variables === doc.id;
            const processingReport = processingReports[doc.id];
            const importQualityReport = importQualityReports[doc.id];
            const priceFactsResponse = priceFacts[doc.id];
            const commercialTruthReviewResponse = commercialTruthReviews[doc.id];
            const shouldLoadPriceFacts = priceFactDocumentIds.includes(doc.id);
            const isPriceFactsLoading = shouldLoadPriceFacts
              && (priceFactsQuery.isLoading || (priceFactsQuery.isFetching && !priceFactsResponse));
            const isCommercialTruthReviewLoading = shouldLoadPriceFacts
              && (commercialTruthReviewQuery.isLoading || (commercialTruthReviewQuery.isFetching && !commercialTruthReviewResponse));
            const mutatingPriceFactId = priceFactActionMutation.variables?.documentId === doc.id
              ? priceFactActionMutation.variables.factId
              : null;

            return (
              <KnowledgeDocumentCard
                key={doc.id}
                doc={doc}
                statusBadge={statusBadge}
                isRetighteningThisDoc={isRetighteningThisDoc}
                processingReport={processingReport}
                importQualityReport={importQualityReport}
                priceFactsResponse={priceFactsResponse}
                commercialTruthReviewResponse={commercialTruthReviewResponse}
                isPriceFactsLoading={isPriceFactsLoading}
                isCommercialTruthReviewLoading={isCommercialTruthReviewLoading}
                mutatingPriceFactId={mutatingPriceFactId}
                importQualityLoading={importQualityReportsQuery.isLoading || (importQualityReportsQuery.isFetching && !importQualityReport)}
                commercialTruthReviewPolicy={commercialTruthReviewPolicy}
                onPolicyChange={setCommercialTruthReviewPolicy}
                onPublishFact={(fact) => handlePublishPriceFact(doc.id, fact)}
                onRejectFact={(fact) => handleRejectPriceFact(doc.id, fact)}
                actionsNode={(<DocumentActionsBlock showRetighten={isDocumentRetightenable(doc)} showStop={false} isRetighteningThisDoc={isRetighteningThisDoc} retightenPending={retightenMutation.isPending} cancelPending={cancelProcessingMutation.isPending} onRetighten={() => retightenMutation.mutate(doc.id)} onStop={() => cancelProcessingMutation.mutate(doc.id)} />)}
                processingNode={(
                  <DocumentProcessingBlock
                    doc={doc}
                    processingReport={processingReport}
                    isDocumentProcessing={isDocumentProcessing(doc)}
                    processingProgressLabel={processingProgressLabel(doc)}
                    processingProgressPercent={processingProgressPercent(doc)}
                    processingStatusMessage={processingStatusMessage(doc)}
                    processingModelLabel={processingModelLabel(doc)}
                    processingElapsedLabel={formatDurationSeconds(processingElapsedSeconds(doc, processingNowMs))}
                    processingDetailRows={processingDetailRows(doc)}
                    sourceChunkCount={sourceChunkCount(doc)}
                    incomingAnswerCandidateCount={incomingAnswerCandidateCount(doc)}
                    answerResolutionCount={answerResolutionCount(doc)}
                    documentLlmTokenText={documentLlmTokenText(doc)}
                    documentLlmModels={documentLlmModels(doc)}
                    answerDraftsResponse={answerDrafts[doc.id]}
                    answerDraftsLoading={answerDraftsQuery.isLoading || (answerDraftsQuery.isFetching && !answerDrafts[doc.id])}
                    showDraftSummary={draftPreviewDocumentIds.includes(doc.id)}
                    onOpenDrafts={() => openDraftsModal(doc.id)}
                    sourceUnitsResponse={sourceUnits[doc.id]}
                    sourceUnitsLoading={sourceUnitsQuery.isLoading || (sourceUnitsQuery.isFetching && !sourceUnits[doc.id])}
                    showSourceUnitsSummary={sourceUnitDocumentIds.includes(doc.id)}
                    onOpenSourceUnits={() => openSourceUnitsModal(doc.id)}
                    onRetryFailedBatches={() => retryFailedBatchesMutation.mutate(doc.id)}
                    onPublishReady={() => publishReadyMutation.mutate(doc.id)}
                    retryPending={retryFailedBatchesMutation.isPending}
                    retryTarget={retryFailedBatchesMutation.variables}
                    publishReadyPending={publishReadyMutation.isPending}
                    publishReadyTarget={publishReadyMutation.variables}
                    formatNumber={formatNumber}
                    answerResolutionStepId={ANSWER_RESOLUTION_STEP_ID}
                    renderDraftsSummary={({ response, isLoading, onOpen }) => (
                      <DraftsSummary response={response} isLoading={isLoading} onOpen={onOpen} />
                    )}
                    renderSourceUnitsSummary={({ response, isLoading, onOpen }) => (
                      <SourceUnitsSummary response={response} isLoading={isLoading} onOpen={onOpen} />
                    )}
                    renderAnswerResolutionTracePanel={(report) => <AnswerResolutionTracePanel report={report} />}
                  />
                )}
                retightenReportNode={(() => {
                  const reportRows = retightenReportRows(doc);
                  if (reportRows.length === 0) return null;

                  return (
                    <div className="mb-4 rounded-xl bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-muted)]">
                      <div className="mb-1 font-medium text-[var(--text-primary)]">
                        {t('knowledge.retightenReport.title')}
                      </div>
                      <div className="space-y-1">
                        {reportRows.map((row) => (
                          <div key={row}>{row}</div>
                        ))}
                      </div>
                    </div>
                  );
                })()}
                hasDrafts={draftPreviewDocumentIds.includes(doc.id)}
                draftCount={answerDrafts[doc.id]?.total_count}
                hasSourceUnits={sourceUnitDocumentIds.includes(doc.id)}
                isDocumentProcessing={isDocumentProcessing(doc)}
                onOpenDrafts={() => openDraftsModal(doc.id)}
                onOpenSourceUnits={() => openSourceUnitsModal(doc.id)}
                onStopProcessing={() => cancelProcessingMutation.mutate(doc.id)}
                statusNode={(
                  <DocumentStatusBlock
                    doc={doc}
                    statusBadge={statusBadge}
                    isCancelled={isDocumentCancelled(doc)}
                    isFailed={isDocumentFailed(doc)}
                    issueText={documentIssueText(doc)}
                    processingFailedText={t('knowledge.document.processingFailed')}
                    stoppedWarningText={t('knowledge.document.stoppedWarning')}
                  />
                )}
                formatSize={formatSize}
                knowledgeProcessingModeLabel={knowledgeProcessingModeLabel}
              />
            );
          })}
          </div>
        </>
      )}

      {draftsDocumentId && draftsDocument && (
        <DraftsModal
          documentName={draftsDocument.file_name}
          response={draftsModalResponse}
          isLoading={answerDraftsQuery.isLoading || (answerDraftsQuery.isFetching && !draftsModalResponse)}
          filter={draftsModalFilter}
          expandedDraftIds={draftsModalExpandedIds}
          onFilterChange={(value) => setDraftFilter(draftsDocumentId, value)}
          onToggleDraft={(draftId) => toggleDraftExpanded(draftsDocumentId, draftId)}
          onClose={() => setDraftsDocumentId(null)}
        />
      )}

      {sourceUnitsDocumentId && sourceUnitsDocument && (
        <SourceUnitsModal
          documentName={sourceUnitsDocument.file_name}
          response={sourceUnitsModalResponse}
          isLoading={sourceUnitsQuery.isLoading || (sourceUnitsQuery.isFetching && !sourceUnitsModalResponse)}
          filter={sourceUnitsModalFilter}
          expandedSourceUnitIds={sourceUnitsModalExpandedIds}
          onFilterChange={(value) => setSourceUnitFilter(sourceUnitsDocumentId, value)}
          onToggleSourceUnit={(sourceUnitId) => toggleSourceUnitExpanded(sourceUnitsDocumentId, sourceUnitId)}
          onClose={() => setSourceUnitsDocumentId(null)}
        />
      )}

      <BaseModal
        isOpen={isClearModalOpen}
        onClose={() => {
          if (!clearMutation.isPending) {
            setIsClearModalOpen(false);
          }
        }}
        title={t('knowledge.actions.clear')}
        cancelLabel={t('common.actions.cancel')}
      >
        <p className="text-sm leading-relaxed text-[var(--text-primary)]">
          {t('knowledge.clearModal.confirm')}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => clearMutation.mutate()}
            disabled={clearMutation.isPending}
            className="min-h-9 rounded-lg bg-[var(--accent-danger)] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[var(--accent-danger-text)] disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-[var(--accent-danger)]/25"
          >
            {clearMutation.isPending ? t('knowledge.clearModal.clearing') : t('knowledge.clearModal.clear')}
          </button>
        </div>
      </BaseModal>
    </div>
  );
};
