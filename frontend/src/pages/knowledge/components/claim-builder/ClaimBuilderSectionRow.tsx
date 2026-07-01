import {
  claimBuilderSectionRowTone,
  claimBuilderSectionStatusLabel,
  claimBuilderSectionStatusTone,
  formatClaimBuilderNumber,
} from './claimBuilderLabels';
import { ClaimBuilderAttemptRow } from './ClaimBuilderAttemptRow';
import type { ClaimBuilderSectionRowView } from './claimBuilderTypes';

type ClaimBuilderSectionRowProps = {
  row: ClaimBuilderSectionRowView;
};

export const ClaimBuilderSectionRow = ({ row }: ClaimBuilderSectionRowProps) => (
  <div className={`rounded-xl border p-3 ${claimBuilderSectionRowTone(row.status)}`}>
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0">
        <div className="text-sm font-medium text-[var(--text-primary)]">
          Раздел {formatClaimBuilderNumber(row.sectionIndex + 1)} · {row.title}
        </div>
        <div className={`mt-1 text-xs ${claimBuilderSectionStatusTone(row.status)}`}>
          {claimBuilderSectionStatusLabel(row.status)}
          {row.attemptCount > 0
            ? ` · попыток: ${formatClaimBuilderNumber(row.attemptCount)}`
            : ''}
        </div>
      </div>

      {row.userActionRequired && (
        <span className="rounded-full bg-amber-500/10 px-2 py-1 text-xs text-amber-700 dark:text-amber-300">
          Нужно решение
        </span>
      )}
    </div>

    {row.text && (
      <p className="mt-3 whitespace-pre-wrap rounded-lg bg-[var(--surface-elevated)] p-3 text-xs leading-relaxed text-[var(--text-secondary)]">
        {row.text}
      </p>
    )}

    {row.errorKind && (
      <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
        Ошибка: {row.errorKind}
      </p>
    )}

    {row.blockedReason && (
      <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
        Причина блокировки: {row.blockedReason}
      </p>
    )}

    <div className="mt-3 space-y-2">
      {row.attempts.length > 0 ? (
        row.attempts.map((attempt) => (
          <ClaimBuilderAttemptRow key={attempt.nodeRunId} attempt={attempt} />
        ))
      ) : (
        <div className="rounded-lg border border-dashed border-[var(--border-subtle)] p-3 text-xs text-[var(--text-muted)]">
          Попытки обработки этой секции ещё не начались.
        </div>
      )}
    </div>
  </div>
);
