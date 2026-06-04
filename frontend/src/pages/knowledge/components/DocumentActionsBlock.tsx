import React from 'react';
import { StopCircle } from 'lucide-react';

import { t } from '@shared/i18n';

export const DocumentActionsBlock: React.FC<{
  showStop: boolean;
  cancelPending: boolean;
  onStop: () => void;
}> = ({
  showStop,
  cancelPending,
  onStop,
}) => {
  if (!showStop) return null;

  return (
    <div className="flex gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
      <button
        type="button"
        onClick={onStop}
        disabled={cancelPending}
        title={t('knowledge.actions.stopProcessing')}
        className="rounded-lg p-2 text-[var(--accent-danger-text)] transition-colors hover:bg-[var(--accent-danger-bg)] disabled:cursor-wait disabled:opacity-50"
      >
        <StopCircle className="h-4 w-4" />
      </button>
    </div>
  );
};
