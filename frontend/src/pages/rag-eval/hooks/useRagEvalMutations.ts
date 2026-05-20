import { useMutation, type QueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { t } from '@shared/i18n';
import { getErrorMessage } from '@shared/api/core/errors';
import { ragEvalApi, type KnowledgeEditActionExecutionSummary, type RagEvalFullRunAcceptedResponse, type RagEvalJob, type RagEvalJobProgressResponse, type RagEvalJobsResponse } from '@shared/api/modules/ragEval';

export const useRagEvalMutations = ({ activeDocumentId, queryClient, setLastQueued, setLastActionExecutionSummary, invalidateEvalQueries }: {
  activeDocumentId: string;
  queryClient: QueryClient;
  setLastQueued: (value: RagEvalFullRunAcceptedResponse | null) => void;
  setLastActionExecutionSummary: (value: KnowledgeEditActionExecutionSummary | null) => void;
  invalidateEvalQueries: () => Promise<void>;
}) => {
  const applyJobMutationResult = (job: RagEvalJob) => {
    queryClient.setQueryData<RagEvalJobsResponse>(['rag-eval-jobs', activeDocumentId], (current) => {
      if (!current) return current;
      const exists = current.jobs.some((item) => item.id === job.id);
      const jobs = exists ? current.jobs.map((item) => (item.id === job.id ? job : item)) : [job, ...current.jobs];
      return { ...current, jobs };
    });
    queryClient.setQueryData<RagEvalJobProgressResponse>(['rag-eval-job-progress', job.id], { ok: true, job });
  };

  const runMutation = useMutation({ mutationFn: async () => { if (!activeDocumentId) throw new Error(t('ragEval.error.noProcessedDocument')); return ragEvalApi.runFullDocumentEval(activeDocumentId); }, onSuccess: async (result) => { setLastQueued(result); setLastActionExecutionSummary(null); toast.success(t('ragEval.feedback.started')); await invalidateEvalQueries(); }, onError: (e) => toast.error(getErrorMessage(e, t('ragEval.error.enqueueFailed'))) });
  const pauseMutation = useMutation({ mutationFn: async (jobId: string) => ragEvalApi.pauseJob(jobId), onSuccess: (result) => { applyJobMutationResult(result.job); toast.success(t('ragEval.feedback.paused')); void invalidateEvalQueries(); }, onError: (e) => toast.error(getErrorMessage(e, t('ragEval.error.pauseFailed'))) });
  const resumeMutation = useMutation({ mutationFn: async (jobId: string) => ragEvalApi.resumeJob(jobId), onSuccess: (result) => { applyJobMutationResult(result.job); toast.success(t('ragEval.feedback.resumed')); void invalidateEvalQueries(); }, onError: (e) => toast.error(getErrorMessage(e, t('ragEval.error.resumeFailed'))) });
  const cancelMutation = useMutation({ mutationFn: async (jobId: string) => ragEvalApi.cancelJob(jobId), onSuccess: (result) => { setLastQueued(null); applyJobMutationResult(result.job); toast.success(t('ragEval.feedback.cancelled')); void invalidateEvalQueries(); }, onError: (e) => toast.error(getErrorMessage(e, t('ragEval.error.cancelFailed'))) });
  const executeActionsMutation = useMutation<KnowledgeEditActionExecutionSummary, unknown, string>({ mutationFn: async (resultId: string) => ragEvalApi.executeResultActions(resultId), onSuccess: async (summary) => { setLastActionExecutionSummary(summary); const suffix = summary.queued_rerun_job_ids.length ? t('ragEval.feedback.rerunQueuedSuffix') : ''; toast.success(t('ragEval.feedback.actionsApplied', { applied: summary.applied_actions, rejected: summary.rejected_actions, failed: summary.failed_actions, suffix })); await invalidateEvalQueries(); }, onError: (e) => toast.error(getErrorMessage(e, t('ragEval.error.executeActionsFailed'))) });
  const reviewQuestionMutation = useMutation({ mutationFn: async ({ questionId, status }: { questionId: string; status: 'accepted' | 'rejected' }) => ragEvalApi.reviewQuestion(questionId, status), onSuccess: async () => { toast.success('Решение по вопросу сохранено'); await invalidateEvalQueries(); }, onError: (e) => toast.error(getErrorMessage(e, 'Не удалось сохранить решение по вопросу')) });
  const editQuestionMutation = useMutation({ mutationFn: async ({ questionId, question }: { questionId: string; question: string }) => ragEvalApi.editQuestion(questionId, question), onSuccess: async () => { toast.success('Формулировка сохранена'); await invalidateEvalQueries(); }, onError: (e) => toast.error(getErrorMessage(e, 'Не удалось отредактировать вопрос')) });
  const applyAcceptedMutation = useMutation({ mutationFn: async (runId: string) => ragEvalApi.applyAcceptedQuestions(runId), onSuccess: async (result) => { toast.success(`Применено вопросов: ${result.applied_questions}`); await invalidateEvalQueries(); }, onError: (e) => toast.error(getErrorMessage(e, 'Не удалось применить принятые вопросы')) });

  return { runMutation, pauseMutation, resumeMutation, cancelMutation, executeActionsMutation, reviewQuestionMutation, editQuestionMutation, applyAcceptedMutation };
};
