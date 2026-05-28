import { t } from '../../i18n';
import { authedJsonRequest, authedMultipartRequest } from '../core/http';

export type KnowledgePreprocessingMode = 'faq' | 'price_list';

export type KnowledgePreprocessingModeOption = {
  value: KnowledgePreprocessingMode;
  label: string;
  description: string;
};

export const KNOWLEDGE_PREPROCESSING_MODE_OPTIONS: KnowledgePreprocessingModeOption[] = [
  {
    value: 'faq',
    label: t('knowledge.preprocessing.faq.label'),
    description: t('knowledge.preprocessing.faq.description'),
  },
  {
    value: 'price_list',
    label: t('knowledge.preprocessing.priceList.label'),
    description: t('knowledge.preprocessing.priceList.description'),
  },
];

export type KnowledgeSearchTrace = {
  matched_fields: string[];
  lexical_score: number;
  vector_score: number;
  exact_question_match: boolean;
  title_match: boolean;
  length_penalty: number;
  final_score: number;
  retrieval_surface_role: string;
  displayed_field: string;
  is_production_safe: boolean;
};

export type KnowledgePreviewResult = {
  id: string;
  content: string;
  answer: string;
  score: number;
  method: string;
  source: string | null;
  document_id: string | null;
  document_status: string | null;
  entry_kind?: string | null;
  title?: string | null;
  source_excerpt?: string | null;
  questions?: unknown;
  synonyms?: unknown;
  tags?: unknown;
  trace?: KnowledgeSearchTrace | null;
};

export type KnowledgePreviewResponse = {
  query: string;
  best_result: KnowledgePreviewResult | null;
  top_results: KnowledgePreviewResult[];
  is_empty: boolean;
};


export type KnowledgeProcessingStep = {
  id: string;
  label: string;
  status: string;
  current: number;
  total: number;
  message: string;
};

export type KnowledgeProcessingAction = {
  id: string;
  label: string;
  kind: string;
  enabled: boolean;
};

export type KnowledgeProcessingReport = {
  document_id: string;
  status: string;
  title: string;
  message: string;
  recoverable: boolean;
  steps: KnowledgeProcessingStep[];
  actions: KnowledgeProcessingAction[];
  metrics: Record<string, unknown>;
};

export type KnowledgeProcessingOverviewDocument = Record<string, unknown>;

export type KnowledgeProcessingOverviewResponse = {
  documents: KnowledgeProcessingOverviewDocument[];
  processing_reports: Record<string, KnowledgeProcessingReport>;
  reports: Record<string, KnowledgeProcessingReport>;
  partial_surface_count: Record<string, number>;
  source_unit_summary: Record<string, Record<string, unknown>>;
  groq_route_summary: Record<string, Record<string, unknown>>;
  economy_mode_summary: Record<string, Record<string, unknown>>;
};

export type KnowledgeAnswerDraft = {
  id: string;
  title: string;
  answer: string;
  status: string;
  batch_id: string;
  batch_index: number | null;
  fragment_index: number | null;
  canonical_question: string;
  question_variants: string[];
  synonyms: string[];
  tags: string[];
  source_chunk_indexes: number[];
  source_refs: Array<{
    quote: string;
    source_index?: number;
    source_chunk_id?: string;
    start_offset?: number;
    end_offset?: number;
    confidence?: number;
  }>;
  rejection_reason: string;
};

export type KnowledgeAnswerDraftsResponse = {
  document_id: string;
  drafts: KnowledgeAnswerDraft[];
  total_count: number;
};

export type KnowledgeSourceUnit = {
  id: string;
  source_index: number;
  title: string;
  content: string;
  page?: number;
  start_offset?: number;
  end_offset?: number;
  metadata: Record<string, unknown>;
  draft_count: number;
  draft_titles: string[];
  draft_ids: string[];
};

export type KnowledgeSourceUnitsResponse = {
  document_id: string;
  source_units: KnowledgeSourceUnit[];
  total_count: number;
};


export type KnowledgePriceValueKind =
  | 'exact'
  | 'starting_from'
  | 'range'
  | 'on_request'
  | string;

