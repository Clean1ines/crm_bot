import { authedJsonRequest } from '@shared/api/core/http';

export interface RagEvalFullRunAcceptedResponse {
  ok: boolean;
  queued: boolean;
  job_id: string;
  document: Record<string, unknown>;
  mode: string;
}

export interface RagEvalDocumentStatusResponse {
  ok: boolean;
  document: Record<string, unknown>;
  run: (Record<string, unknown> & { results?: RagEvalResultSummary[] }) | null;
  report: (Record<string, unknown> & { results?: RagEvalResultSummary[] }) | null;
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

export interface RagEvalResultSummary {
  result_id: string;
  run_id: string;
  question_id: string;
  question: string;
  question_type: string;
  expected_entry_ids: string[];
  retrieved_entry_ids: string[];
  top1_hit?: boolean;
  top3_hit?: boolean;
  top5_hit?: boolean;
  expected_entry_found?: boolean;
  wrong_entry_top1: boolean;
  answer_supported: boolean;
  should_answer_passed: boolean;
  hallucination_risk: string;
  score: number;
  notes?: string;
  latency_ms?: number;
  created_at?: string;
  classification: Record<string, unknown> | null;
  proposed_actions: RagEvalProposedActionSummary[];
}

export interface RagEvalProgressPayload {
  stage?: string;
  status?: string;
  percent?: number;
  generated_questions?: number;
  processed_questions?: number;
  total_questions?: number;
  source_chunk_count?: number;
  processed_batches?: number;
  total_batches?: number;
  successful_batches?: number;
  failed_batches?: number;
  skipped_batches?: number;
  json_parse_failures?: number;
  provider_failures?: number;
  retry_count?: number;
  failed_retrieval_count?: number;
  dataset_generation_concurrency?: number;
  retrieval_concurrency?: number;
  dataset_id?: string;
  run_id?: string;
  report_id?: string;
  score?: number;
  readiness?: string;
  tokens_input?: number;
  tokens_output?: number;
  tokens_total?: number;
  question_tokens_total?: number;
  judge_tokens_total?: number;
  updated_at?: string;
  message?: string;
  [key: string]: unknown;
}

export interface RagEvalJob {
  id: string;
  task_type: string;
  status: string;
  effective_status?: string;
  attempts: number;
  max_attempts: number;
  created_at: string | null;
  updated_at: string | null;
  locked_at: string | null;
  error: string | null;
  payload: Record<string, unknown>;
  progress: RagEvalProgressPayload | null;
  percent?: number;
  progress_kind?: string;
  project_id?: unknown;
  document_id?: unknown;
  requested_by?: unknown;
  retrieval_limit?: unknown;
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

export const RAG_EVAL_PROPOSED_ACTION_TYPES = [
  'attach_question_to_entry',
  'create_entry_from_failure',
  'rebuild_embedding',
  'rerun_eval',
] as const;

export type RagEvalProposedActionType = (typeof RAG_EVAL_PROPOSED_ACTION_TYPES)[number];

const RAG_EVAL_PROPOSED_ACTION_TYPE_VALUES = new Set<string>(RAG_EVAL_PROPOSED_ACTION_TYPES);

export const isRagEvalProposedActionType = (value: string): value is RagEvalProposedActionType => (
  RAG_EVAL_PROPOSED_ACTION_TYPE_VALUES.has(value)
);

export interface RagEvalProposedActionSummary {
  action_type: RagEvalProposedActionType;
  target_entry_id: string | null;
  reason: string;
  payload: Record<string, unknown>;
}

export interface RagEvalActionableResult {
  result_id: string;
  run_id: string;
  question_id: string;
  question: string;
  question_type: string;
  expected_entry_ids: string[];
  retrieved_entry_ids: string[];
  score: number;
  answer_supported: boolean;
  wrong_entry_top1: boolean;
  hallucination_risk: string;
  should_answer_passed: boolean;
  classification: Record<string, unknown> | null;
  proposed_actions: RagEvalProposedActionSummary[];
}

export interface KnowledgeEditActionExecutionSummary {
  ok: boolean;
  source_result_id: string;
  project_id: string;
  document_id: string;
  total_actions: number;
  applied_actions: number;
  rejected_actions: number;
  failed_actions: number;
  skipped_actions: number;
  queued_rerun_job_ids: string[];
}

interface RunDocumentEvalOptions {
  mode?: 'quick' | 'standard' | 'deep' | 'paranoid' | 'retrieval_eval' | 'answer_quality_eval';
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

  async executeResultActions(resultId: string): Promise<KnowledgeEditActionExecutionSummary> {
    return unwrap(
      authedJsonRequest<KnowledgeEditActionExecutionSummary>(
        `/api/rag-eval/results/${encode(resultId)}/actions/execute`,
        { method: 'POST' },
      ),
    );
  },

  async runFullDocumentEval(documentId: string): Promise<RagEvalFullRunAcceptedResponse> {
    return unwrap(
      authedJsonRequest<RagEvalFullRunAcceptedResponse>(
        `/api/rag-eval/documents/${encode(documentId)}/run-full`,
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

    const suffix = query.toString() ? `?${query.toString()}` : '';

    return unwrap(
      authedJsonRequest<RagEvalRunAcceptedResponse>(
        `/api/rag-eval/documents/${encode(documentId)}/run${suffix}`,
        { method: 'POST' },
      ),
    );
  },
};
