import React from 'react';
import type { KnowledgeEntryVersion } from '../../../shared/api/modules/knowledgeCuration';

export const KnowledgeEntryVersionDrawer: React.FC<{
  versions: KnowledgeEntryVersion[];
  pending: boolean;
  onClose: () => void;
  onRestore: (versionId: string) => void;
}> = ({ versions, pending, onClose, onRestore }) => (
  <div className="fixed inset-0 z-50 bg-black/40 p-4">
    <div className="ml-auto flex h-full max-w-3xl flex-col rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-xl">
      <div className="flex items-center justify-between"><h2 className="text-lg font-semibold text-[var(--text-primary)]">Versions</h2><button type="button" onClick={onClose} className="text-sm text-[var(--text-muted)]">Закрыть</button></div>
      <div className="mt-4 space-y-3 overflow-auto">
        {!versions.length && <div className="rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">Версий пока нет.</div>}
        {versions.map((version) => <article key={version.id} className="rounded-xl bg-[var(--control-bg)] p-3">
          <div className="flex items-center justify-between gap-3 text-sm text-[var(--text-primary)]"><span>{version.from_version} → {version.to_version}</span><button type="button" disabled={pending} onClick={() => onRestore(version.id)} className="rounded-lg bg-[var(--accent-primary)] px-3 py-1 text-xs font-semibold text-white disabled:opacity-50">Restore</button></div>
          <div className="mt-1 text-xs text-[var(--text-muted)]">action: {version.action_id || '—'} · {version.created_at || '—'}</div>
          <pre className="mt-2 max-h-48 overflow-auto text-xs text-[var(--text-secondary)]">{JSON.stringify(version.new_snapshot, null, 2)}</pre>
        </article>)}
      </div>
    </div>
  </div>
);
