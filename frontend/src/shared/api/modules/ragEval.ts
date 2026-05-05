import { authedJsonRequest } from '@shared/api/core/http';

export interface RagEvalFullRunAcceptedResponse {
  ok: boolean;
  job_id: string;
  document_id: string;
  project_id: string;
  source_chunk_count: number;
  questions_per_chunk: number;
  target_questions: number;
  max_questions: number | null;
  retrieval_limit: number;
}

export interface RagEvalDocumentStatusResponse {
  ok: boolean;
  document: Record<string, unknown>;
  run: Record<string, unknown> | null;
  report: Record<string, unknown> | null;
}

export interface RagEvalLatestReportResponse {
  ok: boolean;
  document: Record<string, unknown>;
  report: Record<string, unknown> | null;
}

export interface RagEvalRunAcceptedResponse {
  ok: boolean;
  run_id?: string;
  report?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface RagEvalProgressPayload {
  stage?: string;
  status?: string;
  percent?: number;
  generated_questions?: number;
  target_questions?: number;
  processed_questions?: number;
  total_questions?: number;
  source_chunk_count?: number;
  processed_batches?: number;
  total_batches?: number;
  dataset_id?: string;
  run_id?: string;
  report_id?: string;
  score?: number;
  readiness?: string;
  updated_at?: string;
  message?: string;
  [key: string]: unknown;
}

export interface RagEvalJob {
  id: string;
  task_type: string;
  status: string;
  attempts: number;
  max_attempts: number;
  created_at: string | null;
  updated_at: string | null;
  locked_at: string | null;
  error: string | null;
  payload: Record<string, unknown>;
  progress: RagEvalProgressPayload | null;
}

export interface RagEvalJobsResponse {
  ok: boolean;
  document: Record<string, unknown>;
  jobs: RagEvalJob[];
}

export interface RagEvalJobProgressResponse {
  ok: boolean;
  job: RagEvalJob;
}

export interface RagEvalJobActionResponse {
  ok: boolean;
  job: RagEvalJob;
}

interface RunFullDocumentEvalOptions {
  questionsPerChunk?: number;
  maxQuestions?: number;
}

interface RunDocumentEvalOptions {
  mode?: 'quick' | 'standard' | 'deep' | 'paranoid';
  maxQuestions?: number;
}

const encode = (value: string): string => encodeURIComponent(value);

const unwrap = async <T>(promise: Promise<{ data: T }>): Promise<T> => {
  const response = await promise;
  return response.data;
};

export const ragEvalApi = {
  async getLatestReport(documentId: string): Promise<RagEvalLatestReportResponse> {
    return unwrap(
      authedJsonRequest<RagEvalLatestReportResponse>(
        `/api/rag-eval/documents/${encode(documentId)}/latest-report`,
        { method: 'GET' },
      ),
    );
  },

  async getStatus(documentId: string): Promise<RagEvalDocumentStatusResponse> {
    return unwrap(
      authedJsonRequest<RagEvalDocumentStatusResponse>(
        `/api/rag-eval/documents/${encode(documentId)}/status`,
        { method: 'GET' },
      ),
    );
  },

  async listJobs(documentId: string): Promise<RagEvalJobsResponse> {
    return unwrap(
      authedJsonRequest<RagEvalJobsResponse>(
        `/api/rag-eval/documents/${encode(documentId)}/jobs`,
        { method: 'GET' },
      ),
    );
  },

  async getJobProgress(jobId: string): Promise<RagEvalJobProgressResponse> {
    return unwrap(
      authedJsonRequest<RagEvalJobProgressResponse>(
        `/api/rag-eval/jobs/${encode(jobId)}/progress`,
        { method: 'GET' },
      ),
    );
  },

  async cancelJob(jobId: string): Promise<RagEvalJobActionResponse> {
    return unwrap(
      authedJsonRequest<RagEvalJobActionResponse>(
        `/api/rag-eval/jobs/${encode(jobId)}/cancel`,
        { method: 'POST' },
      ),
    );
  },

  async pauseJob(jobId: string): Promise<RagEvalJobActionResponse> {
    return unwrap(
      authedJsonRequest<RagEvalJobActionResponse>(
        `/api/rag-eval/jobs/${encode(jobId)}/pause`,
        { method: 'POST' },
      ),
    );
  },

  async resumeJob(jobId: string): Promise<RagEvalJobActionResponse> {
    return unwrap(
      authedJsonRequest<RagEvalJobActionResponse>(
        `/api/rag-eval/jobs/${encode(jobId)}/resume`,
        { method: 'POST' },
      ),
    );
  },

  async runFullDocumentEval(
    documentId: string,
    options: RunFullDocumentEvalOptions = {},
  ): Promise<RagEvalFullRunAcceptedResponse> {
    const query = new URLSearchParams();

    if (options.questionsPerChunk !== undefined) {
      query.set('questions_per_chunk', String(options.questionsPerChunk));
    }

    if (options.maxQuestions !== undefined) {
      query.set('max_questions', String(options.maxQuestions));
    }

    const suffix = query.toString() ? `?${query.toString()}` : '';

    return unwrap(
      authedJsonRequest<RagEvalFullRunAcceptedResponse>(
        `/api/rag-eval/documents/${encode(documentId)}/run-full${suffix}`,
        { method: 'POST' },
      ),
    );
  },

  async runDocumentEval(
    documentId: string,
    options: RunDocumentEvalOptions = {},
  ): Promise<RagEvalRunAcceptedResponse> {
    const query = new URLSearchParams();

    if (options.mode) {
      query.set('mode', options.mode);
    }

    if (options.maxQuestions !== undefined) {
      query.set('max_questions', String(options.maxQuestions));
    }

    const suffix = query.toString() ? `?${query.toString()}` : '';

    return unwrap(
      authedJsonRequest<RagEvalRunAcceptedResponse>(
        `/api/rag-eval/documents/${encode(documentId)}/run${suffix}`,
        { method: 'POST' },
      ),
    );
  },
};
