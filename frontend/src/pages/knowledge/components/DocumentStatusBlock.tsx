import React from 'react';

type DocumentMeta = {
  created_at: string;
};

type StatusBadge = {
  className: string;
  label: string;
};

export const DocumentStatusBlock: React.FC<{
  doc: DocumentMeta;
  statusBadge: StatusBadge;
  isCancelled: boolean;
  isFailed: boolean;
  issueText: string | null;
  processingFailedText: string;
  stoppedWarningText: string;
}> = ({
  doc,
  statusBadge,
  isCancelled,
  isFailed,
  issueText,
  processingFailedText,
  stoppedWarningText,
}) => (
  <>
    {isCancelled && (
      <div className="mb-4 rounded-xl bg-[var(--accent-warning-bg)] p-3 text-xs leading-relaxed text-[var(--accent-warning)]">
        {stoppedWarningText}
      </div>
    )}

    {isFailed && !isCancelled && (
      <div className="mb-4 rounded-xl bg-[var(--accent-danger-bg)] p-3 text-xs leading-relaxed text-[var(--accent-danger-text)]">
        {issueText || processingFailedText}
      </div>
    )}

    <div className="flex items-center justify-between">
      <span className={`inline-flex min-h-6 items-center rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide ${statusBadge.className}`}>
        {statusBadge.label}
      </span>
      <span className="text-[10px] text-[var(--text-muted)]">
        {new Date(doc.created_at).toLocaleDateString()}
      </span>
    </div>
  </>
);
