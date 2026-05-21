import React, { useMemo, useState } from 'react';
import { t } from '@shared/i18n';
import type {
  KnowledgeCurationEntry,
  KnowledgeEntryMergeIncludeOptions,
  KnowledgeEntryMergePreview,
  KnowledgeEntryMergePreviewRequest,
} from '../../../shared/api/modules/knowledgeCuration';

const defaultInclude: KnowledgeEntryMergeIncludeOptions = {
  answers: true,
  questions: true,
  paraphrases: true,
  synonyms: true,
  typo_queries: true,
  colloquial_queries: true,
  tags: true,
  retrieval_guards: false,
  source_refs: true,
  metadata: true,
};

const includeKeys: Array<keyof KnowledgeEntryMergeIncludeOptions> = [
  'answers',
  'questions',
  'paraphrases',
  'synonyms',
  'typo_queries',
  'colloquial_queries',
  'tags',
  'retrieval_guards',
  'source_refs',
  'metadata',
];

const includeKeyLabel = (key: keyof KnowledgeEntryMergeIncludeOptions): string => {
  if (key === 'answers') return t('ragEval.curation.merge.include.answers');
  if (key === 'questions') return t('ragEval.curation.merge.include.questions');
  if (key === 'paraphrases') return t('ragEval.curation.merge.include.paraphrases');
  if (key === 'synonyms') return t('ragEval.curation.merge.include.synonyms');
  if (key === 'typo_queries') return t('ragEval.curation.merge.include.typoQueries');
  if (key === 'colloquial_queries') return t('ragEval.curation.merge.include.colloquialQueries');
  if (key === 'tags') return t('ragEval.curation.merge.include.tags');
  if (key === 'retrieval_guards') return t('ragEval.curation.merge.include.retrievalGuards');
  if (key === 'source_refs') return t('ragEval.curation.merge.include.sourceRefs');
  if (key === 'metadata') return t('ragEval.curation.merge.include.metadata');
  return key;
};

type MergeExcludeState = KnowledgeEntryMergePreviewRequest['exclude'];

const emptyExclude = (): MergeExcludeState => ({
  question_values: [],
  synonym_values: [],
  tag_values: [],
  source_ref_keys: [],
  metadata_keys: [],
});