export type KnowledgePriceFactStatus =
  | 'draft'
  | 'needs_review'
  | 'published'
  | 'rejected'
  | 'superseded'
  | string;

export type KnowledgePriceMoney = {
  amount: string;
  currency: string;
};

export type KnowledgePriceRange = {
  min_amount: KnowledgePriceMoney;
  max_amount: KnowledgePriceMoney;
};

export type KnowledgePriceCondition = {
  text: string;
};

export type KnowledgePriceSourceRef = {
  price_document_id: string;
  source_unit_id: string;
  source_row_id?: string;
  quote: string;
};

export type KnowledgePriceFact = {
  id: string;
  project_id: string;
  price_document_id: string;
  item_name: string;
  value_kind: KnowledgePriceValueKind;
  status: KnowledgePriceFactStatus;
  unit: string;
  amount?: KnowledgePriceMoney;
  price_range?: KnowledgePriceRange;
  price_text: string;
  variant: Record<string, string>;
  aliases: string[];
  conditions: KnowledgePriceCondition[];
  source_refs: KnowledgePriceSourceRef[];
  confidence: string;
};

export type KnowledgePriceFactsResponse = {
  knowledge_document_id: string;
  price_document_id: string | null;
  facts: KnowledgePriceFact[];
  items: KnowledgePriceFact[];
  is_empty: boolean;
};


export type KnowledgePriceFactsMutationResponse = {
  knowledge_document_id: string;
  price_document_id: string;
  affected_count: number;
  facts: KnowledgePriceFact[];
  items: KnowledgePriceFact[];
};

export type KnowledgeCommercialTruthReviewPolicy =
  | 'manual_review'
  | 'higher_authority_wins'
  | 'newer_source_wins';

export type KnowledgeCommercialTruthFactReview = {
  fact_id: string;
  price_document_id: string;
  item_name: string;
  value_kind: string;
  status: string;
  unit: string;
  value_text: string;
  source_quote: string;
  source_id: string;
  source_title: string;
  source_observed_at: string;
  source_kind: string;
  source_authority: string;
  is_runtime_eligible: boolean;
};

export type KnowledgeCommercialTruthConflictReview = {
  identity_key: string;
  reason: string;
  resolution_status: string;
  resolution_reason: string;
  selected_fact_id: string | null;
  options: KnowledgeCommercialTruthFactReview[];
};

export type KnowledgeCommercialTruthReviewResponse = {
  policy: string;
  fact_count: number;
  conflict_count: number;
  resolved_conflict_count: number;
  unresolved_conflict_count: number;
  surface_fact_ids: string[];
  surface_facts: KnowledgeCommercialTruthFactReview[];
  facts: KnowledgeCommercialTruthFactReview[];
  conflicts: KnowledgeCommercialTruthConflictReview[];
};

export type KnowledgePriceFactsActionRequest = {
  fact_ids: string[];
  reason?: string;
};

export type KnowledgeImportQualityStatus = 'good' | 'needs_review' | 'unsafe' | string;

export type KnowledgeImportIssueSeverity = 'info' | 'warning' | 'error' | string;

export type KnowledgeImportIssue = {
  code: string;
  severity: KnowledgeImportIssueSeverity;
  message: string;
};

export type KnowledgeImportQualityReport = {
  document_id: string;
  status: KnowledgeImportQualityStatus;
  safe_to_compile: boolean;
  source_format: string;
  extracted_text_chars: number;
  source_units_count: number;
  empty_units_count: number;
  short_units_count: number;
  table_like_units_count: number;
  duplicated_headings_count: number;
  source_refs_ready: boolean;
  warnings: KnowledgeImportIssue[];
  recommended_action: string;
};

export type KnowledgeUsageBreakdown = {
  provider: string;
  model: string;
  usage_type: string;
  source: string;
  tokens_input: number;
  tokens_output: number;
  tokens_total: number;
  estimated_cost_usd: number;
  events_count: number;
};

export type KnowledgeUsageDaily = {
  day: string;
  tokens_total: number;
  estimated_cost_usd: number;
};

