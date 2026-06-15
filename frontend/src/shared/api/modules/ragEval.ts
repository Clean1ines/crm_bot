import { authedJsonRequest } from '@shared/api/core/http';

export type RagEvalRetrievalMode = 'production_equivalent' | 'vector_debug';

export type WorkbenchRagEvalRunStatus = 'created' | 'running' | 'completed' | 'failed' | string;

export type WorkbenchRagEvalRunSummary = {
  run_id: string;
  project_id: string;
  publication_id?: string | null;
  source_document_ref?: string | null;
  status: WorkbenchRagEvalRunStatus;
  question_generation_model?: string | null;
  question_generation_prompt_version?: string | null;
  total_entries: number;
  total_questions: number;
  completed_questions: number;
  top1_hits: number;
  top3_hits: number;
  top5_hits: number;
  misses: number;
  promotion_candidate_count?: number;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
};

export type RunWorkbenchRagEvalRequest = {
  publication_id?: string | null;
  source_document_ref?: string | null;
  top_k: number;
  max_entries: number;
};

export type WorkbenchRagEvalRunResponse = {
  run: WorkbenchRagEvalRunSummary;
};

export type WorkbenchRagEvalLatestResponse = {
  run: WorkbenchRagEvalRunSummary | null;
};

export type WorkbenchRagEvalRetrievalResultDetails = {
  result_id: string;
  matched_runtime_entry_id: string;
  matched_fact_id: string;
  rank: number;
  score: number;
  top1_hit: boolean;
  top3_hit: boolean;
  top5_hit: boolean;
  created_at: string;
};

export type WorkbenchRagEvalQuestionDetails = {
  question_id: string;
  run_id: string;
  project_id: string;
  expected_runtime_entry_id: string;
  expected_fact_id: string;
  question: string;
  question_kind: string;
  source: string;
  generation_model?: string | null;
  prompt_version?: string | null;
  status: string;
  created_at: string;
  results: WorkbenchRagEvalRetrievalResultDetails[];
};

export type WorkbenchRagEvalPromotionCandidateDetails = {
  promotion_id: string;
  run_id: string;
  question_id: string;
  project_id: string;
  target_runtime_entry_id: string;
  target_fact_id: string;
  question: string;
  status: string;
  created_at: string;
  applied_at?: string | null;
};

export type WorkbenchRagEvalQuestionsResponse = {
  questions: WorkbenchRagEvalQuestionDetails[];
};

export type WorkbenchRagEvalPromotionCandidatesResponse = {
  candidates: WorkbenchRagEvalPromotionCandidateDetails[];
};

export type WorkbenchRagEvalPromotionApplyResult = {
  promotion_id: string;
  run_id: string;
  question_id: string;
  project_id: string;
  target_runtime_entry_id: string;
  target_fact_id: string;
  question: string;
  status: string;
  possible_question_count: number;
  embedding_model_id: string;
  embedding_count: number;
  applied_at: string;
};

export type WorkbenchRagEvalPromotionApplyResponse = {
  result: WorkbenchRagEvalPromotionApplyResult;
};

