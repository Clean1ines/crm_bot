import React from 'react';

type DocumentOverviewPanelProps = {
  fileName: string;
  fileSizeText: string;
  processingModeText: string;
  headline: string;
  phaseText: string;
  failedSourceUnitCount: number;
  formatNumber: (value: number) => string;
};

export const DocumentOverviewPanel: React.FC<DocumentOverviewPanelProps> = ({
  fileName,
  fileSizeText,
  processingModeText,
  headline,
  phaseText,
  failedSourceUnitCount,
  formatNumber,
}) => (
  <div className="mb-3">
    <div className="flex min-w-0 items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <h3 className="truncate font-semibold text-[var(--text-primary)]" title={fileName}>
          {fileName}
        </h3>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          {fileSizeText} · {processingModeText}
        </p>
      </div>
    </div>

    <div className="mt-2 rounded-xl bg-[var(--surface-secondary)] px-3 py-2 text-sm leading-relaxed text-[var(--text-secondary)]">
      <div className="font-medium text-[var(--text-primary)]">Что происходит с документом</div>
      <p className="mt-1">
        {headline}. Сейчас: {phaseText}.
      </p>
      {failedSourceUnitCount > 0 && (
        <p className="mt-1 text-amber-700 dark:text-amber-300">
          {formatNumber(failedSourceUnitCount)} раздела требуют повторной обработки.
        </p>
      )}
    </div>
  </div>
);
