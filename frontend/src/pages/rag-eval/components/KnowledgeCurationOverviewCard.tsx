import React from 'react';
import { AlertTriangle, CheckCircle2, GitMerge, SearchX } from 'lucide-react';
import type { KnowledgeCurationSummary } from '../../../shared/api/modules/knowledgeCuration';

export const KnowledgeCurationOverviewCard: React.FC<{ summary: KnowledgeCurationSummary }> = ({ summary }) => {
  const metrics = [
    ['Всего entries', summary.total_entries],
    ['Published/runtime', summary.published_runtime_entries],
    ['Needs review', summary.needs_review_entries],
    ['Hidden/rejected/merged', summary.hidden_entries + summary.rejected_entries + summary.merged_entries],
    ['Duplicate groups', summary.duplicate_group_count],
    ['Без source refs', summary.entries_without_source_refs],
    ['Нет retrieval row', summary.entries_missing_retrieval_surface],
    ['Suspicious', summary.suspicious_entries],
  ];

  return (
    <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Курация знаний</h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">{summary.document_name || summary.document_id}</p>
        </div>
        <div className={`inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm ${summary.document_processing_active ? 'bg-amber-500/10 text-amber-600' : 'bg-emerald-500/10 text-emerald-600'}`}>
          {summary.document_processing_active ? <AlertTriangle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
          {summary.document_processing_active ? 'Документ ещё обрабатывается' : 'Готово к ручной проверке'}
        </div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-xl bg-[var(--control-bg)] p-3">
            <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
            <div className="mt-1 text-xl font-semibold text-[var(--text-primary)]">{String(value)}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs text-[var(--text-muted)]">
        <span className="inline-flex items-center gap-1"><GitMerge className="h-3.5 w-3.5" /> Merge не удаляет absorbed entries физически.</span>
        <span className="inline-flex items-center gap-1"><SearchX className="h-3.5 w-3.5" /> Hidden/rejected/merged исключаются из runtime retrieval.</span>
      </div>
    </section>
  );
};
