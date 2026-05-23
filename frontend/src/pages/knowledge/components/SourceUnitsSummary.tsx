import React from 'react';
import { Loader2 } from 'lucide-react';

import { type KnowledgeSourceUnit, type KnowledgeSourceUnitsResponse } from '@shared/api/modules/knowledge';
import { t } from '@shared/i18n';

const sourceUnitTitle = (sourceUnit: KnowledgeSourceUnit): string => (
  sourceUnit.title.trim() || t('knowledge.sourceUnits.fallbackTitle', { index: String(sourceUnit.source_index) })
);

const formatNumber = (value: number): string => {
  if (!Number.isFinite(value)) return '0';
  return new Intl.NumberFormat().format(value);
};

export const SourceUnitsSummary: React.FC<{
  response: KnowledgeSourceUnitsResponse | undefined;
  isLoading: boolean;
  onOpen: () => void;
}> = ({ response, isLoading, onOpen }) => {
  if (isLoading && !response) {
    return (
      <div className="mt-3 border-t border-[var(--border-subtle)] pt-2 text-xs text-[var(--text-muted)]">
        <div className="flex items-center gap-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span>{t('knowledge.sourceUnits.loading')}</span>
        </div>
      </div>
    );
  }

  if (!response) return null;

  const previewUnits = response.source_units.slice(0, 3);
  return (
    <div className="mt-3 border-t border-[var(--border-subtle)] pt-2 text-xs">
      <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="font-medium text-[var(--text-primary)]">
            {t('knowledge.sourceUnits.total', { total: formatNumber(response.total_count) })}
          </div>
          <div className="mt-0.5 text-[var(--text-muted)]">
            {t('knowledge.sourceUnits.description')}
          </div>
        </div>
        <button
          type="button"
          onClick={onOpen}
          className="w-fit rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20 focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
        >
          {t('knowledge.sourceUnits.open')}
        </button>
      </div>

      {previewUnits.length > 0 ? (
        <div className="space-y-1">
          {previewUnits.map((sourceUnit) => (
            <div
              key={sourceUnit.id}
              className="truncate rounded-lg bg-[var(--control-bg)] px-2 py-1.5 font-medium text-[var(--text-primary)]"
              title={sourceUnitTitle(sourceUnit)}
            >
              #{sourceUnit.source_index} · {sourceUnitTitle(sourceUnit)}
              {sourceUnit.draft_count > 0 ? ` · ${t('knowledge.sourceUnits.badge.drafts', { count: formatNumber(sourceUnit.draft_count) })}` : ''}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg bg-[var(--control-bg)] px-2 py-2 text-[var(--text-muted)]">
          {t('knowledge.sourceUnits.empty')}
        </div>
      )}
    </div>
  );
};
