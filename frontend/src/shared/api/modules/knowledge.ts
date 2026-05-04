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
    label: 'FAQ / база знаний',
    description: 'Лучше для вопросов клиентов, описания услуг, условий, частых ответов.',
  },
  {
    value: 'price_list',
    label: 'Прайс / каталог',
    description: 'Лучше для тарифов, меню, товаров, услуг и цен.',
  },
  {
    value: 'instruction',
    label: 'Инструкции / правила',
    description: 'Лучше для регламентов, политик, процедур и внутренних правил.',
  },
  {
    value: 'plain',
    label: 'Без предобработки',
    description: 'Быстрая загрузка обычными чанками без LLM-нормализации.',
  },
];

export type KnowledgePreviewResult = {
  id: string;
  content: string;
  answer: string;
  score: number;
  method: string;
  source: string | null;
  document_id: string | null;
  document_status: string | null;
};

export type KnowledgePreviewResponse = {
  query: string;
  best_result: KnowledgePreviewResult | null;
  top_results: KnowledgePreviewResult[];
  is_empty: boolean;
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
