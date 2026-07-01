import { useEffect, useMemo, useState } from 'react';

import type { WorkflowTimerInput } from './workflowTimerTypes';

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

const timerBaseKey = (timer: WorkflowTimerInput): string =>
  [
    timer?.mode ?? '',
    timer?.is_live ? 'live' : 'still',
    timer?.active_elapsed_seconds ?? 0,
    timer?.current_active_started_at ?? '',
    timer?.started_at ?? '',
    timer?.completed_at ?? '',
  ].join('|');

export const useWorkflowTimerText = (timer: WorkflowTimerInput): string => {
  const isLive = Boolean(timer?.is_live && timer?.current_active_started_at);
  const baseElapsedSeconds = safeSeconds(timer?.active_elapsed_seconds);
  const baseKey = timerBaseKey(timer);
  const [baseObservedAtMs, setBaseObservedAtMs] = useState(() => Date.now());
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const now = Date.now();
    setBaseObservedAtMs(now);
    setNowMs(now);
  }, [baseKey]);

  useEffect(() => {
    if (!isLive) return undefined;

    setNowMs(Date.now());
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [isLive, baseKey]);

  const elapsedSeconds = useMemo(() => {
    if (!isLive) return baseElapsedSeconds;

    return baseElapsedSeconds + Math.max(0, Math.floor((nowMs - baseObservedAtMs) / 1000));
  }, [baseElapsedSeconds, baseObservedAtMs, isLive, nowMs]);

  if (elapsedSeconds > 0 || isLive) return formatDuration(elapsedSeconds);
  return '—';
};
