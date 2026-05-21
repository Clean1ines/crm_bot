import { t } from '@shared/i18n';
import React from 'react';
import type { KnowledgeCurationAction } from '../../../shared/api/modules/knowledgeCuration';

export const KnowledgeCurationActionsPanel: React.FC<{ actions: KnowledgeCurationAction[] }> = ({ actions }) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
    <h3 className="text-base font-semibold text-[var(--text-primary)]">{t('ragEval.curation.actions.historyTitle')}</h3>
    <div className="mt-3 space-y-2">
      {!actions.length && <div className="text-sm text-[var(--text-muted)]">{t('ragEval.curation.actions.empty')}</div>}
      {actions.slice(0, 20).map((action) => <div key={action.id} className="rounded-xl bg-[var(--control-bg)] p-3 text-sm text-[var(--text-secondary)]">
        <div className="font-medium text-[var(--text-primary)]">{action.action_type} · {action.status}</div>
        <div className="mt-1 text-xs text-[var(--text-muted)]">{action.source_kind} · {action.created_at || '—'} · {action.reason || 'no reason'}</div>
        {action.error && <div className="mt-1 text-xs text-red-500">{action.error}</div>}
      </div>)}
    </div>
  </section>
);
