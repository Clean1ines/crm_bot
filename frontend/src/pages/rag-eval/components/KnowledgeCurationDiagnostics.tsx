import React from 'react';
import type { KnowledgeCurationDuplicateGroup, KnowledgeCurationEntry } from '../../../shared/api/modules/knowledgeCuration';

export const KnowledgeCurationDiagnostics: React.FC<{
  entry: KnowledgeCurationEntry | null;
  duplicateGroups: KnowledgeCurationDuplicateGroup[];
  onClose: () => void;
}> = ({ entry, duplicateGroups, onClose }) => {
  if (!entry) return null;
  const groups = duplicateGroups.filter((group) => group.entry_ids.includes(entry.id));
  return (
    <div className="fixed inset-0 z-50 bg-black/40 p-4">
      <div className="ml-auto h-full max-w-3xl overflow-auto rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-xl">
        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold text-[var(--text-primary)]">Diagnostics</h2><button type="button" onClick={onClose} className="text-sm text-[var(--text-muted)]">Закрыть</button></div>
        <pre className="mt-4 rounded-xl bg-[var(--control-bg)] p-3 text-xs text-[var(--text-secondary)]">{JSON.stringify({ entry, duplicate_groups: groups }, null, 2)}</pre>
      </div>
    </div>
  );
};
