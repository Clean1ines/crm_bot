import React from 'react';
import { FileText, Trash2 } from 'lucide-react';

import { workflowStatusLabel } from '../workflow-card/workflowCardLabels';
import { t } from '@shared/i18n';

type DocumentCardHeaderProps = {
  workflowStatus: string | null | undefined;
  canShowPrimaryProcessingControl: boolean;
  primaryProcessingActionId: string | null;
  primaryProcessingActionReason?: string | null;
  isDeletePending: boolean;
  onPrimaryProcessingControl: () => Promise<void> | void;
  onRequestDelete: () => void;
};

export const DocumentCardHeader: React.FC<DocumentCardHeaderProps> = ({
  workflowStatus,
  canShowPrimaryProcessingControl,
  primaryProcessingActionId,
  primaryProcessingActionReason,
  isDeletePending,
  onPrimaryProcessingControl,
  onRequestDelete,
}) => (
  <div className="mb-4 flex min-w-0 items-start justify-between gap-2">
    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--surface-secondary)] text-[var(--accent-primary)]">
      <FileText className="h-5 w-5" />
    </div>

    <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
      <span className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]">
        {workflowStatusLabel(workflowStatus)}
      </span>
      {canShowPrimaryProcessingControl && (
        <button
          type="button"
          onClick={onPrimaryProcessingControl}
          title={primaryProcessingActionReason || undefined}
          className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20"
        >
          {primaryProcessingActionId === 'pause_processing' ? 'Пауза' : 'Продолжить'}
        </button>
      )}
      <button
        type="button"
        onClick={onRequestDelete}
        disabled={isDeletePending}
        title={t('common.actions.delete')}
        className="rounded-lg p-2 text-[var(--accent-danger-text)] transition-colors hover:bg-[var(--accent-danger-bg)] disabled:cursor-wait disabled:opacity-50"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  </div>
);
