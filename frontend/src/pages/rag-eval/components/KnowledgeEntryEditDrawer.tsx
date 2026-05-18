import React, { useMemo, useState } from 'react';
import type { KnowledgeCurationEntry, KnowledgeEntryPatchRequest } from '../../../shared/api/modules/knowledgeCuration';

const listFromRecord = (record: Record<string, unknown>, key: string): string[] => {
  const value = record[key];
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === 'string') return item;
      if (typeof item === 'number' || typeof item === 'boolean') return String(item);
      return '';
    })
    .map((item) => item.trim())
    .filter(Boolean);
};

const linesToList = (value: string): string[] => Array.from(new Set(value.split('\n').map((line) => line.trim()).filter(Boolean)));

const parseObjectJson = (value: string): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } => {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ok: false, error: 'Advanced JSON должен быть объектом.' };
    }
    return { ok: true, value: parsed as Record<string, unknown> };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : 'Invalid JSON' };
  }
};

export const KnowledgeEntryEditDrawer: React.FC<{
  entry: KnowledgeCurationEntry | null;
  pending: boolean;
  error: string;
  onClose: () => void;
  onSave: (payload: KnowledgeEntryPatchRequest) => void;
}> = ({ entry, pending, error, onClose, onSave }) => {
  const [title, setTitle] = useState(entry?.title ?? '');
  const [answer, setAnswer] = useState(entry?.answer ?? '');
  const [questions, setQuestions] = useState(entry ? listFromRecord(entry.enrichment, 'questions').join('\n') : '');
  const [paraphrases, setParaphrases] = useState(entry ? listFromRecord(entry.enrichment, 'paraphrases').join('\n') : '');
  const [synonyms, setSynonyms] = useState(entry ? listFromRecord(entry.enrichment, 'synonyms').join('\n') : '');
  const [typoQueries, setTypoQueries] = useState(entry ? listFromRecord(entry.enrichment, 'typo_queries').join('\n') : '');
  const [colloquialQueries, setColloquialQueries] = useState(entry ? listFromRecord(entry.enrichment, 'colloquial_queries').join('\n') : '');
  const [tags, setTags] = useState(entry ? listFromRecord(entry.enrichment, 'tags').join('\n') : '');
  const [retrievalGuards, setRetrievalGuards] = useState(entry ? listFromRecord(entry.enrichment, 'retrieval_guards').join('\n') : '');
  const [advancedJson, setAdvancedJson] = useState(JSON.stringify(entry?.enrichment ?? {}, null, 2));
  const [rebuildEmbedding, setRebuildEmbedding] = useState(true);

  const advancedParse = useMemo(() => parseObjectJson(advancedJson), [advancedJson]);

  if (!entry) return null;

  const save = () => {
    if (!advancedParse.ok) return;

    const enrichment: Record<string, unknown> = {
      ...advancedParse.value,
      questions: linesToList(questions),
      paraphrases: linesToList(paraphrases),
      synonyms: linesToList(synonyms),
      typo_queries: linesToList(typoQueries),
      colloquial_queries: linesToList(colloquialQueries),
      tags: linesToList(tags),
      retrieval_guards: linesToList(retrievalGuards),
    };

    onSave({
      title,
      answer,
      enrichment,
      expected_version: entry.version,
      reason: 'Manual curation edit',
      rebuild_embedding: rebuildEmbedding,
      idempotency_key: crypto.randomUUID(),
    });
  };

  const saveDisabled = pending || !title.trim() || !answer.trim() || !advancedParse.ok;

  return (
    <div className="fixed inset-0 z-50 bg-black/40 p-4">
      <div className="ml-auto flex h-full max-w-4xl flex-col rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-xl">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Edit canonical entry</h2>
            <p className="text-sm text-[var(--text-muted)]">Source refs пока read-only: backend не принимает их silent-edit и вернёт 400 при попытке изменить.</p>
          </div>
          <button type="button" onClick={onClose} className="text-sm text-[var(--text-muted)]">Закрыть</button>
        </div>

        <div className="mt-4 grid min-h-0 flex-1 gap-4 overflow-auto xl:grid-cols-[1fr_360px]">
          <div className="space-y-3">
            {error && <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">{error}</div>}
            {!advancedParse.ok && <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">Invalid advanced JSON: {advancedParse.error}</div>}

            <label className="block text-sm text-[var(--text-muted)]">
              Title
              <input value={title} onChange={(event) => setTitle(event.target.value)} className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)]" />
            </label>

            <label className="block text-sm text-[var(--text-muted)]">
              Answer
              <textarea value={answer} onChange={(event) => setAnswer(event.target.value)} rows={8} className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)]" />
            </label>

            <div className="grid gap-3 md:grid-cols-2">
              <ListEditor title="Questions" value={questions} onChange={setQuestions} />
              <ListEditor title="Paraphrases" value={paraphrases} onChange={setParaphrases} />
              <ListEditor title="Synonyms" value={synonyms} onChange={setSynonyms} />
              <ListEditor title="Typo queries" value={typoQueries} onChange={setTypoQueries} />
              <ListEditor title="Colloquial queries" value={colloquialQueries} onChange={setColloquialQueries} />
              <ListEditor title="Tags" value={tags} onChange={setTags} />
            </div>

            <ListEditor title="Retrieval guards" value={retrievalGuards} onChange={setRetrievalGuards} rows={3} />

            <details className="rounded-xl bg-[var(--control-bg)] p-3">
              <summary className="cursor-pointer text-sm font-semibold text-[var(--text-primary)]">Advanced enrichment JSON</summary>
              <textarea value={advancedJson} onChange={(event) => setAdvancedJson(event.target.value)} rows={10} className="mt-3 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-2 font-mono text-xs text-[var(--text-primary)]" />
            </details>

            <label className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
              <input type="checkbox" checked={rebuildEmbedding} onChange={(event) => setRebuildEmbedding(event.target.checked)} />
              Rebuild embedding after save
            </label>
          </div>

          <div className="space-y-3">
            <div className="rounded-xl bg-[var(--control-bg)] p-3 text-sm text-[var(--text-muted)]">
              <div className="font-semibold text-[var(--text-primary)]">Entry state</div>
              <div className="mt-2">id: {entry.id}</div>
              <div>version: {entry.version}</div>
              <div>status: {entry.status}</div>
              <div>visibility: {entry.visibility}</div>
              <div>embedding: {entry.has_embedding ? 'yes' : 'no'}</div>
              <div>retrieval surface: {entry.has_retrieval_surface ? 'yes' : 'no'}</div>
            </div>

            <div className="rounded-xl bg-[var(--control-bg)] p-3 text-xs text-[var(--text-muted)]">
              <div className="font-semibold text-[var(--text-primary)]">Source refs · read-only · {entry.source_refs.length}</div>
              <div className="mt-2 max-h-[420px] space-y-2 overflow-auto">
                {entry.source_refs.length ? entry.source_refs.map((ref, index) => (
                  <div key={`${entry.id}-source-ref-${index}`} className="rounded-lg bg-[var(--surface-elevated)] p-2">
                    <div className="font-medium text-[var(--text-primary)]">#{index + 1}</div>
                    <pre className="mt-1 overflow-auto whitespace-pre-wrap">{JSON.stringify(ref, null, 2)}</pre>
                  </div>
                )) : <div>Нет source refs.</div>}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-xl bg-[var(--control-bg)] px-4 py-2 text-sm text-[var(--text-primary)]">Cancel</button>
          <button type="button" disabled={saveDisabled} onClick={save} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Save</button>
        </div>
      </div>
    </div>
  );
};

const ListEditor: React.FC<{
  title: string;
  value: string;
  rows?: number;
  onChange: (value: string) => void;
}> = ({ title, value, rows = 4, onChange }) => (
  <label className="block text-sm text-[var(--text-muted)]">
    {title}
    <textarea
      value={value}
      onChange={(event) => onChange(event.target.value)}
      rows={rows}
      placeholder="One value per line"
      className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)]"
    />
  </label>
);
