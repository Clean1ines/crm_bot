import { authedJsonRequest, authedMultipartRequest } from '../core/http';

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

export const knowledgeApi = {
  list: (projectId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge`, {
      method: 'GET',
    }),

  preview: (projectId: string, question: string, limit = 5) =>
    authedJsonRequest<KnowledgePreviewResponse, { question: string; limit: number }>(
      `/api/projects/${projectId}/knowledge/preview`,
      {
        method: 'POST',
        body: { question, limit },
      },
    ),

  upload: (projectId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);

    return authedMultipartRequest(`/api/projects/${projectId}/knowledge`, formData);
  },
};
