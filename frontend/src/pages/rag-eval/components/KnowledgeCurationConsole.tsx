import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { getErrorMessage } from '../../../shared/api/client';
import {
  knowledgeCurationApi,
  type KnowledgeCurationEntry,
  type KnowledgeEntryMergePreview,
  type KnowledgeEntryMergePreviewRequest,
  type KnowledgeEntryPatchRequest,
} from '../../../shared/api/modules/knowledgeCuration';
import { KnowledgeCurationActionsPanel } from './KnowledgeCurationActionsPanel';
import { KnowledgeCurationDiagnostics } from './KnowledgeCurationDiagnostics';
import { KnowledgeCurationFiltersBar, type CurationFilter, type CurationSort } from './KnowledgeCurationFiltersBar';
import { KnowledgeCurationOverviewCard } from './KnowledgeCurationOverviewCard';
import { KnowledgeEntryCurationCard } from './KnowledgeEntryCurationCard';
import { KnowledgeEntryEditDrawer } from './KnowledgeEntryEditDrawer';
import { KnowledgeEntryMergeDrawer } from './KnowledgeEntryMergeDrawer';
import { KnowledgeEntryVersionDrawer } from './KnowledgeEntryVersionDrawer';
import { matchesKnowledgeCurationFilter } from '../lib/knowledgeCurationFilters';
import { sortKnowledgeCurationEntries } from '../lib/knowledgeCurationSort';
import { useKnowledgeCurationSelection } from '../hooks/useKnowledgeCurationSelection';


