import React, { useMemo } from 'react';
import { ChevronDown, Loader2, Search } from 'lucide-react';

import { type KnowledgeSourceUnit, type KnowledgeSourceUnitsResponse } from '@shared/api/modules/knowledge';
import { t } from '@shared/i18n';
import { BaseModal } from '@shared/ui';

const sourceUnitTitle = (sourceUnit: KnowledgeSourceUnit): string => (
  sourceUnit.title.trim() || t('knowledge.sourceUnits.fallbackTitle', { index: String(sourceUnit.source_index) })
);

const sourceUnitSearchText = (sourceUnit: KnowledgeSourceUnit): string => [
  sourceUnit.title,
  sourceUnit.content,
  ...sourceUnit.draft_titles,
  JSON.stringify(sourceUnit.metadata || {}),
].join(' ').toLowerCase();

const formatNumber = (value: number): string => {
  if (!Number.isFinite(value)) return '0';
  return new Intl.NumberFormat().format(value);
};

const DraftDetailRow: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
    <div className="text-sm leading-relaxed text-[var(--text-primary)]">{children}</div>
  </div>
);

export const SourceUnitsModal: React.FC<{
  documentName: string;
  response: KnowledgeSourceUnitsResponse | undefined;
  isLoading: boolean;
  filter: string;
  expandedSourceUnitIds: string[];
  onFilterChange: (value: string) => void;
  onToggleSourceUnit: (sourceUnitId: string) => void;
  onClose: () => void;
}> = ({
  documentName,
  response,
  isLoading,
  filter,
  expandedSourceUnitIds,
  onFilterChange,
  onToggleSourceUnit,
  onClose,
}) => {
  const normalizedFilter = filter.trim().toLowerCase();
  const expandedSet = useMemo(() => new Set(expandedSourceUnitIds), [expandedSourceUnitIds]);
  const filteredSourceUnits = useMemo(() => {
    const sourceUnits = response?.source_units ?? [];
    if (!normalizedFilter) return sourceUnits;
    return sourceUnits.filter((sourceUnit) => sourceUnitSearchText(sourceUnit).includes(normalizedFilter));
  }, [normalizedFilter, response?.source_units]);

  return (
    <BaseModal
      isOpen
      onClose={onClose}
      title={t('knowledge.sourceUnits.title')}
      cancelLabel={t('common.actions.close')}
      maxWidthClassName="max-w-4xl"
    >
      <div className="-mt-2 max-h-[72vh] overflow-hidden text-sm text-[var(--text-primary)]">
        <div className="mb-3 text-xs text-[var(--text-muted)]">{documentName}</div>
        <div className="relative mb-4">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="text"
            value={filter}
            onChange={(event) => onFilterChange(event.target.value)}
            placeholder={t('knowledge.sourceUnits.searchPlaceholder')}
            className="min-h-10 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--control-bg)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/15"
          />
        </div>

        <div className="max-h-[56vh] overflow-y-auto pr-1">
          {isLoading && !response && (
            <div className="flex items-center gap-2 rounded-xl bg-[var(--surface-secondary)] p-4 text-[var(--text-muted)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{t('knowledge.sourceUnits.loading')}</span>
            </div>
          )}

          {response && response.source_units.length === 0 && (
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-[var(--text-muted)]">
              {t('knowledge.sourceUnits.empty')}
            </div>
          )}

          {response && response.source_units.length > 0 && filteredSourceUnits.length === 0 && (
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-[var(--text-muted)]">
              {t('knowledge.sourceUnits.noFilterResults')}
            </div>
          )}

          <div className="space-y-2">
            {filteredSourceUnits.map((sourceUnit) => {
              const isExpanded = expandedSet.has(sourceUnit.id);
              return (
                <div key={sourceUnit.id} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)]">
                  <button
                    type="button"
                    onClick={() => onToggleSourceUnit(sourceUnit.id)}
                    aria-expanded={isExpanded}
                    className="flex w-full items-start justify-between gap-3 px-3 py-3 text-left transition-colors hover:bg-[var(--control-bg)] focus:outline-none focus:ring-2 focus:ring-inset focus:ring-[var(--accent-primary)]/25"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-[var(--text-primary)]" title={sourceUnitTitle(sourceUnit)}>
                        #{sourceUnit.source_index} · {sourceUnitTitle(sourceUnit)}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-muted)]">
                        {sourceUnit.draft_count > 0 && <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">{t('knowledge.sourceUnits.badge.drafts', { count: formatNumber(sourceUnit.draft_count) })}</span>}
                        {typeof sourceUnit.start_offset === 'number' && <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">{t('knowledge.sourceUnits.badge.offset', { value: formatNumber(sourceUnit.start_offset) })}</span>}
                        {typeof sourceUnit.end_offset === 'number' && <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">{t('knowledge.sourceUnits.badge.end', { value: formatNumber(sourceUnit.end_offset) })}</span>}
                      </div>
                    </div>
                    <ChevronDown className={`mt-0.5 h-4 w-4 shrink-0 text-[var(--text-muted)] transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                  </button>

                  {isExpanded && (
                    <div className="space-y-4 border-t border-[var(--border-subtle)] px-3 py-3">
                      <DraftDetailRow label={t('knowledge.sourceUnits.fields.sourceText')}>
                        <div className="whitespace-pre-wrap">{sourceUnit.content || '—'}</div>
                      </DraftDetailRow>

                      {sourceUnit.draft_titles.length > 0 && (
                        <DraftDetailRow label={t('knowledge.sourceUnits.fields.extractedDrafts')}>
                          <ul className="list-disc space-y-1 pl-5">
                            {sourceUnit.draft_titles.map((title) => <li key={title}>{title}</li>)}
                          </ul>
                        </DraftDetailRow>
                      )}

                      <DraftDetailRow label={t('knowledge.sourceUnits.fields.metadata')}>
                        <div className="flex flex-wrap gap-1.5 text-xs text-[var(--text-muted)]">
                          <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">{t('knowledge.sourceUnits.badge.id', { value: sourceUnit.id })}</span>
                          <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">{t('knowledge.sourceUnits.badge.sourceIndex', { value: formatNumber(sourceUnit.source_index) })}</span>
                          {typeof sourceUnit.page === 'number' && <span className="rounded-full bg-[var(--control-bg)] px-2 py-1">{t('knowledge.sourceUnits.badge.page', { value: formatNumber(sourceUnit.page) })}</span>}
                        </div>
                      </DraftDetailRow>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </BaseModal>
  );
};
