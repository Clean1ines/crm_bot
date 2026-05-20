import type { RagEvalJob } from '@shared/api/modules/ragEval';

const ACTIVE_JOB_STATUSES = new Set(['pending', 'processing', 'running', 'retrying', 'running_or_locked']);
const PAUSED_STATUSES = new Set(['paused', 'manual_pause', 'manual-pause']);
const TERMINAL_JOB_STATUSES = new Set(['completed', 'done', 'succeeded', 'success', 'failed', 'cancelled']);

type RagEvalJobWithEffectiveStatus = RagEvalJob & { effective_status?: string };

export const getJobStatus = (job: RagEvalJob | null | undefined): string => {
  const jobWithEffectiveStatus = job as RagEvalJobWithEffectiveStatus | null | undefined;
  return String(jobWithEffectiveStatus?.effective_status || jobWithEffectiveStatus?.status || '');
};

export const isJobTerminal = (job: RagEvalJob | null | undefined): boolean => (
  Boolean(job && TERMINAL_JOB_STATUSES.has(getJobStatus(job)))
);

export const isJobActive = (job: RagEvalJob | null | undefined): boolean => (
  Boolean(job && !isJobTerminal(job) && ACTIVE_JOB_STATUSES.has(getJobStatus(job)))
);

export const isJobPaused = (job: RagEvalJob | null | undefined): boolean => (
  Boolean(job && !isJobTerminal(job) && PAUSED_STATUSES.has(getJobStatus(job)))
);
