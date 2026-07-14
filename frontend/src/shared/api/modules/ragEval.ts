import { authedJsonRequest } from '@shared/api/core/http';

export type WorkbenchRagEvalRunStatus =
  | 'created'
  | 'running'
  | 'promotion_review'
  | 'verifying'
  | 'completed'
  | 'blocked'
  | 'failed'
  | string;

export type WorkbenchRagEvalRetrievalClassificationCounts = {
  pass_strong: number;
  pass_weak: number;
  confusion: number;
  miss: number;
  existing_alias_retrieval_failure: number;
};

export type WorkbenchRagEvalRetrievalProgress = {
  completed: number;
  total: number;
  classification_counts?: WorkbenchRagEvalRetrievalClassificationCounts | null;
};

export type WorkbenchRagEvalRunSummary = {
  run_id: string;
  project_id: string;
  publication_id?: string | null;
  source_document_ref?: string | null;
  status: WorkbenchRagEvalRunStatus;
  current_phase?: string | null;
  retrieval_progress?: WorkbenchRagEvalRetrievalProgress | null;
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
  allow_degraded_llama_instant?: boolean;
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
  generation_account_ref?: string | null;
  generation_slot_index?: number | null;
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

export type WorkbenchRagEvalEmbeddingRevisionStatus =
  | 'pending_verification'
  | 'accepted'
  | 'regression_failed'
  | 'rolled_back';

export type WorkbenchRagEvalPromotionRevisionResult = {
  revision_id: string;
  runtime_entry_id: string;
  source_rag_eval_run_id: string;
  status: WorkbenchRagEvalEmbeddingRevisionStatus;
  promotion_ids: string[];
  idempotent: boolean;
};

export type WorkbenchRagEvalPromotionApplicationError = {
  code: string;
  message: string;
  promotion_ids: string[];
  runtime_entry_id: string | null;
};

export type WorkbenchRagEvalPromotionApplicationResult = {
  requested_count: number;
  applied_count: number;
  skipped_count: number;
  embedding_recalculation_count: number;
  revisions: WorkbenchRagEvalPromotionRevisionResult[];
  errors: WorkbenchRagEvalPromotionApplicationError[];
};

export type WorkbenchRagEvalPromotionApplyResponse =
  WorkbenchRagEvalPromotionApplicationResult & {
    result: WorkbenchRagEvalPromotionApplicationResult;
  };

export type WorkbenchRagEvalPromotionBatchApplyRequest =
  | {
      mode: 'selected';
      promotion_ids: string[];
    }
  | {
      mode: 'all_candidates_for_run';
      run_id: string;
    };

export type WorkbenchRagEvalPromotionBatchApplyResponse =
  WorkbenchRagEvalPromotionApplicationResult & {
    result: WorkbenchRagEvalPromotionApplicationResult;
  };

export type WorkbenchRagEvalEmbeddingRevision = {
  revision_id: string;
  project_id: string;
  runtime_entry_id: string;
  source_rag_eval_run_id: string;
  promotion_ids: string[];
  status: WorkbenchRagEvalEmbeddingRevisionStatus;
  previous_promoted_questions: string[];
  new_promoted_questions: string[];
  created_at: string;
  accepted_at: string | null;
  regression_failed_at: string | null;
  rolled_back_at: string | null;
  available_actions: {
    can_accept: boolean;
    can_rollback: boolean;
  };
};

export type WorkbenchRagEvalEmbeddingRevisionsResponse = {
  revisions: WorkbenchRagEvalEmbeddingRevision[];
};

export type WorkbenchRagEvalEmbeddingRevisionResponse = {
  revision: WorkbenchRagEvalEmbeddingRevision;
};

export type WorkbenchRagEvalVerificationRoleMetrics = {
  query_count: number;
  top1_hits: number;
  top3_hits: number;
  top5_hits: number;
  top1_rate: number;
  top3_rate: number;
  top5_rate: number;
  mean_expected_rank: number;
  mean_expected_score: number;
  mean_score_margin: number;
  miss_count: number;
  confusion_count: number;
  existing_alias_failure_count: number;
  strong_pass_count: number;
  weak_pass_count: number;
  before_top1_hits: number;
  before_top3_hits: number;
  before_top5_hits: number;
  before_top1_rate: number;
  before_top3_rate: number;
  before_top5_rate: number;
  before_mean_expected_rank: number;
  before_mean_score_margin: number;
  top1_rate_delta: number;
  top3_rate_delta: number;
  top5_rate_delta: number;
  mean_expected_rank_delta: number;
  mean_score_margin_delta: number;
  promoted_top3_improvement_count: number;
  promoted_top3_regression_count: number;
  promoted_mean_margin_delta: number;
  holdout_top3_recall_before: number;
  holdout_top3_recall_after: number;
  holdout_top3_recall_delta: number;
  holdout_mean_margin_delta: number;
  baseline_top3_recall_before: number;
  baseline_top3_recall_after: number;
  baseline_top3_recall_delta: number;
  baseline_regression_count: number;
  neighbor_query_count: number;
  neighbor_top1_regression_count: number;
  neighbor_top3_regression_count: number;
  neighbor_mean_margin_delta: number;
};

export type WorkbenchRagEvalVerificationMetrics = {
  overall: WorkbenchRagEvalVerificationRoleMetrics;
  promoted: WorkbenchRagEvalVerificationRoleMetrics;
  holdout: WorkbenchRagEvalVerificationRoleMetrics;
  baseline: WorkbenchRagEvalVerificationRoleMetrics;
  neighbour: WorkbenchRagEvalVerificationRoleMetrics;
};

export type WorkbenchRagEvalVerification = {
  verification_id: string;
  revision_id: string;
  project_id: string;
  source_rag_eval_run_id: string;
  runtime_entry_id: string;
  status: string;
  policy_version: string;
  decision: string | null;
  failure_reasons: string[];
  metrics: WorkbenchRagEvalVerificationMetrics | null;
  query_count: number;
  outcome_count: number;
  created_at: string;
  completed_at: string | null;
  failed_at: string | null;
  error_message: string | null;
};

export type WorkbenchRagEvalVerificationsResponse = {
  verifications: WorkbenchRagEvalVerification[];
};

export type WorkbenchRagEvalVerificationResponse = {
  verification: WorkbenchRagEvalVerification;
};

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

  async listWorkbenchEmbeddingRevisions(
    projectId: string,
    runId: string,
  ): Promise<WorkbenchRagEvalEmbeddingRevisionsResponse> {
    return unwrap(
      authedJsonRequest<WorkbenchRagEvalEmbeddingRevisionsResponse>(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/runs/${encode(runId)}/embedding-revisions`,
        { method: 'GET' },
      ),
    );
  },

  async listWorkbenchPostPromotionVerifications(
    projectId: string,
    runId: string,
  ): Promise<WorkbenchRagEvalVerificationsResponse> {
    return unwrap(
      authedJsonRequest<WorkbenchRagEvalVerificationsResponse>(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/runs/${encode(runId)}/post-promotion-verifications`,
        { method: 'GET' },
      ),
    );
  },

  async getWorkbenchPostPromotionVerification(
    projectId: string,
    revisionId: string,
  ): Promise<WorkbenchRagEvalVerificationResponse> {
    return unwrap(
      authedJsonRequest<WorkbenchRagEvalVerificationResponse>(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/embedding-revisions/${encode(revisionId)}/verification`,
        { method: 'GET' },
      ),
    );
  },

  async acceptWorkbenchEmbeddingRevision(
    projectId: string,
    revisionId: string,
  ): Promise<WorkbenchRagEvalEmbeddingRevisionResponse> {
    return unwrap(
      authedJsonRequest<WorkbenchRagEvalEmbeddingRevisionResponse>(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/embedding-revisions/${encode(revisionId)}/accept`,
        { method: 'POST' },
      ),
    );
  },

  async rollbackWorkbenchEmbeddingRevision(
    projectId: string,
    revisionId: string,
  ): Promise<WorkbenchRagEvalEmbeddingRevisionResponse> {
    return unwrap(
      authedJsonRequest<WorkbenchRagEvalEmbeddingRevisionResponse>(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/embedding-revisions/${encode(revisionId)}/rollback`,
        { method: 'POST' },
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

  async applyWorkbenchPromotionCandidatesBatch(
    projectId: string,
    payload: WorkbenchRagEvalPromotionBatchApplyRequest,
  ): Promise<WorkbenchRagEvalPromotionBatchApplyResponse> {
    return unwrap(
      authedJsonRequest<
        WorkbenchRagEvalPromotionBatchApplyResponse,
        WorkbenchRagEvalPromotionBatchApplyRequest
      >(
        `/api/projects/${encode(projectId)}/knowledge/rag-eval/workbench/promotion-candidates/apply-batch`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    );
  },
};
