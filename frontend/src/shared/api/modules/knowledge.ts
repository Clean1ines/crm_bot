import { t } from '../../i18n';
import { authedJsonRequest, authedMultipartRequest } from '../core/http';

export type KnowledgePreprocessingMode = 'plain' | 'faq' | 'price_list' | 'instruction';

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
  {
    value: 'instruction',
    label: t('knowledge.preprocessing.instruction.label'),
    description: t('knowledge.preprocessing.instruction.description'),
  },
  {
    value: 'plain',
    label: t('knowledge.preprocessing.plain.label'),
    description: t('knowledge.preprocessing.plain.description'),
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

  retighten: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/${documentId}/retighten`, {
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
