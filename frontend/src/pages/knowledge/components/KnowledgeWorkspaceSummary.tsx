import React from 'react';

import { t } from '@shared/i18n';

import { type KnowledgeWorkspacePrimaryActionKind, type KnowledgeWorkspaceSummaryVm } from '../viewModel/workspaceSummary';

const toneClassName = (tone: KnowledgeWorkspaceSummaryVm['counters'][number]['tone']): string => {
  if (tone === 'success') return 'bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]';
  if (tone === 'warning') return 'bg-[var(--accent-warning-bg)] text-[var(--accent-warning)]';
  if (tone === 'danger') return 'bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]';
  return 'bg-[var(--control-bg)] text-[var(--text-muted)]';
};

export const KnowledgeWorkspaceSummary: React.FC<{
  summary: KnowledgeWorkspaceSummaryVm;
  onPrimaryAction: (kind: KnowledgeWorkspacePrimaryActionKind) => void;
}> = ({ summary, onPrimaryAction }) => (
  <section className="mb-6 rounded-2xl bg-[var(--surface-elevated)] p-4 sm:p-5">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 className="text-base font-semibold text-[var(--text-primary)] sm:text-lg">{t(summary.headlineKey as never)}</h2>
        <p className="mt-1 text-sm text-[var(--text-muted)]">{t(summary.descriptionKey as never)}</p>
      </div>
      <button
        type="button"
        onClick={() => onPrimaryAction(summary.primaryAction.kind)}
        className="w-fit rounded-full bg-[var(--accent-primary)]/10 px-3 py-1.5 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20"
      >
        {t(summary.primaryAction.labelKey as never)}
      </button>
    </div>

    <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
      {summary.counters.slice(0, 4).map((counter) => (
        <span key={counter.id} className={`rounded-full px-2 py-0.5 ${toneClassName(counter.tone)}`}>
          {t(counter.labelKey as never)}: {counter.value}
        </span>
      ))}
    </div>
  </section>
);
