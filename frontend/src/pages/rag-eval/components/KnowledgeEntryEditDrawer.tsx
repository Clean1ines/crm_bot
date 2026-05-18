import React, { useState } from 'react';
import type { KnowledgeCurationEntry, KnowledgeEntryPatchRequest } from '../../../shared/api/modules/knowledgeCuration';

export const KnowledgeEntryEditDrawer: React.FC<{
  entry: KnowledgeCurationEntry | null;
  pending: boolean;
  error: string;
  onClose: () => void;
  onSave: (payload: KnowledgeEntryPatchRequest) => void;
}> = ({ entry, pending, error, onClose, onSave }) => {
  const [title, setTitle] = useState(entry?.title ?? '');
  const [answer, setAnswer] = useState(entry?.answer ?? '');
  const [enrichmentJson, setEnrichmentJson] = useState(JSON.stringify(entry?.enrichment ?? {}, null, 2));
  const [rebuildEmbedding, setRebuildEmbedding] = useState(true);

  if (!entry) return null;

  const save = () => {
    let enrichment: Record<string, unknown> = {};
    try {
      const parsed = JSON.parse(enrichmentJson) as unknown;
      enrichment = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
    } catch {
      return;
    }
    onSave({ title, answer, enrichment, expected_version: entry.version, reason: 'Manual curation edit', rebuild_embedding: rebuildEmbedding, idempotency_key: crypto.randomUUID() });
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 p-4">
      <div className="ml-auto flex h-full max-w-3xl flex-col rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-xl">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Edit entry</h2>
          <button type="button" onClick={onClose} className="text-sm text-[var(--text-muted)]">Закрыть</button>
        </div>
        <div className="mt-4 space-y-3 overflow-auto">
          {error && <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">{error}</div>}
          <label className="block text-sm text-[var(--text-muted)]">Title<input value={title} onChange={(event) => setTitle(event.target.value)} className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)]" /></label>
          <label className="block text-sm text-[var(--text-muted)]">Answer<textarea value={answer} onChange={(event) => setAnswer(event.target.value)} rows={8} className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)]" /></label>
          <label className="block text-sm text-[var(--text-muted)]">Enrichment JSON<textarea value={enrichmentJson} onChange={(event) => setEnrichmentJson(event.target.value)} rows={10} className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 font-mono text-xs text-[var(--text-primary)]" /></label>
          <div className="rounded-xl bg-[var(--control-bg)] p-3 text-xs text-[var(--text-muted)]">Source refs: {entry.source_refs.length}<pre className="mt-2 max-h-40 overflow-auto">{JSON.stringify(entry.source_refs, null, 2)}</pre></div>
          <label className="flex items-center gap-2 text-sm text-[var(--text-muted)]"><input type="checkbox" checked={rebuildEmbedding} onChange={(event) => setRebuildEmbedding(event.target.checked)} /> Rebuild embedding after save</label>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-xl bg-[var(--control-bg)] px-4 py-2 text-sm text-[var(--text-primary)]">Cancel</button>
          <button type="button" disabled={pending || !title.trim() || !answer.trim()} onClick={save} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Save</button>
        </div>
      </div>
    </div>
  );
};
