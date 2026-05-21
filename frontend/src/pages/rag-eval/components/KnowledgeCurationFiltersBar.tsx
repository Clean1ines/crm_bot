import { t } from '@shared/i18n';
import React from 'react';

export type CurationFilter = 'all' | 'published' | 'needs_review' | 'hidden' | 'rejected' | 'merged' | 'possible_duplicates' | 'missing_source_refs' | 'missing_embedding' | 'no_retrieval_surface' | 'fallback_chunk' | 'suspicious_short' | 'changed_recently';
export type CurationSort = 'most_suspicious' | 'title' | 'status' | 'updated_at' | 'source_refs_count' | 'questions_count' | 'duplicate_group_size';

const filters: Array<[CurationFilter, string]> = [
  ['all', t('ragEval.curation.filter.all')], ['published', t('ragEval.curation.filter.published')], ['needs_review', t('ragEval.curation.filter.needsReview')], ['hidden', t('ragEval.curation.filter.hidden')], ['rejected', t('ragEval.curation.filter.rejected')], ['merged', t('ragEval.curation.filter.merged')],
  ['possible_duplicates', t('ragEval.curation.filter.possibleDuplicates')], ['missing_source_refs', t('ragEval.curation.filter.missingSourceRefs')], ['missing_embedding', t('ragEval.curation.filter.missingEmbedding')], ['no_retrieval_surface', t('ragEval.curation.filter.noRetrievalSurface')], ['fallback_chunk', t('ragEval.curation.filter.fallbackChunk')], ['suspicious_short', t('ragEval.curation.filter.suspiciousShort')], ['changed_recently', t('ragEval.curation.filter.changedRecently')],
];

export const KnowledgeCurationFiltersBar: React.FC<{
  filter: CurationFilter;
  sort: CurationSort;
  onFilterChange: (value: CurationFilter) => void;
  onSortChange: (value: CurationSort) => void;
}> = ({ filter, sort, onFilterChange, onSortChange }) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
    <div className="flex flex-wrap gap-2">
      {filters.map(([value, label]) => (
        <button key={value} type="button" onClick={() => onFilterChange(value)} className={`rounded-xl px-3 py-1.5 text-sm ${filter === value ? 'bg-[var(--accent-primary)] text-white' : 'bg-[var(--control-bg)] text-[var(--text-muted)]'}`}>{label}</button>
      ))}
    </div>
    <label className="mt-3 block text-sm text-[var(--text-muted)]">
      {t('ragEval.curation.sort.label')}
      <select value={sort} onChange={(event) => onSortChange(event.target.value as CurationSort)} className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)] sm:w-72">
        <option value="most_suspicious">{t('ragEval.curation.sort.mostSuspicious')}</option>
        <option value="title">{t('ragEval.curation.sort.title')}</option>
        <option value="status">{t('ragEval.curation.sort.status')}</option>
        <option value="updated_at">{t('ragEval.curation.sort.updatedAt')}</option>
        <option value="source_refs_count">{t('ragEval.curation.sort.sourceRefsCount')}</option>
        <option value="questions_count">{t('ragEval.curation.sort.questionsCount')}</option>
        <option value="duplicate_group_size">{t('ragEval.curation.sort.duplicateGroupSize')}</option>
      </select>
    </label>
  </section>
);