export type KnowledgeUsageResponse = {
  counter_enabled: boolean;
  monthly_budget_tokens: number;
  remaining_tokens: number;
  tokens_month_total: number;
  tokens_today_total: number;
  estimated_cost_month_usd: number;
  breakdown: KnowledgeUsageBreakdown[];
  daily: KnowledgeUsageDaily[];
};

export const knowledgeApi = {
  list: (projectId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge`, {
      method: 'GET',
    }),

  clear: (projectId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge`, {
      method: 'DELETE',
    }),

  cancel: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/${documentId}/cancel`, {
      method: 'POST',
    }),

  resumeProcessing: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/${documentId}/resume-processing`, {
      method: 'POST',
    }),

  retighten: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/${documentId}/retighten`, {
      method: 'POST',
    }),

  publishReady: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/${documentId}/publish-ready`, {
      method: 'POST',
    }),

  retryFailedBatches: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/${documentId}/retry-failed-batches`, {
      method: 'POST',
    }),

  progress: (projectId: string, documentId: string) =>
    authedJsonRequest<KnowledgeProcessingReport>(
      `/api/projects/${projectId}/knowledge/${documentId}/progress`,
      {
        method: 'GET',
      },
    ),

  processingOverview: (projectId: string) =>
    authedJsonRequest<KnowledgeProcessingOverviewResponse>(
      `/api/projects/${projectId}/knowledge/processing-overview`,
      {
        method: 'GET',
      },
    ),

  fragments: (projectId: string, documentId: string, limit = 5) =>
    authedJsonRequest<KnowledgeAnswerDraftsResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/fragments?limit=${limit}`,
      {
        method: 'GET',
      },
    ),

  sourceUnits: (projectId: string, documentId: string, limit = 1000) =>
    authedJsonRequest<KnowledgeSourceUnitsResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/source-units?limit=${limit}`,
      {
        method: 'GET',
      },
    ),

  priceFacts: (projectId: string, documentId: string) =>
    authedJsonRequest<KnowledgePriceFactsResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/price-facts`,
      {
        method: 'GET',
      },
    ),

  projectCommercialTruthReview: (
    projectId: string,
    policy: KnowledgeCommercialTruthReviewPolicy = 'manual_review',
  ) =>
    authedJsonRequest<KnowledgeCommercialTruthReviewResponse>(
      `/api/projects/${projectId}/knowledge/commercial-truth-review?policy=${policy}`,
      {
        method: 'GET',
      },
    ),

  commercialTruthReview: (
    projectId: string,
    documentId: string,
    policy: KnowledgeCommercialTruthReviewPolicy = 'manual_review',
  ) =>
    authedJsonRequest<KnowledgeCommercialTruthReviewResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/commercial-truth-review?policy=${policy}`,
      {
        method: 'GET',
      },
    ),

  publishPriceFacts: (
    projectId: string,
    documentId: string,
    payload: KnowledgePriceFactsActionRequest,
  ) =>
    authedJsonRequest<KnowledgePriceFactsMutationResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/price-facts/publish`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  rejectPriceFacts: (
    projectId: string,
    documentId: string,
    payload: KnowledgePriceFactsActionRequest,
  ) =>
    authedJsonRequest<KnowledgePriceFactsMutationResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/price-facts/reject`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  importQuality: (projectId: string, documentId: string) =>
    authedJsonRequest<KnowledgeImportQualityReport>(
      `/api/projects/${projectId}/knowledge/${documentId}/import-quality`,
      {
        method: 'GET',
      },
    ),

  preview: (projectId: string, question: string, limit = 5) =>
    authedJsonRequest<KnowledgePreviewResponse, { question: string; limit: number }>(
      `/api/projects/${projectId}/knowledge/preview`,
      {
        method: 'POST',
        body: { question, limit },
      },
    ),

  usage: (projectId: string) =>
    authedJsonRequest<KnowledgeUsageResponse>(`/api/projects/${projectId}/knowledge/usage`, {
      method: 'GET',
    }),

  upload: (
    projectId: string,
    file: File,
    preprocessingMode: KnowledgePreprocessingMode = 'faq',
  ) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preprocessing_mode', preprocessingMode);

    return authedMultipartRequest(`/api/projects/${projectId}/knowledge`, formData);
  },
};
