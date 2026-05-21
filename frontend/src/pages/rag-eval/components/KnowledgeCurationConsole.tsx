import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { t } from '@shared/i18n';
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

const listCount = (value: unknown): number => Array.isArray(value) ? value.length : 0;
const issueTypes = (entry: KnowledgeCurationEntry): Set<string> => new Set(entry.issues.map((issue) => issue.type));

const matchesFilter = (entry: KnowledgeCurationEntry, filter: CurationFilter, duplicateIds: Set<string>): boolean => {
  const issues = issueTypes(entry);
  if (filter === 'all') return true;
  if (filter === 'published') return entry.status === 'published';
  if (filter === 'needs_review') return entry.status === 'needs_review';
  if (filter === 'hidden') return entry.status === 'hidden';
  if (filter === 'rejected') return entry.status === 'rejected';
  if (filter === 'merged') return entry.status === 'merged' || Boolean((entry.metadata.curation as Record<string, unknown> | undefined)?.merged_into);
  if (filter === 'possible_duplicates') return duplicateIds.has(entry.id);
  if (filter === 'missing_source_refs') return issues.has('missing_source_refs');
  if (filter === 'missing_embedding') return !entry.has_embedding;
  if (filter === 'no_retrieval_surface') return issues.has('published_without_retrieval_row');
  if (filter === 'fallback_chunk') return entry.entry_kind === 'fallback_chunk';
  if (filter === 'suspicious_short') return issues.has('empty_or_too_short_answer');
  if (filter === 'changed_recently') return Boolean(entry.updated_at);
  return true;
};

const sortEntries = (entries: KnowledgeCurationEntry[], sort: CurationSort, duplicateSize: Map<string, number>): KnowledgeCurationEntry[] => {
  const copy = [...entries];
  copy.sort((left, right) => {
    if (sort === 'title') return left.title.localeCompare(right.title);
    if (sort === 'status') return left.status.localeCompare(right.status);
    if (sort === 'updated_at') return String(right.updated_at || '').localeCompare(String(left.updated_at || ''));
    if (sort === 'source_refs_count') return right.source_refs.length - left.source_refs.length;
    if (sort === 'questions_count') return listCount(right.enrichment.questions) - listCount(left.enrichment.questions);
    if (sort === 'duplicate_group_size') return (duplicateSize.get(right.id) ?? 0) - (duplicateSize.get(left.id) ?? 0);
    return right.issues.length - left.issues.length;
  });
  return copy;
};

