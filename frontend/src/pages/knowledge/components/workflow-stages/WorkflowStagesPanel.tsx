import React from 'react';

import type { WorkflowStageRowView } from './workflowStagesTypes';

type WorkflowStagesPanelProps = {
  rows: WorkflowStageRowView[];
  formatNumber: (value: number) => string;
};

export const WorkflowStagesPanel: React.FC<WorkflowStagesPanelProps> = ({
  rows,
  formatNumber,
}) => {
  if (rows.length === 0) return null;

  return (
    <section>
      <div className="mb-2 font-medium text-[var(--text-primary)]">
        Этапы обработки
      </div>
      <div className="space-y-1.5">
        {rows.map((stage, stageIndex) => (
          <details
            key={stage.id}
            className={`rounded-lg border px-3 py-2 ${stage.toneClassName}`}
          >
            <summary className="cursor-pointer list-none">
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="min-w-0">
                  <span className="font-semibold text-[var(--text-primary)]">
                    {formatNumber(stageIndex + 1)}. {stage.title}
                  </span>
                  <span className="ml-2 text-[var(--text-muted)]">
                    {stage.statusLabel}
                    {stage.showCounts
                      ? ` · ${formatNumber(stage.current)} / ${formatNumber(stage.total)}`
                      : ''}
                  </span>
                </span>
                <span className={`rounded-full px-2.5 py-1 font-medium ${stage.pillClassName}`}>
                  {stage.statusLabel}
                </span>
              </span>
            </summary>
            {stage.message && (
              <div className="mt-2 text-[var(--text-secondary)]">
                {stage.message}
              </div>
            )}
          </details>
        ))}
      </div>
    </section>
  );
};
