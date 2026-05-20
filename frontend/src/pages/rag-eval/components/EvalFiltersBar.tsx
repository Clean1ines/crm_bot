import React from 'react';
import { REVIEW_FILTERS, REVIEW_SORTS, type EvalReviewFilter, type EvalReviewSort } from '../lib/ragEvalReviewFilters';

export const EvalFiltersBar: React.FC<{
  filter: EvalReviewFilter;
  sort: EvalReviewSort;
  onFilterChange: (value: EvalReviewFilter) => void;
  onSortChange: (value: EvalReviewSort) => void;
}> = ({ filter, sort, onFilterChange, onSortChange }) => (
  <div className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
    <div className="flex flex-wrap gap-2">
      {REVIEW_FILTERS.map((item) => (
        <button key={item.id} type="button" onClick={() => onFilterChange(item.id)} className={`rounded-full px-3 py-1.5 text-sm font-medium ${filter === item.id ? 'bg-[var(--accent-primary)] text-white' : 'bg-[var(--control-bg)] text-[var(--text-secondary)]'}`}>{item.label}</button>
      ))}
    </div>
    <label className="mt-3 block max-w-sm text-sm text-[var(--text-secondary)]">
      Сортировка
      <select value={sort} onChange={(event) => onSortChange(event.target.value as EvalReviewSort)} className="mt-1 w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none">
        {REVIEW_SORTS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select>
    </label>
  </div>
);
