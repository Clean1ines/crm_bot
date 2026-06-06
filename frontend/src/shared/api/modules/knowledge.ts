import { t } from '../../i18n';
import { authedJsonRequest, authedMultipartRequest } from '../core/http';

export type KnowledgePreprocessingMode = 'faq' | 'price_list';
export type KnowledgePreviewRetrievalMode = 'runtime_equivalent' | 'lexical_debug';

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
  retrieval_mode: KnowledgePreviewRetrievalMode;
  method: string;
  trace: Record<string, unknown>;
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

export type WorkbenchDocumentCardMessageSeverity =
  | 'info'
  | 'success'
  | 'warning'
  | 'error'
  | string;

export type WorkbenchDocumentCardActionTone =
  | 'primary'
  | 'secondary'
  | 'warning'
  | 'danger'
  | string;

export type WorkbenchDocumentCardUserMessage = {
  code: string;
  severity: WorkbenchDocumentCardMessageSeverity;
  i18n_key: string;
  default_message: string;
  debug_ref?: string | null;
};

export type WorkbenchDocumentCardErrorView = {
  reason_code: string;
  user_message: WorkbenchDocumentCardUserMessage;
  recoverable: boolean;
  retry_available: boolean;
  internal_error_ref?: string | null;
};

export type WorkbenchDocumentCardTimerView = {
  mode: 'running' | 'paused' | 'stopped' | 'completed' | 'published' | string;
  active_elapsed_seconds: number;
  wall_elapsed_seconds: number;
  current_active_started_at?: string | null;
  i18n_key: string;
  default_label: string;
};

export type WorkbenchDocumentCardUsageView = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  llm_call_count: number;
  i18n_key?: string;
};

export type WorkbenchDocumentCardSectionSummaryView = {
  total: number;
  processed: number;
  failed: number;
  pending: number;
};

export type WorkbenchDocumentCardRegistrySummaryView = {
  entry_count: number;
  final_snapshot_id?: string | null;
  retained: boolean;
};

export type WorkbenchDocumentCardSurfaceSummaryView = {
  draft_count: number;
  ready_count: number;
  published_count: number;
  rejected_count: number;
};

export type WorkbenchDocumentCardRuntimeSummaryView = {
  publication_id?: string | null;
  runtime_entry_count: number;
};

export type WorkbenchDocumentCardRecoveryView = {
  mode: 'none' | 'scheduled_auto_resume' | 'manual_only' | 'forbidden' | string;
  scheduled_at?: string | null;
  can_cancel_scheduled_resume: boolean;
  reason_code: string;
  i18n_key: string;
  default_message: string;
};

export type WorkbenchDocumentCardActionView = {
  action_id:
    | 'cancel_processing'
    | 'resume_processing'
    | 'cancel_scheduled_recovery'
    | 'delete_document'
    | 'open_workbench'
    | 'open_curation'
    | 'publish_ready'
    | 'open_published_surfaces'
    | 'reprocess_fresh'
    | string;
  visible: boolean;
  enabled: boolean;
  tone: WorkbenchDocumentCardActionTone;
  i18n_key: string;
  default_label: string;
  reason_code?: string | null;
  confirmation_i18n_key?: string | null;
  default_confirmation?: string | null;
};

