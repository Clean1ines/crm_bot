import React from 'react';
import { Clock3 } from 'lucide-react';

import { useWorkflowTimerText } from './useWorkflowTimerText';
import type { WorkflowTimerInput } from './workflowTimerTypes';

type WorkflowTimerCardProps = {
  timer: WorkflowTimerInput;
  workflowStatus?: string | null;
};

export const WorkflowTimerCard: React.FC<WorkflowTimerCardProps> = ({
  timer,
  workflowStatus = null,
}) => {
  const elapsedText = useWorkflowTimerText(timer, workflowStatus);
  const normalizedStatus = (workflowStatus || '').trim().toLowerCase();
  const normalizedMode = (timer?.mode || '').trim().toLowerCase();
  const isStopped =
    [
      'paused',
      'waiting_for_review',
      'completed',
      'done',
      'published',
      'failed',
      'cancelled',
      'canceled',
      'stopped',
    ].includes(normalizedStatus) ||
    [
      'paused',
      'completed',
      'done',
      'published',
      'failed',
      'cancelled',
      'canceled',
      'stopped',
    ].includes(normalizedMode) ||
    timer?.is_live === false;
  const title = isStopped ? 'Время обработки' : 'Активная обработка';

  return (
    <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
      <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
        <Clock3 className="h-3.5 w-3.5" />
        {title}
      </div>
      <div className="text-[var(--text-muted)]">{elapsedText}</div>
    </div>
  );
};
