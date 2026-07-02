import React from 'react';

type ResultSummaryCardProps = {
  visible: boolean;
  summaryText: string;
};

export const ResultSummaryCard: React.FC<ResultSummaryCardProps> = ({
  visible,
  summaryText,
}) => {
  if (!visible) return null;

  return (
    <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
      <div className="mb-1 font-medium text-[var(--text-primary)]">Итог</div>
      <div className="text-[var(--text-muted)]">{summaryText}</div>
    </div>
  );
};
