import React from 'react';

export type CurationFilter = 'all' | 'published' | 'needs_review' | 'hidden' | 'rejected' | 'merged' | 'possible_duplicates' | 'missing_source_refs' | 'missing_embedding' | 'no_retrieval_surface' | 'fallback_chunk' | 'suspicious_short' | 'changed_recently';
export type CurationSort = 'most_suspicious' | 'title' | 'status' | 'updated_at' | 'source_refs_count' | 'questions_count' | 'duplicate_group_size';

const filters: Array<[CurationFilter, string]> = [
  ['all', 'Все'], ['published', 'Published'], ['needs_review', 'Needs review'], ['hidden', 'Hidden'], ['rejected', 'Rejected'], ['merged', 'Merged'],
  ['possible_duplicates', 'Duplicates'], ['missing_source_refs', 'Без source refs'], ['missing_embedding', 'Без embedding'], ['no_retrieval_surface', 'Нет retrieval row'], ['fallback_chunk', 'Fallback'], ['suspicious_short', 'Короткие'], ['changed_recently', 'Недавно изменены'],
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
      Сортировка
      <select value={sort} onChange={(event) => onSortChange(event.target.value as CurationSort)} className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] px-3 py-2 text-[var(--text-primary)] sm:w-72">
        <option value="most_suspicious">Самые подозрительные</option>
        <option value="title">Title</option>
        <option value="status">Status</option>
        <option value="updated_at">Updated at</option>
        <option value="source_refs_count">Source refs count</option>
        <option value="questions_count">Questions count</option>
        <option value="duplicate_group_size">Duplicate group size</option>
      </select>
    </label>
  </section>
);
