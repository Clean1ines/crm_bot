import { ClaimBuilderSectionRow } from './ClaimBuilderSectionRow';
import type { ClaimBuilderSectionRowView } from './claimBuilderTypes';

type ClaimBuilderPanelProps = {
  sectionRows: ClaimBuilderSectionRowView[];
};

export const ClaimBuilderPanel = ({ sectionRows }: ClaimBuilderPanelProps) => (
  <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-4">
    <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
      <div>
        <h4 className="font-medium text-[var(--text-primary)]">Разделы документа</h4>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          Claim Builder извлекает факты из каждой секции документа. Попытки ИИ и
          извлечённые факты показаны внутри своей секции.
        </p>
      </div>
      <span className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-xs text-[var(--text-secondary)]">
        {sectionRows.length} секц.
      </span>
    </div>

    <div className="space-y-3">
      {sectionRows.length > 0 ? (
        sectionRows.map((row) => (
          <ClaimBuilderSectionRow key={row.queueItemId} row={row} />
        ))
      ) : (
        <div className="rounded-xl border border-dashed border-[var(--border-subtle)] p-3 text-sm text-[var(--text-muted)]">
          Разделы документа ещё не подготовлены.
        </div>
      )}
    </div>
  </div>
);