export const KnowledgeCurationConsole: React.FC<{
  projectId: string;
  documentId: string;
  documentName?: string;
  onInvalidateRagEval?: () => Promise<void>;
}> = ({ projectId, documentId, documentName, onInvalidateRagEval }) => {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<CurationFilter>('all');
  const [sort, setSort] = useState<CurationSort>('most_suspicious');
  const [editingEntry, setEditingEntry] = useState<KnowledgeCurationEntry | null>(null);
  const [diagnosticsEntry, setDiagnosticsEntry] = useState<KnowledgeCurationEntry | null>(null);
  const [versionEntry, setVersionEntry] = useState<KnowledgeCurationEntry | null>(null);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergePreview, setMergePreview] = useState<KnowledgeEntryMergePreview | null>(null);
  const [mutationError, setMutationError] = useState('');

  const curationQuery = useQuery({
    queryKey: ['knowledge-curation', projectId, documentId],
    queryFn: async () => {
      const { data } = await knowledgeCurationApi.getDocumentCuration(projectId, documentId);
      return data;
    },
    enabled: !!projectId && !!documentId,
    retry: false,
  });

  const actionsQuery = useQuery({
    queryKey: ['knowledge-curation-actions', projectId, documentId],
    queryFn: async () => {
      const { data } = await knowledgeCurationApi.listActions(projectId, documentId);
      return data.actions;
    },
    enabled: !!projectId && !!documentId,
    retry: false,
  });

  const versionsQuery = useQuery({
    queryKey: ['knowledge-curation-versions', projectId, documentId, versionEntry?.id],
    queryFn: async () => {
      const { data } = await knowledgeCurationApi.listEntryVersions(projectId, documentId, String(versionEntry?.id));
      return data.versions;
    },
    enabled: !!projectId && !!documentId && !!versionEntry?.id,
    retry: false,
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['knowledge-curation', projectId, documentId] });
    await queryClient.invalidateQueries({ queryKey: ['knowledge-curation-actions', projectId, documentId] });
    if (onInvalidateRagEval) await onInvalidateRagEval();
  };

  const statusMutation = useMutation({
    mutationFn: async ({ entry, action }: { entry: KnowledgeCurationEntry; action: 'hide_entry' | 'reject_entry' | 'restore_entry' | 'publish_entry' | 'unpublish_entry' }) => knowledgeCurationApi.setEntryStatus(projectId, documentId, entry.id, { action, expected_version: entry.version, reason: `Manual ${action}`, idempotency_key: crypto.randomUUID() }),
    onSuccess: async () => { toast.success('Статус обновлён'); await invalidate(); },
    onError: (error) => { toast.error(getErrorMessage(error, 'Не удалось обновить статус')); },
  });

  const patchMutation = useMutation({
    mutationFn: async ({ entry, payload }: { entry: KnowledgeCurationEntry; payload: KnowledgeEntryPatchRequest }) => knowledgeCurationApi.patchEntry(projectId, documentId, entry.id, payload),
    onSuccess: async () => { setEditingEntry(null); setMutationError(''); toast.success('Entry сохранён'); await invalidate(); },
    onError: (error) => { setMutationError(getErrorMessage(error, 'Не удалось сохранить entry')); },
  });

  const rebuildMutation = useMutation({
    mutationFn: async (entry: KnowledgeCurationEntry) => knowledgeCurationApi.rebuildEntryEmbedding(projectId, documentId, entry.id, {
      expected_version: entry.version,
      reason: 'Manual embedding rebuild',
      idempotency_key: crypto.randomUUID(),
    }),
    onSuccess: async () => { toast.success('Embedding rebuild выполнен'); await invalidate(); },
    onError: (error) => { toast.error(getErrorMessage(error, 'Не удалось rebuild embedding')); },
  });

  const previewMutation = useMutation({
    mutationFn: async (payload: KnowledgeEntryMergePreviewRequest) => knowledgeCurationApi.previewMerge(projectId, documentId, payload),
    onSuccess: ({ data }) => { setMergePreview(data.preview); setMutationError(''); },
    onError: (error) => { setMutationError(getErrorMessage(error, 'Preview merge failed')); },
  });

  const applyMergeMutation = useMutation({
    mutationFn: async (payload: KnowledgeEntryMergePreviewRequest) => knowledgeCurationApi.applyMerge(projectId, documentId, payload),
    onSuccess: async ({ data }) => {
      if (data.partial) toast.error(data.error || 'Merge применён частично'); else toast.success('Merge применён');
      setMergeOpen(false); setMergePreview(null); clearSelection(); await invalidate();
    },
    onError: (error) => { setMutationError(getErrorMessage(error, 'Apply merge failed')); },
  });

  const restoreVersionMutation = useMutation({
    mutationFn: async (versionId: string) => knowledgeCurationApi.restoreEntryVersion(projectId, documentId, String(versionEntry?.id), versionId, 'Manual version restore'),
    onSuccess: async () => { toast.success('Версия восстановлена'); setVersionEntry(null); await invalidate(); },
    onError: (error) => { toast.error(getErrorMessage(error, 'Не удалось восстановить версию')); },
  });

  const payload = curationQuery.data;
  const duplicateIds = useMemo(() => new Set((payload?.duplicate_groups ?? []).flatMap((group) => group.entry_ids)), [payload?.duplicate_groups]);
  const duplicateSize = useMemo(() => {
    const map = new Map<string, number>();
    for (const group of payload?.duplicate_groups ?? []) for (const id of group.entry_ids) map.set(id, Math.max(map.get(id) ?? 0, group.entry_ids.length));
    return map;
  }, [payload?.duplicate_groups]);
  const allEntries = useMemo(() => payload?.entries ?? [], [payload?.entries]);
  const { selectedIds, selectedEntries, toggleEntry, clearSelection } = useKnowledgeCurationSelection(allEntries);
  const visibleEntries = useMemo(() => sortKnowledgeCurationEntries(allEntries.filter((entry) => matchesKnowledgeCurationFilter(entry, filter, duplicateIds)), sort, duplicateSize), [allEntries, filter, duplicateIds, sort, duplicateSize]);

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
      <KnowledgeEntryVersionDrawer versions={versionEntry ? (versionsQuery.data ?? []) : []} pending={restoreVersionMutation.isPending} onClose={() => setVersionEntry(null)} onRestore={(versionId) => restoreVersionMutation.mutate(versionId)} />
      <KnowledgeCurationDiagnostics entry={diagnosticsEntry} duplicateGroups={payload.duplicate_groups} onClose={() => setDiagnosticsEntry(null)} />
    </div>
  );
};
