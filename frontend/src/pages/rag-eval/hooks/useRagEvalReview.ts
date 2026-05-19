import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ragEvalApi } from '@shared/api/modules/ragEval';
import { isJobActive, isJobPaused } from '../lib/ragEvalStatus';

const ACTIVE_RUN_STATUSES = new Set(['created', 'pending', 'processing', 'generating', 'ready', 'running', 'paused']);

export const useRagEvalReview = (activeDocumentId: string, statusRun?: Record<string, unknown>) => {
  const reviewQuery = useQuery({
    queryKey: ['rag-eval-latest-review', activeDocumentId],
    queryFn: async () => ragEvalApi.getLatestReview(activeDocumentId),
    enabled: !!activeDocumentId,
    retry: false,
    refetchInterval: (query) => {
      const latestReview = query.state.data?.review;
      const reviewRun = latestReview?.run as Record<string, unknown> | undefined;
      const status = String(reviewRun?.status || statusRun?.status || '');
      return ACTIVE_RUN_STATUSES.has(status) ? 3000 : false;
    },
  });
  return { reviewQuery };
};

export const useRagEvalJobs = (activeDocumentId: string, lastQueuedJobId?: string) => {
  const jobsQuery = useQuery({
    queryKey: ['rag-eval-jobs', activeDocumentId],
    queryFn: async () => ragEvalApi.listJobs(activeDocumentId),
    enabled: !!activeDocumentId,
    retry: false,
    refetchInterval: (query) => {
      const jobs = query.state.data?.jobs ?? [];
      return jobs.some((job) => isJobActive(job) || isJobPaused(job)) ? 3000 : false;
    },
  });

  const visibleJob = useMemo(() => {
    const jobs = jobsQuery.data?.jobs ?? [];
    const active = jobs.find((job) => isJobActive(job));
    if (active) return active;
    const paused = jobs.find((job) => isJobPaused(job));
    if (paused) return paused;
    if (lastQueuedJobId) {
      const queued = jobs.find((job) => job.id === lastQueuedJobId);
      if (queued) return queued;
    }
    return jobs[0] ?? null;
  }, [jobsQuery.data?.jobs, lastQueuedJobId]);

  const progressQuery = useQuery({
    queryKey: ['rag-eval-job-progress', visibleJob?.id],
    queryFn: async () => ragEvalApi.getJobProgress(String(visibleJob?.id)),
    enabled: !!visibleJob?.id,
    retry: false,
    refetchInterval: (query) => {
      const job = query.state.data?.job;
      return isJobActive(job) || isJobPaused(job) ? 3000 : false;
    },
  });

  return { jobsQuery, visibleJob, progressQuery };
};
