import React from 'react';
import { RefreshCw, StopCircle } from 'lucide-react';

import { t } from '@shared/i18n';

export const DocumentActionsBlock: React.FC<{
  showRetighten: boolean;
  showStop: boolean;
  isRetighteningThisDoc: boolean;
  retightenPending: boolean;
  cancelPending: boolean;
  onRetighten: () => void;
  onStop: () => void;
}> = ({
  showRetighten,
  showStop,
  isRetighteningThisDoc,
  retightenPending,
  cancelPending,
  onRetighten,
  onStop,
}) => {
  if (!showRetighten && !showStop) return null;

  return (
    <div className="flex gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
      {showRetighten && (
        <button
          type="button"
          onClick={onRetighten}
          disabled={retightenPending}
          title={isRetighteningThisDoc ? t('knowledge.actions.retightening') : t('knowledge.actions.retightenDuplicates')}
          className="rounded-lg p-2 text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/10 disabled:cursor-wait disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${isRetighteningThisDoc ? 'animate-spin' : ''}`} />
        </button>
      )}
      {showStop && (
        <button
          type="button"
          onClick={onStop}
          disabled={cancelPending}
          title={t('knowledge.actions.stopProcessing')}
          className="rounded-lg p-2 text-[var(--accent-danger-text)] transition-colors hover:bg-[var(--accent-danger-bg)] disabled:cursor-wait disabled:opacity-50"
        >
          <StopCircle className="h-4 w-4" />
        </button>
      )}
    </div>
  );
};
