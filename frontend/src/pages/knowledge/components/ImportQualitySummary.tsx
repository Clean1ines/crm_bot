import React from 'react';

import { type KnowledgeImportQualityReport } from '@shared/api/modules/knowledge';
import { t } from '@shared/i18n';

const importQualityStatusLabel = (status: string): string => {
  if (status === 'good') return t('knowledge.importQuality.status.good');
  if (status === 'needs_review') return t('knowledge.importQuality.status.needsReview');
  if (status === 'unsafe') return t('knowledge.importQuality.status.unsafe');
  return status || t('knowledge.common.unspecified');
};

const importQualityStatusClassName = (status: string): string => {
  if (status === 'good') return 'bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]';
  if (status === 'unsafe') return 'bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]';
  return 'bg-[var(--accent-warning-bg)] text-[var(--accent-warning)]';
};

const importQualityActionLabel = (action: string): string => {
  if (action === 'continue_to_knowledge_compilation') return t('knowledge.importQuality.action.continue');
  if (action === 'review_source_units') return t('knowledge.importQuality.action.reviewSourceUnits');
  if (action === 'wait_for_processing') return t('knowledge.importQuality.action.waitForProcessing');
  if (action === 'replace_or_review_document') return t('knowledge.importQuality.action.replaceOrReview');
  return action || t('knowledge.common.unspecified');
};

const importQualityWarningLabel = (code: string): string => {
  if (code === 'processing_failed') return t('knowledge.importQuality.warning.processingFailed');
  if (code === 'processing_cancelled') return t('knowledge.importQuality.warning.processingCancelled');
  if (code === 'processing_not_finished') return t('knowledge.importQuality.warning.processingNotFinished');
  if (code === 'no_source_units') return t('knowledge.importQuality.warning.noSourceUnits');
  if (code === 'very_little_text') return t('knowledge.importQuality.warning.veryLittleText');
  if (code === 'many_empty_units') return t('knowledge.importQuality.warning.manyEmptyUnits');
  if (code === 'many_short_units') return t('knowledge.importQuality.warning.manyShortUnits');
  if (code === 'table_like_content') return t('knowledge.importQuality.warning.tableLikeContent');
  if (code === 'duplicated_headings') return t('knowledge.importQuality.warning.duplicatedHeadings');
  return t('knowledge.importQuality.warning.unknown');
};

const formatNumber = (value: number): string => new Intl.NumberFormat('ru-RU').format(value);

interface ImportQualitySummaryProps {
  report?: KnowledgeImportQualityReport;
  isLoading: boolean;
}

export const ImportQualitySummary: React.FC<ImportQualitySummaryProps> = ({ report, isLoading }) => {
  if (isLoading && !report) {
    return (
      <div className="mb-4 rounded-xl bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-muted)]">
        {t('knowledge.importQuality.loading')}
      </div>
    );
  }

  if (!report) {
    return null;
  }

  const visibleWarnings = report.warnings.slice(0, 2);

  return (
    <div className="mb-4 rounded-xl bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-muted)]">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="font-semibold text-[var(--text-primary)]">
          {t('knowledge.importQuality.title')}
        </div>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${importQualityStatusClassName(report.status)}`}>
          {importQualityStatusLabel(report.status)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <span className="text-[var(--text-muted)]">{t('knowledge.importQuality.sourceUnits')}</span>
          <div className="font-medium text-[var(--text-primary)]">{formatNumber(report.source_units_count)}</div>
        </div>
        <div>
          <span className="text-[var(--text-muted)]">{t('knowledge.importQuality.extractedText')}</span>
          <div className="font-medium text-[var(--text-primary)]">{formatNumber(report.extracted_text_chars)}</div>
        </div>
        <div>
          <span className="text-[var(--text-muted)]">{t('knowledge.importQuality.shortUnits')}</span>
          <div className="font-medium text-[var(--text-primary)]">{formatNumber(report.short_units_count)}</div>
        </div>
        <div>
          <span className="text-[var(--text-muted)]">{t('knowledge.importQuality.tableLikeUnits')}</span>
          <div className="font-medium text-[var(--text-primary)]">{formatNumber(report.table_like_units_count)}</div>
        </div>
      </div>

      {visibleWarnings.length > 0 && (
        <ul className="mt-3 space-y-1">
          {visibleWarnings.map((warning) => (
            <li key={`${warning.code}-${warning.severity}`} className="leading-relaxed">
              {importQualityWarningLabel(warning.code)}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 border-t border-[var(--border-subtle)] pt-2">
        <span className="font-medium text-[var(--text-primary)]">
          {t('knowledge.importQuality.recommendedAction')}
        </span>{' '}
        <span>{importQualityActionLabel(report.recommended_action)}</span>
      </div>
    </div>
  );
};
