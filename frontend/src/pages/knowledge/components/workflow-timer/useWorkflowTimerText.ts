import { useEffect, useMemo, useState } from 'react';

import type { WorkflowTimerInput } from './workflowTimerTypes';

const normalize = (value: string | null | undefined): string =>
  (value || '').trim().toLowerCase();

const safeSeconds = (value: number | null | undefined): number => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.floor(value));
};

const formatDuration = (seconds: number): string => {
  const value = safeSeconds(seconds);
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const restSeconds = value % 60;

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${restSeconds
      .toString()
      .padStart(2, '0')}`;
  }

  return `${minutes}:${restSeconds.toString().padStart(2, '0')}`;
};

const isActiveWorkflowStatus = (workflowStatus: string | null | undefined): boolean =>
  ['running', 'active', 'processing'].includes(normalize(workflowStatus));

const isStoppedWorkflowStatus = (workflowStatus: string | null | undefined): boolean =>
  [
    'paused',
    'pause',
    'manual_paused',
    'paused_manual',
    'waiting_for_review',
    'completed',
    'done',
    'published',
    'failed',
    'cancelled',
    'canceled',
    'stopped',
  ].includes(normalize(workflowStatus));

const isActiveTimerMode = (mode: string | null | undefined): boolean =>
  ['running', 'active', 'processing'].includes(normalize(mode));

const isStoppedTimerMode = (mode: string | null | undefined): boolean =>
  ['paused', 'completed', 'done', 'published', 'failed', 'cancelled', 'canceled', 'stopped'].includes(
    normalize(mode),
  );

const shouldTick = (
  timer: WorkflowTimerInput,
  workflowStatus: string | null | undefined,
): boolean => {
  if (!timer) return false;
  if (isStoppedWorkflowStatus(workflowStatus)) return false;
  if (isStoppedTimerMode(timer.mode)) return false;
  if (!isActiveWorkflowStatus(workflowStatus)) return false;
  if (!isActiveTimerMode(timer.mode)) return false;
  return Boolean(timer.is_live);
};

const timerBaseKey = (
  timer: WorkflowTimerInput,
  workflowStatus: string | null | undefined,
): string =>
  [
    workflowStatus ?? '',
    timer?.mode ?? '',
    timer?.is_live ? 'live' : 'still',
    timer?.active_elapsed_seconds ?? 0,
    timer?.wall_elapsed_seconds ?? 0,
    timer?.current_active_started_at ?? '',
    timer?.started_at ?? '',
    timer?.completed_at ?? '',
  ].join('|');

export const useWorkflowTimerText = (
  timer: WorkflowTimerInput,
  workflowStatus?: string | null,
): string => {
  const baseElapsedSeconds = safeSeconds(timer?.active_elapsed_seconds);
  const isTicking = shouldTick(timer, workflowStatus ?? null);
  const baseKey = timerBaseKey(timer, workflowStatus ?? null);

  const [baseObservedAtMs, setBaseObservedAtMs] = useState(() => Date.now());
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const now = Date.now();
    setBaseObservedAtMs(now);
    setNowMs(now);
  }, [baseKey]);

  useEffect(() => {
    if (!isTicking) return undefined;

    setNowMs(Date.now());
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [isTicking, baseKey]);

  const elapsedSeconds = useMemo(() => {
    if (!isTicking) return baseElapsedSeconds;
    return baseElapsedSeconds + Math.max(0, Math.floor((nowMs - baseObservedAtMs) / 1000));
  }, [baseElapsedSeconds, baseObservedAtMs, isTicking, nowMs]);

  if (elapsedSeconds > 0 || isTicking) return formatDuration(elapsedSeconds);
  return '—';
};
