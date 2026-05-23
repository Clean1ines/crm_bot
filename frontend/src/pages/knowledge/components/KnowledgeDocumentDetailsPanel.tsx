import React from 'react';

import { t } from '@shared/i18n';

export const KnowledgeDocumentDetailsPanel: React.FC<{
  actionsNode: React.ReactNode;
  technicalNode: React.ReactNode;
}> = ({ actionsNode, technicalNode }) => (
  <details className="mb-3 rounded-xl bg-[var(--surface-secondary)] p-2 text-xs text-[var(--text-muted)]">
    <summary className="cursor-pointer list-none font-medium text-[var(--text-primary)]">
      {t('knowledge.documentCard.detailsSummary')}
    </summary>
    <div className="mt-2 space-y-2">
      {actionsNode}
      {technicalNode}
    </div>
  </details>
);
