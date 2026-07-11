import React from 'react';

import type {
  WorkbenchRagEvalRetrievalClassificationCounts,
  WorkbenchRagEvalRunSummary,
} from '@shared/api/modules/ragEval';

const classificationLabels: ReadonlyArray<
  readonly [keyof WorkbenchRagEvalRetrievalClassificationCounts, string]
> = [
  ['pass_strong', 'PASS_STRONG'],
  ['pass_weak', 'PASS_WEAK'],
  ['confusion', 'CONFUSION'],
  ['miss', 'MISS'],
  ['existing_alias_retrieval_failure', 'EXISTING_ALIAS_RETRIEVAL_FAILURE'],
];

const phaseLabel = (phase: string | null | undefined): string => {
  if (phase === 'retrieval_evaluation') return 'Оценка retrieval';
  return phase || '—';
};

export const RagEvalRetrievalProgress: React.FC<{
  run: WorkbenchRagEvalRunSummary;
}> = ({ run }) => {
  const progress = run.retrieval_progress;
  const completed = progress?.completed ?? run.completed_questions;
  const total = progress?.total ?? run.total_questions;
  const counts = progress?.classification_counts;

  return (
    <section className="rounded-xl bg-[var(--control-bg)] p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
            Текущая фаза
          </div>
          <div className="mt-1 font-semibold text-[var(--text-primary)]">
            {phaseLabel(run.current_phase)}
          </div>
        </div>
        <div className="text-sm text-[var(--text-secondary)]">
          Retrieval: <span className="font-semibold text-[var(--text-primary)]">{completed} / {total}</span>
        </div>
      </div>

      {counts ? (
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {classificationLabels.map(([key, label]) => (
            <div key={key} className="rounded-lg bg-[var(--surface-elevated)] p-3">
              <div className="break-words text-[11px] text-[var(--text-muted)]">{label}</div>
              <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
                {counts[key]}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3 text-xs text-[var(--text-muted)]">
          Классификация ещё не сохранена backend.
        </div>
      )}
    </section>
  );
};
