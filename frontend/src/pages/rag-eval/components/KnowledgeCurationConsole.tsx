import React, { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { getErrorMessage } from '../../../shared/api/client';
import {
  type KnowledgeCurationEntry,
  type KnowledgeEntryMergePreview,
} from '../../../shared/api/modules/knowledgeCuration';
import { KnowledgeCurationActionsPanel } from './KnowledgeCurationActionsPanel';
import { KnowledgeCurationDiagnostics } from './KnowledgeCurationDiagnostics';
import { KnowledgeCurationFiltersBar, type CurationFilter, type CurationSort } from './KnowledgeCurationFiltersBar';
import { KnowledgeCurationOverviewCard } from './KnowledgeCurationOverviewCard';
import { KnowledgeEntryCurationCard } from './KnowledgeEntryCurationCard';
import { KnowledgeEntryEditDrawer } from './KnowledgeEntryEditDrawer';
import { KnowledgeEntryMergeDrawer } from './KnowledgeEntryMergeDrawer';
import { KnowledgeEntryVersionDrawer } from './KnowledgeEntryVersionDrawer';
import { useKnowledgeCurationSelection } from '../hooks/useKnowledgeCurationSelection';
import { useKnowledgeCurationQueries } from '../hooks/useKnowledgeCurationQueries';
import { useKnowledgeCurationMutations } from '../hooks/useKnowledgeCurationMutations';


export const KnowledgeCurationConsole: React.FC<{
  projectId: string;
  documentId: string;
  documentName?: string;
  onInvalidateRagEval?: () => Promise<void>;
}> = ({ projectId, documentId, documentName, onInvalidateRagEval }) => {
  const [filter, setFilter] = useState<CurationFilter>('all');
  const [sort, setSort] = useState<CurationSort>('most_suspicious');
  const [editingEntry, setEditingEntry] = useState<KnowledgeCurationEntry | null>(null);
  const [diagnosticsEntry, setDiagnosticsEntry] = useState<KnowledgeCurationEntry | null>(null);
  const [versionEntry, setVersionEntry] = useState<KnowledgeCurationEntry | null>(null);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergePreview, setMergePreview] = useState<KnowledgeEntryMergePreview | null>(null);
  const [mutationError, setMutationError] = useState('');

  const { curationQuery, actionsQuery, versionsQuery, payload, allEntries, visibleEntries } = useKnowledgeCurationQueries(projectId, documentId, filter, sort, versionEntry?.id);
  const { selectedIds, selectedEntries, toggleEntry, clearSelection } = useKnowledgeCurationSelection(allEntries);
  const {
    statusMutation,
    patchMutation,
    rebuildMutation,
    previewMutation,
    applyMergeMutation,
    restoreVersionMutation,
  } = useKnowledgeCurationMutations(
    projectId,
    documentId,
    versionEntry?.id,
    onInvalidateRagEval,
    () => { setEditingEntry(null); setMutationError(''); },
    (partial, error) => { if (partial) setMutationError(error || 'Merge применён частично'); setMergeOpen(false); setMergePreview(null); clearSelection(); },
    (preview) => { setMergePreview(preview); setMutationError(''); },
    (message) => setMutationError(message),
    (message) => setMutationError(message),
  );

  if (!documentId) return <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]">Выберите processed документ для курации знаний.</section>;
  if (curationQuery.isLoading) return <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Загружаем curation console...</section>;
  if (curationQuery.error || !payload) return <section className="rounded-2xl border border-red-500/30 bg-red-500/5 p-5 text-sm text-red-500">{getErrorMessage(curationQuery.error, 'Не удалось загрузить curation state')}</section>;

  return (
    <div className="space-y-4">
      <KnowledgeCurationOverviewCard summary={{ ...payload.summary, document_name: payload.summary.document_name || documentName || '' }} />
      <KnowledgeCurationFiltersBar filter={filter} sort={sort} onFilterChange={setFilter} onSortChange={setSort} />
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
        <div className="text-sm text-[var(--text-muted)]">Selected {selectedIds.size}/12 for merge. Merge требует 2–12 entries.</div>
        <button type="button" disabled={selectedEntries.length < 2 || selectedEntries.length > 12} onClick={() => { setMergeOpen(true); setMergePreview(null); setMutationError(''); }} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Merge selected</button>
      </div>
      <div className="space-y-4">
        {visibleEntries.map((entry) => <KnowledgeEntryCurationCard key={entry.id} entry={entry} selected={selectedIds.has(entry.id)} onToggle={() => toggleEntry(entry.id)} onEdit={() => { setEditingEntry(entry); setMutationError(''); }} onVersions={() => setVersionEntry(entry)} onDiagnostics={() => setDiagnosticsEntry(entry)} onStatus={(action) => statusMutation.mutate({ entry, action })} onRebuild={() => rebuildMutation.mutate(entry)} />)}
        {!visibleEntries.length && <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]">По выбранному фильтру canonical entries нет.</section>}
      </div>
      <KnowledgeCurationActionsPanel actions={actionsQuery.data ?? []} />
      <KnowledgeEntryEditDrawer key={editingEntry?.id ?? 'empty'} entry={editingEntry} pending={patchMutation.isPending} error={mutationError} onClose={() => setEditingEntry(null)} onSave={(patch) => { if (editingEntry) patchMutation.mutate({ entry: editingEntry, payload: patch }); }} />
      <KnowledgeEntryMergeDrawer entries={mergeOpen ? selectedEntries : []} preview={mergePreview} pending={previewMutation.isPending || applyMergeMutation.isPending} error={mutationError} onClose={() => setMergeOpen(false)} onPreview={(request) => previewMutation.mutate(request)} onApply={(request) => applyMergeMutation.mutate(request)} />
      {versionEntry && (
        <KnowledgeEntryVersionDrawer
          versions={versionsQuery.data ?? []}
          pending={restoreVersionMutation.isPending}
          onClose={() => setVersionEntry(null)}
          onRestore={(versionId) => restoreVersionMutation.mutate(versionId)}
        />
      )}
      <KnowledgeCurationDiagnostics entry={diagnosticsEntry} duplicateGroups={payload.duplicate_groups} onClose={() => setDiagnosticsEntry(null)} />
    </div>
  );
};
