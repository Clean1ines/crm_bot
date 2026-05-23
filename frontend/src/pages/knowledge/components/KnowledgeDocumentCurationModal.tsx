import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';

import { BaseModal } from '@shared/ui';
import { t } from '@shared/i18n';
import {
  knowledgeCurationApi,
  type KnowledgeCurationEntry,
  type KnowledgeEntryMergeIncludeOptions,
  type KnowledgeEntryMergePreview,
} from '@shared/api/modules/knowledgeCuration';
import { getErrorMessage } from '@shared/api/core/errors';

const DEFAULT_INCLUDE: KnowledgeEntryMergeIncludeOptions = {
  answers: true,
  questions: true,
  paraphrases: true,
  synonyms: true,
  typo_queries: true,
  colloquial_queries: true,
  tags: true,
  retrieval_guards: true,
  source_refs: true,
  metadata: true,
};

const mergeRequestId = (): string => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `merge-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const runtimeEntries = (entries: KnowledgeCurationEntry[]): KnowledgeCurationEntry[] => (
  entries.filter((entry) => (
    entry.status === 'published'
    && entry.visibility === 'runtime'
    && entry.runtime_eligible
  ))
);

const entrySearchText = (entry: KnowledgeCurationEntry): string => {
  const enrichment = entry.enrichment || {};
  const questions = Array.isArray(enrichment.questions)
    ? enrichment.questions.filter((item): item is string => typeof item === 'string')
    : [];
  return [
    entry.title,
    entry.answer,
    entry.entry_kind,
    entry.status,
    ...questions,
  ].join(' ').toLowerCase();
};

const entryQuestionCount = (entry: KnowledgeCurationEntry): number => {
  const questions = entry.enrichment.questions;
  return Array.isArray(questions) ? questions.length : 0;
};

const defaultParentId = (entries: KnowledgeCurationEntry[]): string | null => {
  if (entries.length === 0) return null;
  return [...entries].sort((left, right) => (
    (right.answer.length + entryQuestionCount(right) * 24 + right.source_refs.length * 18)
    - (left.answer.length + entryQuestionCount(left) * 24 + left.source_refs.length * 18)
  ))[0].id;
};

const previewAnswer = (preview: KnowledgeEntryMergePreview | null): string => {
  if (!preview) return '';
  const value = preview.proposed_entry_after.answer;
  return typeof value === 'string' ? value : '';
};

export const KnowledgeDocumentCurationModal: React.FC<{
  projectId: string;
  documentId: string;
  documentName: string;
  onClose: () => void;
}> = ({ projectId, documentId, documentName, onClose }) => {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [parentId, setParentId] = useState<string | null>(null);
  const [mergeInstruction, setMergeInstruction] = useState('');
  const [preview, setPreview] = useState<KnowledgeEntryMergePreview | null>(null);

  const curationQuery = useQuery({
    queryKey: ['knowledge-document-curation', projectId, documentId],
    queryFn: async () => {
      const { data } = await knowledgeCurationApi.getDocumentCuration(projectId, documentId);
      return data;
    },
  });

  const entries = useMemo(
    () => curationQuery.data?.entries ?? [],
    [curationQuery.data?.entries],
  );
  const duplicateGroups = curationQuery.data?.duplicate_groups ?? [];
  const mergeableEntries = useMemo(() => runtimeEntries(entries), [entries]);
  const filteredEntries = useMemo(() => {
    const normalized = filter.trim().toLowerCase();
    if (!normalized) return mergeableEntries;
    return mergeableEntries.filter((entry) => entrySearchText(entry).includes(normalized));
  }, [filter, mergeableEntries]);

  const selectedEntries = selectedIds
    .map((id) => mergeableEntries.find((entry) => entry.id === id))
    .filter((entry): entry is KnowledgeCurationEntry => Boolean(entry));
  const effectiveParentId = parentId && selectedIds.includes(parentId)
    ? parentId
    : defaultParentId(selectedEntries);
  const canPreview = selectedIds.length >= 2 && selectedIds.length <= 12 && Boolean(effectiveParentId);
  const parentEntry = effectiveParentId
    ? selectedEntries.find((entry) => entry.id === effectiveParentId) ?? null
    : null;

  const buildMergePayload = () => {
    if (!effectiveParentId) throw new Error('missing_parent_entry_id');
    const absorbedIds = selectedIds.filter((id) => id !== effectiveParentId);
    const versionById = selectedEntries.reduce<Record<string, number>>((acc, entry) => {
      acc[entry.id] = entry.version;
      return acc;
    }, {});

    return {
      parent_entry_id: effectiveParentId,
      absorbed_entry_ids: absorbedIds,
      parent_expected_version: versionById[effectiveParentId] ?? null,
      absorbed_expected_versions: absorbedIds.reduce<Record<string, number>>((acc, id) => {
        acc[id] = versionById[id] ?? 0;
        return acc;
      }, {}),
      merge_instruction: mergeInstruction,
      final_title: null,
      final_answer: null,
      include: DEFAULT_INCLUDE,
      exclude: {
        question_values: [],
        synonym_values: [],
        tag_values: [],
        source_ref_keys: [],
        metadata_keys: [],
      },
      absorbed_status: 'merged' as const,
      rebuild_embedding: true,
      rerun_eval: false,
      idempotency_key: mergeRequestId(),
    };
  };

  const previewMutation = useMutation({
    mutationFn: async () => {
      const { data } = await knowledgeCurationApi.previewMerge(projectId, documentId, buildMergePayload());
      return data.preview;
    },
    onSuccess: (nextPreview) => {
      setPreview(nextPreview);
      toast.success(t('knowledge.curation.feedback.previewReady'));
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t('knowledge.curation.feedback.previewFailed')));
    },
  });

  const applyMutation = useMutation({
    mutationFn: async () => {
      const { data } = await knowledgeCurationApi.applyMerge(projectId, documentId, buildMergePayload());
      return data;
    },
    onSuccess: async () => {
      toast.success(t('knowledge.curation.feedback.mergeApplied'));
      setPreview(null);
      setSelectedIds([]);
      setParentId(null);
      await queryClient.invalidateQueries({ queryKey: ['knowledge-document-curation', projectId, documentId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t('knowledge.curation.feedback.mergeFailed')));
    },
  });

  const toggleEntry = (entry: KnowledgeCurationEntry): void => {
    setPreview(null);
    setSelectedIds((current) => {
      if (current.includes(entry.id)) {
        const next = current.filter((id) => id !== entry.id);
        if (parentId === entry.id) setParentId(null);
        return next;
      }
      return [...current, entry.id].slice(0, 12);
    });
  };

  const applyDuplicateGroup = (entryIds: string[]): void => {
    const knownIds = entryIds.filter((id) => mergeableEntries.some((entry) => entry.id === id)).slice(0, 12);
    setSelectedIds(knownIds);
    setParentId(defaultParentId(knownIds.map((id) => mergeableEntries.find((entry) => entry.id === id)).filter((entry): entry is KnowledgeCurationEntry => Boolean(entry))));
    setPreview(null);
  };

  return (
    <BaseModal
      isOpen
      onClose={onClose}
      title={t('knowledge.curation.title')}
      maxWidthClassName="max-w-6xl"
    >
      <div className="space-y-4">
        <div className="rounded-xl bg-[var(--surface-secondary)] p-3">
          <div className="text-sm font-semibold text-[var(--text-primary)]">{documentName}</div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-[var(--text-muted)]">
            <span>{t('knowledge.curation.summary.entries')}: {curationQuery.data?.summary.total_entries ?? 0}</span>
            <span>{t('knowledge.curation.summary.runtime')}: {curationQuery.data?.summary.published_runtime_entries ?? 0}</span>
            <span>{t('knowledge.curation.summary.duplicates')}: {duplicateGroups.length}</span>
            <span>{t('knowledge.curation.summary.merged')}: {curationQuery.data?.summary.merged_entries ?? 0}</span>
          </div>
        </div>

        {duplicateGroups.length > 0 && (
          <section className="rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
              {t('knowledge.curation.duplicateGroups')}
            </div>
            <div className="flex flex-wrap gap-2">
              {duplicateGroups.slice(0, 8).map((group) => (
                <button
                  key={group.group_id}
                  type="button"
                  onClick={() => applyDuplicateGroup(group.entry_ids)}
                  className="rounded-lg bg-[var(--control-bg)] px-3 py-2 text-left text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]"
                >
                  <div className="font-medium text-[var(--text-primary)]">{group.reason}</div>
                  <div>{group.entry_ids.length} entries · {group.score.toFixed(2)}</div>
                </button>
              ))}
            </div>
          </section>
        )}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section className="space-y-3">
            <input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder={t('knowledge.curation.searchPlaceholder')}
              className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
            />

            {curationQuery.isLoading ? (
              <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
                {t('knowledge.curation.loading')}
              </div>
            ) : filteredEntries.length === 0 ? (
              <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
                {t('knowledge.curation.empty')}
              </div>
            ) : (
              <div className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
                {filteredEntries.map((entry) => {
                  const selected = selectedIds.includes(entry.id);
                  const isParent = effectiveParentId === entry.id;
                  return (
                    <div
                      key={entry.id}
                      className={`rounded-xl border p-3 transition-colors ${
                        selected ? 'border-[var(--accent-primary)] bg-[var(--accent-primary)]/5' : 'border-[var(--border-subtle)] bg-[var(--surface-secondary)]'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <button
                          type="button"
                          onClick={() => toggleEntry(entry)}
                          className="min-w-0 flex-1 text-left"
                        >
                          <div className="truncate text-sm font-semibold text-[var(--text-primary)]">{entry.title}</div>
                          <div className="mt-1 line-clamp-3 text-sm text-[var(--text-muted)]">{entry.answer}</div>
                          <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-muted)]">
                            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">{entry.entry_kind}</span>
                            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">v{entry.version}</span>
                            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">questions: {entryQuestionCount(entry)}</span>
                            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">sources: {entry.source_refs.length}</span>
                          </div>
                        </button>
                        {selected && (
                          <button
                            type="button"
                            onClick={() => {
                              setParentId(entry.id);
                              setPreview(null);
                            }}
                            className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                              isParent
                                ? 'bg-[var(--accent-primary)] text-white'
                                : 'bg-[var(--control-bg)] text-[var(--text-muted)]'
                            }`}
                          >
                            {isParent ? t('knowledge.curation.parent') : t('knowledge.curation.makeParent')}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <aside className="space-y-3 rounded-xl bg-[var(--surface-secondary)] p-3">
            <div>
              <div className="text-sm font-semibold text-[var(--text-primary)]">
                {t('knowledge.curation.selectionTitle')}
              </div>
              <div className="mt-1 text-xs text-[var(--text-muted)]">
                {t('knowledge.curation.selectionCount', { count: selectedIds.length })}
              </div>
            </div>

            {parentEntry && (
              <div className="rounded-lg bg-[var(--control-bg)] p-3 text-xs text-[var(--text-muted)]">
                <div className="mb-1 font-medium text-[var(--text-primary)]">
                  {t('knowledge.curation.parent')}: {parentEntry.title}
                </div>
                <div className="line-clamp-3">{parentEntry.answer}</div>
              </div>
            )}

            <textarea
              value={mergeInstruction}
              onChange={(event) => setMergeInstruction(event.target.value)}
              placeholder={t('knowledge.curation.instructionPlaceholder')}
              className="min-h-24 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
            />

            <button
              type="button"
              disabled={!canPreview || previewMutation.isPending}
              onClick={() => previewMutation.mutate()}
              className="w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {previewMutation.isPending ? t('knowledge.curation.previewMerge') : t('knowledge.curation.previewMerge')}
            </button>

            {preview && (
              <div className="space-y-3 rounded-lg bg-[var(--control-bg)] p-3">
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  {t('knowledge.curation.previewTitle')}
                </div>
                {preview.blocking_errors.length > 0 && (
                  <div className="rounded-lg bg-[var(--accent-danger-bg)] p-2 text-xs text-[var(--accent-danger-text)]">
                    {preview.blocking_errors.join(', ')}
                  </div>
                )}
                {preview.warnings.length > 0 && (
                  <div className="rounded-lg bg-[var(--accent-warning-bg)] p-2 text-xs text-[var(--accent-warning)]">
                    {preview.warnings.join(', ')}
                  </div>
                )}
                <div className="max-h-48 overflow-y-auto whitespace-pre-wrap text-xs text-[var(--text-muted)]">
                  {previewAnswer(preview) || t('knowledge.curation.previewEmpty')}
                </div>
                <button
                  type="button"
                  disabled={preview.blocking_errors.length > 0 || applyMutation.isPending}
                  onClick={() => applyMutation.mutate()}
                  className="w-full rounded-lg bg-[var(--accent-primary)] px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {applyMutation.isPending ? t('knowledge.curation.applyMerge') : t('knowledge.curation.applyMerge')}
                </button>
              </div>
            )}
          </aside>
        </div>
      </div>
    </BaseModal>
  );
};
