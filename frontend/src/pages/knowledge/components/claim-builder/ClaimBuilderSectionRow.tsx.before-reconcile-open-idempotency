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
  <details className={`rounded-lg border px-3 py-2 ${claimBuilderSectionRowTone(row.status)}`}>
    <summary className="cursor-pointer list-none">
      <span className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <span className="min-w-0">
          <span className="font-medium text-[var(--text-primary)]">
            Раздел {formatClaimBuilderNumber(row.sectionIndex + 1)}
          </span>
          <span className="ml-2 text-[var(--text-muted)]">
            {row.title}
          </span>
        </span>

        <span className="flex flex-wrap items-center gap-2">
          <span className={`text-xs ${claimBuilderSectionStatusTone(row.status)}`}>
            {claimBuilderSectionStatusLabel(row.status)}
            {row.attemptCount > 0
              ? ` · попыток: ${formatClaimBuilderNumber(row.attemptCount)}`
              : ''}
          </span>

          {row.userActionRequired && (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300">
              Нужно решение
            </span>
          )}
        </span>
      </span>
    </summary>

    <div className="mt-2 space-y-2">
      {row.sourceUnit ? (
        <div>
          <div className="mb-1 font-medium text-[var(--text-primary)]">
            {row.sourceUnit.title}
          </div>
          <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded bg-[var(--surface-elevated)] p-2 text-xs leading-relaxed text-[var(--text-secondary)]">
            {row.sourceUnit.content}
          </pre>
        </div>
      ) : (
        <div className="text-xs text-[var(--text-muted)]">
          Текст раздела ещё не загружен.
        </div>
      )}

      {row.errorKind && (
        <div className="text-xs text-amber-700 dark:text-amber-300">
          Ошибка: {row.errorKind}
        </div>
      )}

      {row.blockedReason && (
        <div className="text-xs text-amber-700 dark:text-amber-300">
          Причина блокировки: {row.blockedReason}
        </div>
      )}

      <div className="space-y-1.5">
        {row.attempts.length > 0 ? (
          row.attempts.map((attempt) => (
            <ClaimBuilderAttemptRow key={attempt.nodeRunId} attempt={attempt} />
          ))
        ) : (
          <div className="rounded border border-dashed border-[var(--border-subtle)] px-2 py-1.5 text-xs text-[var(--text-muted)]">
            Попытки обработки этой секции ещё не начались.
          </div>
        )}
      </div>
    </div>
  </details>
);
