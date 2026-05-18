import React, { useMemo, useState } from 'react';
import type { KnowledgeCurationEntry, KnowledgeEntryMergeIncludeOptions, KnowledgeEntryMergePreview, KnowledgeEntryMergePreviewRequest } from '../../../shared/api/modules/knowledgeCuration';

const defaultInclude: KnowledgeEntryMergeIncludeOptions = {
  answers: true, questions: true, paraphrases: true, synonyms: true, typo_queries: true,
  colloquial_queries: true, tags: true, retrieval_guards: false, source_refs: true, metadata: true,
};

export const KnowledgeEntryMergeDrawer: React.FC<{
  entries: KnowledgeCurationEntry[];
  preview: KnowledgeEntryMergePreview | null;
  pending: boolean;
  error: string;
  onClose: () => void;
  onPreview: (payload: KnowledgeEntryMergePreviewRequest) => void;
  onApply: (payload: KnowledgeEntryMergePreviewRequest) => void;
}> = ({ entries, preview, pending, error, onClose, onPreview, onApply }) => {
  const [parentId, setParentId] = useState(entries[0]?.id ?? '');
  const [finalTitle, setFinalTitle] = useState('');
  const [finalAnswer, setFinalAnswer] = useState('');
  const [instruction, setInstruction] = useState('');
  const [include, setInclude] = useState(defaultInclude);
  const idempotencyKey = useMemo(() => crypto.randomUUID(), []);

  if (entries.length < 2) return null;

  const payload = (): KnowledgeEntryMergePreviewRequest => ({
    parent_entry_id: parentId || entries[0].id,
    absorbed_entry_ids: entries.map((entry) => entry.id).filter((id) => id !== (parentId || entries[0].id)),
    parent_expected_version: entries.find((entry) => entry.id === (parentId || entries[0].id))?.version ?? null,
    absorbed_expected_versions: Object.fromEntries(entries.filter((entry) => entry.id !== (parentId || entries[0].id)).map((entry) => [entry.id, entry.version])),
    merge_instruction: instruction,
    final_title: finalTitle || null,
    final_answer: finalAnswer || null,
    include,
    exclude: { question_values: [], synonym_values: [], tag_values: [], source_ref_keys: [], metadata_keys: [] },
    absorbed_status: 'merged',
    rebuild_embedding: true,
    rerun_eval: false,
    idempotency_key: idempotencyKey,
  });

  return (
    <div className="fixed inset-0 z-50 bg-black/40 p-4">
      <div className="ml-auto flex h-full max-w-4xl flex-col rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-xl">
        <div className="flex items-center justify-between gap-3"><h2 className="text-lg font-semibold text-[var(--text-primary)]">Merge preview/apply</h2><button type="button" onClick={onClose} className="text-sm text-[var(--text-muted)]">Закрыть</button></div>
        <div className="mt-4 grid min-h-0 flex-1 gap-4 overflow-auto lg:grid-cols-2">
          <div className="space-y-3">
            {error && <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">{error}</div>}
            <div className="rounded-xl bg-[var(--control-bg)] p-3">
              <div className="text-sm font-semibold text-[var(--text-primary)]">Parent/survivor</div>
              {entries.map((entry) => <label key={entry.id} className="mt-2 flex items-center gap-2 text-sm text-[var(--text-secondary)]"><input type="radio" checked={(parentId || entries[0].id) === entry.id} onChange={() => setParentId(entry.id)} />{entry.title} · v{entry.version}</label>)}
            </div>
            <input value={finalTitle} onChange={(event) => setFinalTitle(event.target.value)} placeholder="Final title (optional)" className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)]" />
            <textarea value={finalAnswer} onChange={(event) => setFinalAnswer(event.target.value)} placeholder="Final answer (optional)" rows={5} className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)]" />
            <textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder="Merge instruction/reason" rows={3} className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)]" />
            <div className="grid grid-cols-2 gap-2 rounded-xl bg-[var(--control-bg)] p-3 text-sm text-[var(--text-muted)]">
              {Object.keys(include).map((key) => <label key={key} className="flex items-center gap-2"><input type="checkbox" checked={include[key as keyof KnowledgeEntryMergeIncludeOptions]} onChange={(event) => setInclude({ ...include, [key]: event.target.checked })} />{key}</label>)}
            </div>
          </div>
          <div className="space-y-3">
            <div className="rounded-xl bg-[var(--control-bg)] p-3 text-sm text-[var(--text-muted)]">Selected: {entries.length}. Absorbed entries will be marked merged/hidden and removed from retrieval surface.</div>
            {preview ? <div className="space-y-3">
              {!!preview.blocking_errors.length && <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">Blocking: {preview.blocking_errors.join(', ')}</div>}
              {!!preview.warnings.length && <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-600">Warnings: {preview.warnings.join(', ')}</div>}
              <pre className="max-h-[520px] overflow-auto rounded-xl bg-[var(--control-bg)] p-3 text-xs text-[var(--text-secondary)]">{JSON.stringify(preview, null, 2)}</pre>
            </div> : <div className="rounded-xl bg-[var(--control-bg)] p-3 text-sm text-[var(--text-muted)]">Нажмите Preview, чтобы увидеть before/after без мутаций.</div>}
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={() => onPreview(payload())} disabled={pending} className="rounded-xl bg-[var(--control-bg)] px-4 py-2 text-sm text-[var(--text-primary)]">Preview</button>
          <button type="button" onClick={() => onApply(payload())} disabled={pending || !preview || !!preview.blocking_errors.length} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Apply merge</button>
        </div>
      </div>
    </div>
  );
};
