import { authedJsonRequest } from '@shared/api/core/http';

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

export type WorkbenchRagEvalPromotionBatchApplyRequest =
  | {
      mode: 'selected';
      promotion_ids: string[];
    }
  | {
      mode: 'all_candidates_for_run';
      run_id: string;
    };

export type WorkbenchRagEvalPromotionBatchApplyResult = {
  requested_count: number;
  applied_count: number;
  skipped_count: number;
  embedding_recalculation_count: number;
  errors: string[];
};

export type WorkbenchRagEvalPromotionBatchApplyResponse = {
  result: WorkbenchRagEvalPromotionBatchApplyResult;
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
