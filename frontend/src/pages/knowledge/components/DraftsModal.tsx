import React, { useMemo } from 'react';
import { ChevronDown, Loader2, Search } from 'lucide-react';

import { type KnowledgeAnswerDraft, type KnowledgeAnswerDraftsResponse } from '@shared/api/modules/knowledge';
import { t } from '@shared/i18n';
import { BaseModal } from '@shared/ui';

const formatPreviewScore = (value: number): string => (
  Number.isFinite(value) ? value.toFixed(3) : '0.000'
);

const SURFACE_KIND_LABELS: Record<string, string> = {
  umbrella: 'Зонтичная',
  child: 'Дочерняя',
  pricing: 'Цена',
  refund: 'Возврат',
  payment: 'Оплата',
  integration: 'Интеграция',
  channel: 'Канал',
  document_upload: 'Документы',
  curation: 'Курация',
  retrieval_quality: 'Качество поиска',
  handoff: 'Передача менеджеру',
  service_limits: 'Ограничения',
};

const surfaceKindLabel = (kind: string | null | undefined): string => {
  if (!kind) return 'Surface';
  return SURFACE_KIND_LABELS[kind] || kind;
};


const draftTitle = (draft: KnowledgeAnswerDraft): string => (
  draft.canonical_question.trim() || draft.title.trim() || t('knowledge.drafts.untitled')
);

const draftSearchText = (draft: KnowledgeAnswerDraft): string => [
  draft.title,
  draft.canonical_question,
  draft.answer,
  ...draft.question_variants,
  ...draft.synonyms,
  ...draft.tags,
  ...draft.source_refs.map((ref) => ref.quote),
].join(' ').toLowerCase();

const draftSourceChunkIndexes = (draft: KnowledgeAnswerDraft): number[] => {
  const indexes = new Set<number>();
  for (const index of draft.source_chunk_indexes) {
    indexes.add(index);
  }
  for (const ref of draft.source_refs) {
    if (typeof ref.source_index === 'number' && Number.isFinite(ref.source_index)) {
      indexes.add(ref.source_index);
    }
  }
  return [...indexes].sort((left, right) => left - right);
};

const DraftDetailRow: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
    <div className="text-sm leading-relaxed text-[var(--text-primary)]">{children}</div>
  </div>
);