export const KnowledgeCurationConsole: React.FC<{
  projectId: string;
  documentId: string;
  documentName?: string;
  onInvalidateRagEval?: () => Promise<void>;
}> = ({ projectId, documentId, documentName, onInvalidateRagEval }) => {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<CurationFilter>('all');
  const [sort, setSort] = useState<CurationSort>('most_suspicious');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
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
    onSuccess: async () => { toast.success(t('ragEval.curation.console.statusUpdated')); await invalidate(); },
    onError: (error) => { toast.error(getErrorMessage(error, t('ragEval.curation.console.statusUpdateFailed'))); },
  });

  const patchMutation = useMutation({
    mutationFn: async ({ entry, payload }: { entry: KnowledgeCurationEntry; payload: KnowledgeEntryPatchRequest }) => knowledgeCurationApi.patchEntry(projectId, documentId, entry.id, payload),
    onSuccess: async () => { setEditingEntry(null); setMutationError(''); toast.success(t('ragEval.curation.console.entrySaved')); await invalidate(); },
    onError: (error) => { setMutationError(getErrorMessage(error, t('ragEval.curation.console.entrySaveFailed'))); },
  });

  const rebuildMutation = useMutation({
    mutationFn: async (entry: KnowledgeCurationEntry) => knowledgeCurationApi.rebuildEntryEmbedding(projectId, documentId, entry.id, {
      expected_version: entry.version,
      reason: 'Manual embedding rebuild',
      idempotency_key: crypto.randomUUID(),
    }),
    onSuccess: async () => { toast.success(t('ragEval.curation.console.embeddingRebuildDone')); await invalidate(); },
    onError: (error) => { toast.error(getErrorMessage(error, t('ragEval.curation.console.embeddingRebuildFailed'))); },
  });

  const previewMutation = useMutation({
    mutationFn: async (payload: KnowledgeEntryMergePreviewRequest) => knowledgeCurationApi.previewMerge(projectId, documentId, payload),
    onSuccess: ({ data }) => { setMergePreview(data.preview); setMutationError(''); },
    onError: (error) => { setMutationError(getErrorMessage(error, t('ragEval.curation.console.previewMergeFailed'))); },
  });

  const applyMergeMutation = useMutation({
    mutationFn: async (payload: KnowledgeEntryMergePreviewRequest) => knowledgeCurationApi.applyMerge(projectId, documentId, payload),
    onSuccess: async ({ data }) => {
      if (data.partial) toast.error(data.error || t('ragEval.curation.console.mergePartiallyApplied')); else toast.success(t('ragEval.curation.console.mergeApplied'));
      setMergeOpen(false); setMergePreview(null); setSelectedIds(new Set()); await invalidate();
    },
    onError: (error) => { setMutationError(getErrorMessage(error, t('ragEval.curation.console.applyMergeFailed'))); },
  });

  const restoreVersionMutation = useMutation({
    mutationFn: async (versionId: string) => knowledgeCurationApi.restoreEntryVersion(projectId, documentId, String(versionEntry?.id), versionId, 'Manual version restore'),
    onSuccess: async () => { toast.success(t('ragEval.curation.console.versionRestored')); setVersionEntry(null); await invalidate(); },
    onError: (error) => { toast.error(getErrorMessage(error, t('ragEval.curation.console.versionRestoreFailed'))); },
  });

  const payload = curationQuery.data;
  const duplicateIds = useMemo(() => new Set((payload?.duplicate_groups ?? []).flatMap((group) => group.entry_ids)), [payload?.duplicate_groups]);
  const duplicateSize = useMemo(() => {
    const map = new Map<string, number>();
    for (const group of payload?.duplicate_groups ?? []) for (const id of group.entry_ids) map.set(id, Math.max(map.get(id) ?? 0, group.entry_ids.length));
    return map;
  }, [payload?.duplicate_groups]);
  const visibleEntries = useMemo(() => sortEntries((payload?.entries ?? []).filter((entry) => matchesFilter(entry, filter, duplicateIds)), sort, duplicateSize), [payload?.entries, filter, duplicateIds, sort, duplicateSize]);
  const selectedEntries = useMemo(() => (payload?.entries ?? []).filter((entry) => selectedIds.has(entry.id)), [payload?.entries, selectedIds]);

  if (!documentId) return <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]">{t('ragEval.curation.console.selectProcessedDocument')}</section>;
  if (curationQuery.isLoading) return <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />{t('ragEval.curation.console.loading')}</section>;
  if (curationQuery.error || !payload) return <section className="rounded-2xl border border-red-500/30 bg-red-500/5 p-5 text-sm text-red-500">{getErrorMessage(curationQuery.error, t('ragEval.curation.console.loadFailed'))}</section>;

  return (
    <div className="space-y-4">
      <KnowledgeCurationOverviewCard summary={{ ...payload.summary, document_name: payload.summary.document_name || documentName || '' }} />
      <KnowledgeCurationFiltersBar filter={filter} sort={sort} onFilterChange={setFilter} onSortChange={setSort} />
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
        <div className="text-sm text-[var(--text-muted)]">{t('ragEval.curation.console.selectedForMerge', { selected: String(selectedIds.size) })}</div>
        <button type="button" disabled={selectedEntries.length < 2 || selectedEntries.length > 12} onClick={() => { setMergeOpen(true); setMergePreview(null); setMutationError(''); }} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{t('ragEval.curation.console.mergeSelected')}</button>
      </div>
      <div className="space-y-4">
        {visibleEntries.map((entry) => <KnowledgeEntryCurationCard key={entry.id} entry={entry} selected={selectedIds.has(entry.id)} onToggle={() => setSelectedIds((current) => { const next = new Set(current); if (next.has(entry.id)) next.delete(entry.id); else if (next.size < 12) next.add(entry.id); return next; })} onEdit={() => { setEditingEntry(entry); setMutationError(''); }} onVersions={() => setVersionEntry(entry)} onDiagnostics={() => setDiagnosticsEntry(entry)} onStatus={(action) => statusMutation.mutate({ entry, action })} onRebuild={() => rebuildMutation.mutate(entry)} />)}
        {!visibleEntries.length && <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]">{t('ragEval.curation.console.emptyFilteredEntries')}</section>}
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
