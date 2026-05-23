import React from 'react';
import { Loader2 } from 'lucide-react';

import { type KnowledgeAnswerDraft, type KnowledgeAnswerDraftsResponse } from '@shared/api/modules/knowledge';
import { t } from '@shared/i18n';

const draftTitle = (draft: KnowledgeAnswerDraft): string => (
  draft.title || draft.question_variants[0] || t('knowledge.drafts.untitled')
);

const formatNumber = (value: number): string => {
  if (!Number.isFinite(value)) return '0';
  return new Intl.NumberFormat().format(value);
};

export const DraftsSummary: React.FC<{
  response: KnowledgeAnswerDraftsResponse | undefined;
  isLoading: boolean;
  onOpen: () => void;
}> = ({ response, isLoading, onOpen }) => {
  if (isLoading && !response) {
    return (
      <div className="mt-3 border-t border-[var(--border-subtle)] pt-2 text-xs text-[var(--text-muted)]">
        <div className="flex items-center gap-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span>{t('knowledge.drafts.loading')}</span>
        </div>
      </div>
    );
  }

  if (!response) return null;

  const previewDrafts = response.drafts.slice(-3).reverse();
  const shownCount = response.drafts.length;
  const totalCount = response.total_count;

  return (
    <div className="mt-3 border-t border-[var(--border-subtle)] pt-2 text-xs">
      <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="font-medium text-[var(--text-primary)]">
            {t('knowledge.drafts.title', { count: formatNumber(totalCount) })}
          </div>
          <div className="mt-0.5 text-[var(--text-muted)]">
            {t('knowledge.drafts.shownAvailable', {
              shown: formatNumber(shownCount),
              total: formatNumber(totalCount),
            })}
          </div>
        </div>
        <button
          type="button"
          onClick={onOpen}
          className="w-fit rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20 focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
        >
          {t('knowledge.drafts.openAll')}
        </button>
      </div>

      {previewDrafts.length > 0 ? (
        <div className="space-y-1">
          {previewDrafts.map((draft) => (
            <div key={draft.id} className="truncate rounded-lg bg-[var(--control-bg)] px-2 py-1.5 font-medium text-[var(--text-primary)]" title={draftTitle(draft)}>
              {draftTitle(draft)}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg bg-[var(--control-bg)] px-2 py-2 text-[var(--text-muted)]">
          {t('knowledge.drafts.empty')}
        </div>
      )}
    </div>
  );
};