export const DraftsModal: React.FC<{
  documentName: string;
  response: KnowledgeAnswerDraftsResponse | undefined;
  isLoading: boolean;
  filter: string;
  expandedDraftIds: string[];
  onFilterChange: (value: string) => void;
  onToggleDraft: (draftId: string) => void;
  isDebugMode?: boolean;
  onClose: () => void;
}> = ({
  documentName,
  response,
  isLoading,
  filter,
  expandedDraftIds,
  onFilterChange,
  onToggleDraft,
  isDebugMode = false, onClose,
}) => {
  const normalizedFilter = filter.trim().toLowerCase();
  const expandedSet = useMemo(() => new Set(expandedDraftIds), [expandedDraftIds]);
  const filteredDrafts = useMemo(() => {
    const drafts = response?.drafts ?? [];
    if (!normalizedFilter) return drafts;
    return drafts.filter((draft) => draftSearchText(draft).includes(normalizedFilter));
  }, [normalizedFilter, response?.drafts]);

  return (
    <BaseModal
      isOpen
      onClose={onClose}
      title={t('knowledge.drafts.modalTitle')}
      cancelLabel={t('common.actions.close')}
      maxWidthClassName="max-w-4xl"
    >
      <div className="-mt-2 max-h-[72vh] overflow-hidden text-sm text-[var(--text-primary)]">
        <div className="mb-3 text-xs text-[var(--text-muted)]">{documentName}</div>
        <div className="relative mb-4">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="text"
            value={filter}
            onChange={(event) => onFilterChange(event.target.value)}
            placeholder={t('knowledge.drafts.searchPlaceholder')}
            className="min-h-10 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/15"
          />
        </div>

        <div className="max-h-[56vh] overflow-y-auto pr-1">
          {isLoading && !response && (
            <div className="flex items-center gap-2 rounded-xl bg-[var(--surface-secondary)] p-4 text-[var(--text-muted)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{t('knowledge.drafts.loading')}</span>
            </div>
          )}

          {response && response.drafts.length === 0 && (
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-[var(--text-muted)]">
              {t('knowledge.drafts.empty')}
            </div>
          )}

          {response && response.drafts.length > 0 && filteredDrafts.length === 0 && (
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-[var(--text-muted)]">
              {t('knowledge.drafts.noFilterResults')}
            </div>
          )}

          <div className="space-y-2">
            {filteredDrafts.map((draft) => {
              const isExpanded = expandedSet.has(draft.id);
              const sourceChunkIndexes = draftSourceChunkIndexes(draft);

              return (
                <div key={draft.id} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)]">
                  <button
                    type="button"
                    onClick={() => onToggleDraft(draft.id)}
                    aria-expanded={isExpanded}
                    className="flex w-full items-start justify-between gap-3 px-3 py-3 text-left transition-colors hover:bg-[var(--control-bg)] focus:outline-none focus:ring-2 focus:ring-inset focus:ring-[var(--accent-primary)]/25"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-[var(--text-primary)]" title={draftTitle(draft)}>{draftTitle(draft)}</div>
                      <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-muted)]">
                        {draft.status && <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">{draft.status}</span>}
                        {draft.surface_kind && <span className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-0.5 text-[var(--accent-primary)]">{surfaceKindLabel(draft.surface_kind)}</span>}
                        {isDebugMode && draft.batch_index !== null && <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">batch {draft.batch_index}</span>}
                        {isDebugMode && sourceChunkIndexes.length > 0 && (
                          <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                            chunks {sourceChunkIndexes.join(', ')}
                          </span>
                        )}
                      </div>
                    </div>
                    <ChevronDown className={`mt-0.5 h-4 w-4 shrink-0 text-[var(--text-muted)] transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                  </button>

                  {isExpanded && (
                    <div className="space-y-4 border-t border-[var(--border-subtle)] px-3 py-3">
                      <DraftDetailRow label={t('knowledge.drafts.fields.answer')}>
                        <div className="whitespace-pre-wrap">{draft.answer || '—'}</div>
                      </DraftDetailRow>

                      {draft.question_variants.length > 0 && (
                        <DraftDetailRow label={t('knowledge.drafts.fields.questions')}>
                          <ul className="list-disc space-y-1 pl-5">
                            {draft.question_variants.map((question) => <li key={question}>{question}</li>)}
                          </ul>
                        </DraftDetailRow>
                      )}

                      {(draft.synonyms.length > 0 || draft.tags.length > 0) && (
                        <DraftDetailRow label={t('knowledge.drafts.fields.synonymsTags')}>
                          <div className="flex flex-wrap gap-1.5">
                            {[...draft.synonyms, ...draft.tags].map((item) => (
                              <span key={item} className="rounded-full bg-[var(--control-bg)] px-2 py-1 text-xs text-[var(--text-muted)]">{item}</span>
                            ))}
                          </div>
                        </DraftDetailRow>
                      )}

                      {draft.source_refs.length > 0 && (
                        <DraftDetailRow label={t('knowledge.drafts.fields.sources')}>
                          <div className="space-y-2">
                            {draft.source_refs.map((ref, index) => (
                              <div key={`${draft.id}-${index}-${ref.source_chunk_id || ref.source_index || 'source'}`} className="rounded-lg bg-[var(--control-bg)] p-2">
                                <div className="whitespace-pre-wrap">{ref.quote}</div>
                                <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-muted)]">
                                  {isDebugMode && typeof ref.source_index === 'number' && <span>chunk {ref.source_index}</span>}
                                  {isDebugMode && ref.source_chunk_id && <span>{ref.source_chunk_id}</span>}
                                  {typeof ref.confidence === 'number' && <span>{formatPreviewScore(ref.confidence)}</span>}
                                </div>
                              </div>
                            ))}
                          </div>
                        </DraftDetailRow>
                      )}

                      {(draft.status || draft.rejection_reason || draft.is_retrieval_surface || draft.answer_scope || draft.short_answer || (isDebugMode && (draft.batch_index !== null || draft.fragment_index !== null || sourceChunkIndexes.length > 0))) && (
                        <DraftDetailRow label={t('knowledge.drafts.fields.metadata')}>
                          <div className="flex flex-wrap gap-1.5 text-xs text-[var(--text-muted)]">
                            {draft.status && <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">status: {draft.status}</span>}
                            {draft.rejection_reason && <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">reason: {draft.rejection_reason}</span>}
                            {draft.is_retrieval_surface && <span className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-1 text-[var(--accent-primary)]">Retrieval Surface</span>}
                            {draft.surface_kind && <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">surface_kind: {draft.surface_kind}</span>}
                            {draft.answer_scope && <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">Область ответа: {draft.answer_scope}</span>}
                            {draft.parent_surface_keys && draft.parent_surface_keys.length > 0 && <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">Родительские поверхности: {draft.parent_surface_keys.join(', ')}</span>}
                            {draft.child_surface_keys && draft.child_surface_keys.length > 0 && <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">Дочерние поверхности: {draft.child_surface_keys.join(', ')}</span>}
                            {draft.short_answer && <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">Короткий ответ: {draft.short_answer}</span>}
                            {isDebugMode && draft.batch_index !== null && <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">batch_index: {draft.batch_index}</span>}
                            {isDebugMode && draft.fragment_index !== null && <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">fragment_index: {draft.fragment_index}</span>}
                            {isDebugMode && sourceChunkIndexes.length > 0 && <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">source_chunk_indexes: {sourceChunkIndexes.join(', ')}</span>}
                          </div>
                        </DraftDetailRow>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </BaseModal>
  );
};

