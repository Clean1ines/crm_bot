import React from 'react';
import { Clock3 } from 'lucide-react';

import { useWorkflowTimerText } from './useWorkflowTimerText';
import type { WorkflowTimerInput } from './workflowTimerTypes';

type WorkflowTimerCardProps = {
  timer: WorkflowTimerInput;
};

export const WorkflowTimerCard: React.FC<WorkflowTimerCardProps> = ({ timer }) => {
  const elapsedText = useWorkflowTimerText(timer);

  return (
    <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
      <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
        <Clock3 className="h-3.5 w-3.5" />
        Активная обработка
      </div>
      <div className="text-[var(--text-muted)]">{elapsedText}</div>
    </div>
  );
};
