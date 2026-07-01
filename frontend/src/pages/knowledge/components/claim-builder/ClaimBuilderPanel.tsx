import { ClaimBuilderSectionRow } from './ClaimBuilderSectionRow';
import type { ClaimBuilderSectionRowView } from './claimBuilderTypes';

type ClaimBuilderPanelProps = {
  sectionRows: ClaimBuilderSectionRowView[];
};

export const ClaimBuilderPanel = ({ sectionRows }: ClaimBuilderPanelProps) => (
  <details
    className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3"
    open
  >
    <summary className="cursor-pointer list-none">
      <span className="flex flex-wrap items-center justify-between gap-2">
        <span>
          <span className="font-medium text-[var(--text-primary)]">
            Разделы документа
          </span>
          <span className="ml-2 text-xs text-[var(--text-muted)]">
            Claim Builder · {sectionRows.length} секц.
          </span>
        </span>
        <span className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-xs text-[var(--text-secondary)]">
          {sectionRows.length}
        </span>
      </span>
    </summary>

    <div className="mt-2 space-y-1.5">
      {sectionRows.length > 0 ? (
        sectionRows.map((row) => (
          <ClaimBuilderSectionRow key={row.queueItemId} row={row} />
        ))
      ) : (
        <div className="rounded-lg border border-dashed border-[var(--border-subtle)] px-3 py-2 text-xs text-[var(--text-muted)]">
          Разделы документа ещё не подготовлены.
        </div>
      )}
    </div>
  </details>
);