export type WorkbenchDocumentCardView = {
  document_id: string;
  project_id: string;
  file_name: string;
  source_type: string;
  lifecycle_state: string;
  retention_state: string;
  transient_purged: boolean;
  resume_available: boolean;
  status_i18n_key: string;
  default_status_label: string;
  status_description_i18n_key: string;
  default_status_description: string;
  timer: WorkbenchDocumentCardTimerView;
  usage: WorkbenchDocumentCardUsageView;
  sections: WorkbenchDocumentCardSectionSummaryView;
  registry: WorkbenchDocumentCardRegistrySummaryView;
  surfaces: WorkbenchDocumentCardSurfaceSummaryView;
  runtime: WorkbenchDocumentCardRuntimeSummaryView;
  recovery: WorkbenchDocumentCardRecoveryView;
  actions: WorkbenchDocumentCardActionView[];
  messages: WorkbenchDocumentCardUserMessage[];
  error?: WorkbenchDocumentCardErrorView | null;
  metadata?: Record<string, unknown>;
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

export type KnowledgeDocumentDeleteResponse = {
  status: string;
  document_id: string;
};


export interface WorkbenchEvidenceTraceDocument {
  project_id: string;
  document_id: string;
  file_name: string;
  source_type?: string;
  file_size_bytes?: number;
  status?: string;
  current_processing_run_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  deleted_at?: string | null;
}

export interface WorkbenchEvidenceTraceFinding {
  claim_observation_id: string;
  section_id: string;
  action: string;
  status: string;
  target_fact_id?: string | null;
  claim_local_ref?: string | null;
  title?: string | null;
  claim?: string | null;
  claim_kind?: string;
  answer?: string | null;
  short_answer?: string | null;
  claim_delta?: string | null;
  variants: unknown[];
  evidence_quotes: unknown[];
  source_refs: unknown[];
  source_chunk_indexes: unknown[];
  confidence?: number | null;
  reason?: string | null;
  created_at?: string | null;
}

export interface WorkbenchEvidenceTraceCanonicalFact {
  fact_id: string;
  fact_key: string;
  claim: string;
  question_variants: unknown[];
  claim_kind: string;
  answer: string;
  short_answer: string;
  evidence_quotes: unknown[];
  source_refs: unknown[];
  source_section_ids: unknown[];
  source_chunk_indexes: unknown[];
  status: string;
  updated_at?: string | null;
}

export interface WorkbenchEvidenceTraceSurface {
  surface_id: string;
  fact_id?: string | null;
  title: string;
  claim: string;
  question_variants: unknown[];
  answer: string;
  short_answer: string;
  evidence_quotes: unknown[];
  source_refs: unknown[];
  source_section_ids: unknown[];
  claim_kind: string;
  status: string;
  curation_state: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkbenchEvidenceTraceSourceUnit {
  unit_id: string;
  source_unit_id: string;
  section_id: string;
  section_key: string;
  section_index: number;
  title: string;
  status: string;
  source_refs: unknown[];
  source_chunk_indexes: unknown[];
  metadata: Record<string, unknown>;
  text_excerpt: string;
  raw_text_excerpt: string;
  findings: WorkbenchEvidenceTraceFinding[];
  canonical_facts: WorkbenchEvidenceTraceCanonicalFact[];
  surfaces: WorkbenchEvidenceTraceSurface[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkbenchEvidenceTraceResponse {
  document: WorkbenchEvidenceTraceDocument;
  source_units: WorkbenchEvidenceTraceSourceUnit[];
  items: WorkbenchEvidenceTraceSourceUnit[];
  findings: WorkbenchEvidenceTraceFinding[];
  canonical_facts: WorkbenchEvidenceTraceCanonicalFact[];
  surfaces: WorkbenchEvidenceTraceSurface[];
  coverage: Record<string, number>;
  gaps: Record<string, unknown>;
}

export type SurfaceEditRequest = {
  title?: string;
  answer?: string;
  short_answer?: string;
  question_variants?: string[];
  retrieval_scope?: string;
  exclusion_scope?: string;
};

export type SurfaceRejectRequest = {
  reason?: string;
};

export type SurfaceMergeFactsRequest = {
  source_fact_ids: string[];
  reason?: string;
};

export type SurfaceDeleteFactRequest = {
  reason?: string;
};

export type SurfacePublishSelectedRequest = {
  surface_ids: string[];
};

export type SurfaceCurationMutationResponse = {
  project_id: string;
  document_id: string;
  action: string;
  affected_count: number;
  item?: Record<string, unknown> | null;
  items?: Array<Record<string, unknown>>;
};


export const knowledgeApi = {
  list: (projectId: string) =>
    authedJsonRequest<{ documents?: Array<Record<string, unknown>>; items?: Array<Record<string, unknown>> }>(`/api/projects/${projectId}/knowledge`, {
      method: 'GET',
    }),

  clear: (projectId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge`, {
      method: 'DELETE',
    }),

  deleteDocument: (projectId: string, documentId: string) =>
    authedJsonRequest<KnowledgeDocumentDeleteResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}`,
      {
        method: 'DELETE',
      },
    ),

  cancel: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/${documentId}/cancel`, {
      method: 'POST',
    }),

  resumeProcessing: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/${documentId}/resume-processing`, {
      method: 'POST',
    }),

  publishReady: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/${documentId}/publish-ready`, {
      method: 'POST',
    }),

  evidenceTrace: (projectId: string, documentId: string) =>
    authedJsonRequest<WorkbenchEvidenceTraceResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/evidence-trace`,
      {
        method: 'GET',
      },
    ),

  approveSurface: (projectId: string, documentId: string, surfaceId: string) =>
    authedJsonRequest<SurfaceCurationMutationResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/surfaces/${surfaceId}/approve`,
      {
        method: 'POST',
      },
    ),

  rejectSurface: (
    projectId: string,
    documentId: string,
    surfaceId: string,
    payload: SurfaceRejectRequest,
  ) =>
    authedJsonRequest<SurfaceCurationMutationResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/surfaces/${surfaceId}/reject`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  editSurface: (
    projectId: string,
    documentId: string,
    surfaceId: string,
    payload: SurfaceEditRequest,
  ) =>
    authedJsonRequest<SurfaceCurationMutationResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/surfaces/${surfaceId}`,
      {
        method: 'PATCH',
        body: JSON.stringify(payload),
      },
    ),

  mergeFacts: (
    projectId: string,
    documentId: string,
    targetFactId: string,
    payload: SurfaceMergeFactsRequest,
  ) =>
    authedJsonRequest<SurfaceCurationMutationResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/facts/${targetFactId}/merge`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  deleteFact: (
    projectId: string,
    documentId: string,
    factId: string,
    payload: SurfaceDeleteFactRequest,
  ) =>
    authedJsonRequest<SurfaceCurationMutationResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/facts/${factId}`,
      {
        method: 'DELETE',
        body: JSON.stringify(payload),
      },
    ),

  publishSelectedSurfaces: (
    projectId: string,
    documentId: string,
    payload: SurfacePublishSelectedRequest,
  ) =>
    authedJsonRequest<SurfaceCurationMutationResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/surfaces/publish-selected`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  progress: (projectId: string, documentId: string) =>
    authedJsonRequest<KnowledgeProcessingReport>(
      `/api/projects/${projectId}/knowledge/${documentId}/progress`,
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

  preview: (
    projectId: string,
    question: string,
    limit = 5,
    retrievalMode: KnowledgePreviewRetrievalMode = 'runtime_equivalent',
  ) =>
    authedJsonRequest<
      KnowledgePreviewResponse,
      { question: string; limit: number; retrieval_mode: KnowledgePreviewRetrievalMode }
    >(
      `/api/projects/${projectId}/knowledge/preview`,
      {
        method: 'POST',
        body: { question, limit, retrieval_mode: retrievalMode },
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
