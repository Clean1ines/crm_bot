import React from 'react';

import type { SourceIngestionProgressView } from './sourceIngestionTypes';

type SourceIngestionProgressPanelProps = {
  progress: SourceIngestionProgressView;
  formatNumber: (value: number) => string;
};

export const SourceIngestionProgressPanel: React.FC<SourceIngestionProgressPanelProps> = ({
  progress,
  formatNumber,
}) => {
  if (!progress.visible) return null;

  return (
    <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
      <div className="mb-1 font-medium text-[var(--text-primary)]">Прогресс</div>
      <div className="text-[var(--text-muted)]">
        Извлечение утверждений: {progress.text}
        {progress.leasedCount > 0
          ? ` · сейчас обрабатывается ${formatNumber(progress.leasedCount)}`
          : ''}
        {progress.readyCount > 0 ? ` · ожидает ${formatNumber(progress.readyCount)}` : ''}
        {progress.waitingCount > 0
          ? ` · отложено ${formatNumber(progress.waitingCount)}`
          : ''}
        {progress.failedCount > 0 ? ` · ошибок ${formatNumber(progress.failedCount)}` : ''}
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--control-bg)]">
        <div
          className="h-full rounded-full bg-[var(--accent-primary)]"
          style={{ width: `${progress.percent}%` }}
        />
      </div>
      <div className="mt-1 text-[var(--text-muted)]">{progress.percent}%</div>
    </div>
  );
};