const listFromEnrichment = (entry: KnowledgeCurationEntry, key: string): string[] => {
  const value = entry.enrichment[key];
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

const unique = (items: string[]): string[] => Array.from(new Set(items));

const sourceRefKey = (ref: Record<string, unknown>, index: number): string => {
  const chunk = typeof ref.source_chunk_id === 'string' ? ref.source_chunk_id : '';
  const sourceIndex = typeof ref.source_index === 'number' || typeof ref.source_index === 'string' ? String(ref.source_index) : '';
  const quote = typeof ref.quote === 'string' ? ref.quote.slice(0, 80) : '';
  return [chunk, sourceIndex, quote || `ref-${index}`].filter(Boolean).join(':');
};

const stringField = (record: Record<string, unknown>, key: string): string => {
  const value = record[key];
  return typeof value === 'string' ? value : '';
};

const arrayCount = (record: Record<string, unknown>, key: string): number => {
  const value = record[key];
  return Array.isArray(value) ? value.length : 0;
};

const proposedEnrichment = (preview: KnowledgeEntryMergePreview): Record<string, unknown> => {
  const value = preview.proposed_entry_after.enrichment;
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
};

const payloadFingerprint = (payload: KnowledgeEntryMergePreviewRequest): string => JSON.stringify({
  parent_entry_id: payload.parent_entry_id,
  absorbed_entry_ids: payload.absorbed_entry_ids,
  parent_expected_version: payload.parent_expected_version,
  absorbed_expected_versions: payload.absorbed_expected_versions,
  merge_instruction: payload.merge_instruction,
  final_title: payload.final_title,
  final_answer: payload.final_answer,
  include: payload.include,
  exclude: payload.exclude,
  absorbed_status: payload.absorbed_status,
  rebuild_embedding: payload.rebuild_embedding,
  rerun_eval: payload.rerun_eval,
});

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
  const [include, setInclude] = useState<KnowledgeEntryMergeIncludeOptions>(defaultInclude);
  const [exclude, setExclude] = useState<MergeExcludeState>(emptyExclude);
  const [lastPreviewFingerprint, setLastPreviewFingerprint] = useState('');
  const idempotencyKey = useMemo(() => crypto.randomUUID(), []);

  const activeParentId = parentId || entries[0]?.id || '';
  const parent = entries.find((entry) => entry.id === activeParentId) ?? entries[0];
  const absorbed = entries.filter((entry) => entry.id !== activeParentId);

  const questionValues = unique(entries.flatMap((entry) => [
    ...listFromEnrichment(entry, 'questions'),
    ...listFromEnrichment(entry, 'paraphrases'),
    ...listFromEnrichment(entry, 'typo_queries'),
    ...listFromEnrichment(entry, 'colloquial_queries'),
  ]));
  const synonymValues = unique(entries.flatMap((entry) => listFromEnrichment(entry, 'synonyms')));
  const tagValues = unique(entries.flatMap((entry) => listFromEnrichment(entry, 'tags')));
  const sourceRefKeys = unique(entries.flatMap((entry) => entry.source_refs.map(sourceRefKey)));

  if (entries.length < 2) return null;

  const makePayload = (): KnowledgeEntryMergePreviewRequest => ({
    parent_entry_id: activeParentId,
    absorbed_entry_ids: absorbed.map((entry) => entry.id),
    parent_expected_version: parent?.version ?? null,
    absorbed_expected_versions: Object.fromEntries(absorbed.map((entry) => [entry.id, entry.version])),
    merge_instruction: instruction,
    final_title: finalTitle.trim() || null,
    final_answer: finalAnswer.trim() || null,
    include,
    exclude,
    absorbed_status: 'merged',
    rebuild_embedding: true,
    rerun_eval: false,
    idempotency_key: idempotencyKey,
  });

  const currentPayload = makePayload();
  const currentFingerprint = payloadFingerprint(currentPayload);
  const previewIsStale = Boolean(preview && lastPreviewFingerprint && lastPreviewFingerprint !== currentFingerprint);
  const applyDisabled = pending || !preview || previewIsStale || preview.blocking_errors.length > 0;

  const toggleExcluded = (field: keyof MergeExcludeState, value: string) => {
    setExclude((current) => {
      const values = new Set(current[field]);
      if (values.has(value)) values.delete(value);
      else values.add(value);
      return { ...current, [field]: Array.from(values) };
    });
  };

  const handlePreview = () => {
    const payload = makePayload();
    setLastPreviewFingerprint(payloadFingerprint(payload));
    onPreview(payload);
  };

  const handleApply = () => {
    onApply(makePayload());
  };

  const proposed = preview?.proposed_entry_after ?? {};
  const enrichment = preview ? proposedEnrichment(preview) : {};
  const proposedTitle = stringField(proposed, 'title') || finalTitle || parent?.title || '';
  const proposedAnswer = stringField(proposed, 'answer') || finalAnswer || parent?.answer || '';
  const proposedSourceRefs = arrayCount(proposed, 'source_refs');

  return (
    <div className="fixed inset-0 z-50 bg-black/40 p-4">
      <div className="ml-auto flex h-full max-w-6xl flex-col rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-xl">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">{t('ragEval.curation.merge.title')}</h2>
            <p className="text-sm text-[var(--text-muted)]">{t('ragEval.curation.merge.description')}</p>
          </div>
          <button type="button" onClick={onClose} className="text-sm text-[var(--text-muted)]">{t('common.actions.close')}</button>
        </div>

        <div className="mt-4 grid min-h-0 flex-1 gap-4 overflow-auto xl:grid-cols-[420px_1fr]">
          <div className="space-y-3">
            {error && <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">{error}</div>}

            <div className="rounded-xl bg-[var(--control-bg)] p-3">
              <div className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.curation.merge.parentSurvivor')}</div>
              <div className="mt-2 space-y-2">
                {entries.map((entry) => (
                  <label key={entry.id} className="flex items-start gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-2 text-sm text-[var(--text-secondary)]">
                    <input type="radio" checked={activeParentId === entry.id} onChange={() => setParentId(entry.id)} className="mt-1" />
                    <span>
                      <span className="block font-medium text-[var(--text-primary)]">{entry.title}</span>
                      <span className="text-xs text-[var(--text-muted)]">v{entry.version} · {entry.status} · {t('ragEval.curation.merge.sourceRefsCount', { count: String(entry.source_refs.length) })}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <input
              value={finalTitle}
              onChange={(event) => setFinalTitle(event.target.value)}
              placeholder={t('ragEval.curation.merge.finalTitlePlaceholder', { title: parent?.title ?? '' })}
              className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)]"
            />
            <textarea
              value={finalAnswer}
              onChange={(event) => setFinalAnswer(event.target.value)}
              placeholder={t('ragEval.curation.merge.finalAnswerPlaceholder')}
              rows={6}
              className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)]"
            />
            <textarea
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder={t('ragEval.curation.merge.instructionPlaceholder')}
              rows={3}
              className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)]"
            />

            <div className="rounded-xl bg-[var(--control-bg)] p-3">
              <div className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.curation.merge.includeGroups')}</div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-[var(--text-muted)]">
                {includeKeys.map((key) => (
                  <label key={key} className="flex items-center gap-2">
                    <input type="checkbox" checked={include[key]} onChange={(event) => setInclude({ ...include, [key]: event.target.checked })} />
                    {includeKeyLabel(key)}
                  </label>
                ))}
              </div>
            </div>

            <div className="rounded-xl bg-[var(--control-bg)] p-3 text-xs text-[var(--text-muted)]">
              <div className="font-semibold text-[var(--text-primary)]">{t('ragEval.curation.merge.retrievalConsequences')}</div>
              <div className="mt-2 space-y-1">
                <div>{t('ragEval.curation.merge.absorbedEntriesConsequence', { count: String(absorbed.length) })}</div>
                <div>{t('ragEval.curation.merge.parentEmbeddingConsequence')}</div>
                <div>{t('ragEval.curation.merge.ragEvalRerunConsequence')}</div>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <div className="rounded-xl bg-[var(--control-bg)] p-3 text-sm text-[var(--text-muted)]">
              {t('ragEval.curation.merge.selectedSummary', { selected: String(entries.length), absorbed: String(absorbed.length) })} <span className="font-semibold text-[var(--text-primary)]">{parent?.title}</span>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <div className="rounded-xl bg-[var(--control-bg)] p-3">
                <div className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.curation.merge.before')}</div>
                <div className="mt-2 space-y-2 text-sm text-[var(--text-muted)]">
                  <div className="rounded-lg bg-[var(--surface-elevated)] p-2">
                    <div className="font-medium text-[var(--text-primary)]">{t('ragEval.curation.merge.parentPrefix')} {parent?.title}</div>
                    <div>{t('ragEval.curation.merge.answerSourceRefsStats', { chars: String(parent?.answer.length ?? 0), refs: String(parent?.source_refs.length ?? 0) })}</div>
                  </div>
                  {absorbed.map((entry) => (
                    <div key={entry.id} className="rounded-lg bg-[var(--surface-elevated)] p-2">
                      <div className="font-medium text-[var(--text-primary)]">{entry.title}</div>
                      <div>{t('ragEval.curation.merge.absorbedEntryStats', { version: String(entry.version), status: entry.status, questions: String(listFromEnrichment(entry, 'questions').length), refs: String(entry.source_refs.length) })}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl bg-[var(--control-bg)] p-3">
                <div className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.curation.merge.afterPreview')}</div>
                {preview ? (
                  <div className="mt-2 space-y-2 text-sm text-[var(--text-muted)]">
                    {previewIsStale && <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-2 text-amber-600">{t('ragEval.curation.merge.previewStaleWarning')}</div>}
                    {!!preview.blocking_errors.length && <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-2 text-red-500">{t('ragEval.curation.merge.blockingPrefix')} {preview.blocking_errors.join(', ')}</div>}
                    {!!preview.warnings.length && <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-2 text-amber-600">{t('ragEval.curation.merge.warningsPrefix')} {preview.warnings.join(', ')}</div>}
                    <div className="rounded-lg bg-[var(--surface-elevated)] p-2">
                      <div className="font-medium text-[var(--text-primary)]">{proposedTitle}</div>
                      <div className="mt-1 line-clamp-5 whitespace-pre-wrap">{proposedAnswer}</div>
                      <div className="mt-2 text-xs">{t('ragEval.curation.merge.proposedStats', { sourceRefs: String(proposedSourceRefs), questions: String(arrayCount(enrichment, 'questions')), synonyms: String(arrayCount(enrichment, 'synonyms')), tags: String(arrayCount(enrichment, 'tags')) })}</div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {Object.entries(preview.included_counts).map(([key, value]) => <div key={key} className="rounded-lg bg-[var(--surface-elevated)] p-2">{t('ragEval.curation.merge.includedCount', { key, value: String(value) })}</div>)}
                    </div>
                    <details className="rounded-lg bg-[var(--surface-elevated)] p-2">
                      <summary className="cursor-pointer text-xs font-semibold text-[var(--text-primary)]">{t('ragEval.curation.merge.diagnosticsJson')}</summary>
                      <pre className="mt-2 max-h-72 overflow-auto text-xs text-[var(--text-secondary)]">{JSON.stringify(preview, null, 2)}</pre>
                    </details>
                  </div>
                ) : (
                  <div className="mt-2 rounded-lg bg-[var(--surface-elevated)] p-3 text-sm text-[var(--text-muted)]">{t('ragEval.curation.merge.previewPrompt')}</div>
                )}
              </div>
            </div>

            <div className="rounded-xl bg-[var(--control-bg)] p-3">
              <div className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.curation.merge.excludeSelectedValues')}</div>
              <div className="mt-3 space-y-3 text-xs text-[var(--text-muted)]">
                <ChipGroup title={t('ragEval.curation.merge.questionValues')} values={questionValues} disabled={!include.questions && !include.paraphrases && !include.typo_queries && !include.colloquial_queries} excluded={exclude.question_values} onToggle={(value) => toggleExcluded('question_values', value)} />
                <ChipGroup title={t('ragEval.curation.merge.synonymValues')} values={synonymValues} disabled={!include.synonyms} excluded={exclude.synonym_values} onToggle={(value) => toggleExcluded('synonym_values', value)} />
                <ChipGroup title={t('ragEval.curation.merge.tagValues')} values={tagValues} disabled={!include.tags} excluded={exclude.tag_values} onToggle={(value) => toggleExcluded('tag_values', value)} />
                <ChipGroup title={t('ragEval.curation.merge.sourceRefValues')} values={sourceRefKeys} disabled={!include.source_refs} excluded={exclude.source_ref_keys} onToggle={(value) => toggleExcluded('source_ref_keys', value)} />
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between gap-2">
          <div className="text-xs text-[var(--text-muted)]">
            {previewIsStale ? t('ragEval.curation.merge.previewStatusStale') : preview ? t('ragEval.curation.merge.previewStatusFresh') : t('ragEval.curation.merge.previewStatusRequired')}
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={handlePreview} disabled={pending} className="rounded-xl bg-[var(--control-bg)] px-4 py-2 text-sm text-[var(--text-primary)] disabled:opacity-50">{t('ragEval.curation.merge.previewButton')}</button>
            <button type="button" onClick={handleApply} disabled={applyDisabled} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{t('ragEval.curation.merge.applyButton')}</button>
          </div>
        </div>
      </div>
    </div>
  );
};

const ChipGroup: React.FC<{
  title: string;
  values: string[];
  excluded: string[];
  disabled: boolean;
  onToggle: (value: string) => void;
}> = ({ title, values, excluded, disabled, onToggle }) => (
  <div>
    <div className="mb-2 font-semibold text-[var(--text-primary)]">{title} · {values.length}</div>
    <div className="flex max-h-28 flex-wrap gap-2 overflow-auto">
      {values.length ? values.map((value) => {
        const isExcluded = excluded.includes(value);
        return (
          <button
            key={value}
            type="button"
            disabled={disabled}
            onClick={() => onToggle(value)}
            className={`rounded-full border px-2 py-1 text-left disabled:opacity-40 ${isExcluded ? 'border-red-500/40 bg-red-500/10 text-red-500 line-through' : 'border-[var(--border-subtle)] bg-[var(--surface-elevated)] text-[var(--text-secondary)]'}`}
            title={value}
          >
            {value.length > 80 ? `${value.slice(0, 80)}…` : value}
          </button>
        );
      }) : <span className="text-[var(--text-muted)]">{t('ragEval.curation.merge.noValues')}</span>}
    </div>
  </div>
);
