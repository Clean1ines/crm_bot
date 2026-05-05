import { getSessionToken, handleUnauthorizedResponse } from '@shared/api/core/session';

export type RagEvalMode = 'quick' | 'standard' | 'deep' | 'paranoid';

export interface RagEvalDocumentHealth {
  id: string;
  project_id: string;
  status: string;
  file_name: string;
  chunk_count: number;
}

export interface RagEvalLatestRunSummary {
  id: string;
  dataset_id: string;
  project_id: string;
  document_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  retriever_version: string;
  reranker_version: string;
  generator_model: string;
  result_count: number;
}

export interface RagEvalLatestReportResponse {
  ok: boolean;
  document: RagEvalDocumentHealth;
  report: unknown | null;
}

export interface RagEvalDocumentStatusResponse {
  ok: boolean;
  document: RagEvalDocumentHealth;
  run: RagEvalLatestRunSummary | null;
  report: unknown | null;
}

export interface RagEvalRunResponse {
  ok: boolean;
  document: RagEvalDocumentHealth;
  mode: RagEvalMode;
  max_questions: number;
  dataset_id: string;
  run_id: string;
  questions: number;
  score: number;
  readiness: string;
  report: unknown;
}

export interface RagEvalFullRunAcceptedResponse {
  ok: boolean;
  queued: boolean;
  job_id: string;
  document: RagEvalDocumentHealth;
  mode: 'full_document';
  questions_per_chunk: number;
  target_questions: number;
}

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL
  || import.meta.env.VITE_API_URL
  || ''
).replace(/\/$/, '');

const buildUrl = (path: string): string => `${API_BASE_URL}${path}`;

const authHeaders = (): HeadersInit => {
  const token = getSessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const readErrorMessage = async (response: Response): Promise<string> => {
  const payload = await response.json().catch(() => null);
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    return JSON.stringify(detail);
  }
  return `HTTP ${response.status}`;
};

const requestJson = async <T>(url: string, init: RequestInit): Promise<T> => {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...authHeaders(),
      ...(init.headers || {}),
    },
  });

  if (response.status === 401) {
    handleUnauthorizedResponse();
  }

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return (await response.json()) as T;
};

export const ragEvalApi = {
  getLatestReport(documentId: string): Promise<RagEvalLatestReportResponse> {
    return requestJson<RagEvalLatestReportResponse>(
      buildUrl(`/api/rag-eval/documents/${encodeURIComponent(documentId)}/latest-report`),
      { method: 'GET' },
    );
  },

  getStatus(documentId: string): Promise<RagEvalDocumentStatusResponse> {
    return requestJson<RagEvalDocumentStatusResponse>(
      buildUrl(`/api/rag-eval/documents/${encodeURIComponent(documentId)}/status`),
      { method: 'GET' },
    );
  },

  runFullDocumentEval(
    documentId: string,
    params: { questionsPerChunk: number; maxQuestions?: number | null },
  ): Promise<RagEvalFullRunAcceptedResponse> {
    const query = new URLSearchParams({
      questions_per_chunk: String(params.questionsPerChunk),
    });

    if (params.maxQuestions != null) {
      query.set('max_questions', String(params.maxQuestions));
    }

    return requestJson<RagEvalFullRunAcceptedResponse>(
      buildUrl(`/api/rag-eval/documents/${encodeURIComponent(documentId)}/run-full?${query.toString()}`),
      { method: 'POST' },
    );
  },

  runDocumentEval(
    documentId: string,
    params: { mode: RagEvalMode; maxQuestions?: number | null },
  ): Promise<RagEvalRunResponse> {
    const query = new URLSearchParams({ mode: params.mode });
    if (params.maxQuestions != null) {
      query.set('max_questions', String(params.maxQuestions));
    }

    return requestJson<RagEvalRunResponse>(
      buildUrl(`/api/rag-eval/documents/${encodeURIComponent(documentId)}/run?${query.toString()}`),
      { method: 'POST' },
    );
  },
};