export interface RagEvalFullRunAcceptedResponse {
  ok: boolean;
  queued: boolean;
  job_id: string;
  document: Record<string, unknown>;
  mode: string;
  retrieval_mode: RagEvalRetrievalMode;
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
  entries_total?: number;
  entries_processed?: number;
  entries_queued?: number;
  entries_generating?: number;
  entries_checking?: number;
  entries_ready_for_review?: number;
  entries_failed?: number;
  fragments_ready_for_review?: number;
  active_generation_workers?: number;
  active_retrieval_workers?: number;
  generated_questions?: number;
  processed_questions?: number;
  queued_questions?: number;
  total_questions?: number;
  failed_retrieval_count?: number;
  actionable_improvements_count?: number;
  questions_per_minute?: number;
  entries_per_minute?: number;
  last_update_seconds_ago?: number;
  question_model?: string;
  fallback_used_count?: number;
  source_chunk_count?: number;
  processed_batches?: number;
  total_batches?: number;
  successful_batches?: number;
  failed_batches?: number;
  skipped_batches?: number;
  json_parse_failures?: number;
  provider_failures?: number;
  retry_count?: number;
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
  retrieval_mode?: RagEvalRetrievalMode;
  retrieval_path?: string;
  query_expansion_enabled?: boolean;
  runtime_equivalent?: boolean;
  diagnostic?: boolean;
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
  retrieval_mode?: unknown;
  retrieval_path?: unknown;
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


export type RagEvalQuestionReviewStatus = 'candidate' | 'accepted' | 'rejected' | 'edited' | 'applied';

export interface RagEvalQuestionReviewState {
  id?: string;
  question_id?: string;
  status: RagEvalQuestionReviewStatus;
  original_question?: string;
  edited_question?: string;
  review_reason?: string;
  reviewed_by?: string;
  reviewed_at?: string | null;
}

export interface RagEvalReviewRetrievedEntry {
  id: string;
  title: string;
  content: string;
}

export interface RagEvalReviewQuestion {
  result_id: string;
  question_id: string;
  question: string;
  effective_question: string;
  question_type: string;
  question_type_label: string;
  retrieval_status: 'reliable' | 'weak' | 'confused' | 'missing';
  retrieval_status_label: string;
  expected_entry_ids: string[];
  retrieved_entry_ids: string[];
  retrieved_entries: RagEvalReviewRetrievedEntry[];
  score: number;
  top1_hit: boolean;
  top3_hit: boolean;
  top5_hit: boolean;
  expected_entry_found: boolean;
  wrong_entry_top1: boolean;
  fallback_generated: boolean;
  review: RagEvalQuestionReviewState;
  why_it_matters: string;
  proposed_improvements: string[];
  diagnostics: Record<string, unknown>;
}

export interface RagEvalReviewGroup {
  entry_id: string;
  title: string;
  content: string;
  existing_questions: string[];
  question_count: number;
  problem_count: number;
  improvement_count: number;
  status: string;
  review_status?: 'queued' | 'generating_questions' | 'checking_retrieval' | 'ready_for_review' | 'failed';
  error?: string;
  issue_summary: string;
  questions: RagEvalReviewQuestion[];
  proposed_improvements: string[];
}

export interface RagEvalReviewSummary {
  title: string;
  score: number;
  readiness: string;
  fragments_total: number;
  questions_total: number;
  reliable_questions: number;
  weak_questions: number;
  confused_questions: number;
  missing_questions: number;
  problem_questions: number;
  improvements_total: number;
  good_fragments: number;
  unstable_fragments: number;
  bad_fragments: number;
  human_summary: string;
}

export interface RagEvalProblemTypeSummary {
  type: string;
  label: string;
  count: number;
}

export interface RagEvalReviewPayload {
  run: Record<string, unknown>;
  summary: RagEvalReviewSummary;
  problem_map: {
    most_problematic_fragments: RagEvalReviewGroup[];
    best_fragments: RagEvalReviewGroup[];
    problem_types: RagEvalProblemTypeSummary[];
  };
  groups: RagEvalReviewGroup[];
  filters: Record<string, unknown>;
  diagnostics: Record<string, unknown>;
}

export interface RagEvalLatestReviewResponse {
  ok: boolean;
  document: Record<string, unknown>;
  review: RagEvalReviewPayload | null;
}

export interface RagEvalRunReviewResponse {
  ok: boolean;
  review: RagEvalReviewPayload | null;
}

export interface RagEvalQuestionReviewResponse {
  ok: boolean;
  review: RagEvalQuestionReviewState;
}

export interface RagEvalApplyAcceptedResponse {
  ok: boolean;
  run_id: string;
  applied_questions: number;
  failed_questions: number;
  queued_rerun_job_id: string | null;
  failures?: Array<Record<string, unknown>>;
}

interface RunDocumentEvalOptions {
  mode?: 'quick' | 'standard' | 'deep' | 'paranoid' | 'retrieval_eval' | 'answer_quality_eval';
  retrieval_mode?: RagEvalRetrievalMode;
}

const encode = (value: string): string => encodeURIComponent(value);

const unwrap = async <T>(promise: Promise<{ data: T }>): Promise<T> => {
  const response = await promise;
  return response.data;
};

export const ragEvalApi = {

  async runWorkbench(
    projectId: string,
    payload: RunWorkbenchRagEvalRequest,
  ): Promise<WorkbenchRagEvalRunResponse> {
    return unwrap(
      authedJsonRequest<WorkbenchRagEvalRunResponse, RunWorkbenchRagEvalRequest>(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/run`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    );
  },

  async latestWorkbench(projectId: string): Promise<WorkbenchRagEvalLatestResponse> {
    return unwrap(
      authedJsonRequest<WorkbenchRagEvalLatestResponse>(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/latest`,
        { method: 'GET' },
      ),
    );
  },

  async getWorkbenchRun(
    projectId: string,
    runId: string,
  ): Promise<WorkbenchRagEvalLatestResponse> {
    return unwrap(
      authedJsonRequest<WorkbenchRagEvalLatestResponse>(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/runs/${encode(runId)}`,
        { method: 'GET' },
      ),
    );
  },

  async listWorkbenchQuestions(
    projectId: string,
    runId: string,
  ): Promise<WorkbenchRagEvalQuestionsResponse> {
    return unwrap(
      authedJsonRequest<WorkbenchRagEvalQuestionsResponse>(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/runs/${encode(runId)}/questions`,
        { method: 'GET' },
      ),
    );
  },

  async listWorkbenchPromotionCandidates(
    projectId: string,
    runId: string,
  ): Promise<WorkbenchRagEvalPromotionCandidatesResponse> {
    return unwrap(
      authedJsonRequest<WorkbenchRagEvalPromotionCandidatesResponse>(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/runs/${encode(runId)}/promotion-candidates`,
        { method: 'GET' },
      ),
    );
  },

  async applyWorkbenchPromotionCandidate(
    projectId: string,
    promotionId: string,
  ): Promise<WorkbenchRagEvalPromotionApplyResponse> {
    return unwrap(
      authedJsonRequest<WorkbenchRagEvalPromotionApplyResponse>(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/promotion-candidates/${encode(promotionId)}/apply`,
        { method: 'POST' },
      ),
    );
  },

  async getLatestReview(documentId: string): Promise<RagEvalLatestReviewResponse> {
    return unwrap(
      authedJsonRequest<RagEvalLatestReviewResponse>(
        `/api/rag-eval/documents/${encode(documentId)}/latest-review`,
        { method: 'GET' },
      ),
    );
  },

  async getRunReview(runId: string): Promise<RagEvalRunReviewResponse> {
    return unwrap(
      authedJsonRequest<RagEvalRunReviewResponse>(
        `/api/rag-eval/runs/${encode(runId)}/review`,
        { method: 'GET' },
      ),
    );
  },

  async reviewQuestion(questionId: string, status: 'accepted' | 'rejected', reason = ''): Promise<RagEvalQuestionReviewResponse> {
    return unwrap(
      authedJsonRequest<RagEvalQuestionReviewResponse>(
        `/api/rag-eval/questions/${encode(questionId)}/review`,
        {
          method: 'POST',
          body: { status, reason },
        },
      ),
    );
  },

  async editQuestion(questionId: string, question: string): Promise<RagEvalQuestionReviewResponse> {
    return unwrap(
      authedJsonRequest<RagEvalQuestionReviewResponse>(
        `/api/rag-eval/questions/${encode(questionId)}`,
        {
          method: 'PATCH',
          body: { question },
        },
      ),
    );
  },

  async applyAcceptedQuestions(runId: string): Promise<RagEvalApplyAcceptedResponse> {
    return unwrap(
      authedJsonRequest<RagEvalApplyAcceptedResponse>(
        `/api/rag-eval/runs/${encode(runId)}/apply-accepted`,
        { method: 'POST' },
      ),
    );
  },
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

  async runFullDocumentEval(
    documentId: string,
    options: Pick<RunDocumentEvalOptions, 'retrieval_mode'> = {},
  ): Promise<RagEvalFullRunAcceptedResponse> {
    return unwrap(
      authedJsonRequest<RagEvalFullRunAcceptedResponse>(
        `/api/rag-eval/documents/${encode(documentId)}/run-full`,
        {
          method: 'POST',
          body: {
            retrieval_mode: options.retrieval_mode ?? 'production_equivalent',
          },
        },
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
    query.set('retrieval_mode', options.retrieval_mode ?? 'production_equivalent');

    const suffix = query.toString() ? `?${query.toString()}` : '';

    return unwrap(
      authedJsonRequest<RagEvalRunAcceptedResponse>(
        `/api/rag-eval/documents/${encode(documentId)}/run${suffix}`,
        { method: 'POST' },
      ),
    );
  },
};
