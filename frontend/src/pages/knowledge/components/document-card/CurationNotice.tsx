import React from 'react';

type CurationNoticeProps = {
  available: boolean;
  workflowRunId?: string | null;
};

export const CurationNotice: React.FC<CurationNoticeProps> = ({
  available,
  workflowRunId,
}) => {
  if (!available || !workflowRunId) return null;

  return (
    <div className="rounded-lg bg-[var(--accent-primary)]/10 px-2 py-1 text-[var(--accent-primary)]">
      Проверка человеком доступна.
    </div>
  );
};
