import React from 'react';
import { AlertTriangle, CheckCircle2, Clock3, FileText, Trash2, Zap } from 'lucide-react';

import { ImportQualitySummary } from './ImportQualitySummary';
import { PriceFactsSummary } from './PriceFactsSummary';
import { CommercialTruthReviewSummary } from './CommercialTruthReviewSummary';

import { t } from '@shared/i18n';
import {
  type KnowledgeCommercialTruthReviewPolicy,
  type KnowledgeCommercialTruthReviewResponse,
  type KnowledgeImportQualityReport,
  type KnowledgePriceFact,
  type KnowledgePriceFactsResponse,
  type KnowledgeProcessingReport,
  type WorkbenchDocumentCardActionView,
  type WorkbenchDocumentCardUserMessage,
  type WorkbenchDocumentCardView,
} from '@shared/api/modules/knowledge';

type DocCardDocument = {
  id: string;
  file_name: string;
  file_size: number;
  chunk_count: number;
  structured_entries?: number;
  structured_chunk_count?: number;
  preprocessing_mode?: string | null;
  created_at: string;
  status: string;
  error?: string | null;
  card_view?: WorkbenchDocumentCardView | null;
};

const formatNumber = (value: number): string =>
  new Intl.NumberFormat('ru-RU').format(Math.max(0, Math.floor(value || 0)));

const formatDuration = (seconds: number): string => {
  const safeSeconds = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const restSeconds = safeSeconds % 60;

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${restSeconds
      .toString()
      .padStart(2, '0')}`;
  }
  return `${minutes}:${restSeconds.toString().padStart(2, '0')}`;
};

const translateDynamic = t as unknown as (key: string) => string;

const cardText = (i18nKey: string | null | undefined, fallback: string): string => {
  if (!i18nKey) return fallback;
  const translated = translateDynamic(i18nKey);
  return translated && translated !== i18nKey ? translated : fallback;
};

const messageClassName = (severity: string): string => {
  if (severity === 'error') {
    return 'border-[var(--accent-danger)]/30 bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]';
  }
  if (severity === 'warning') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300';
  }
  if (severity === 'success') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
  }
  return 'border-[var(--border-subtle)] bg-[var(--surface-secondary)] text-[var(--text-secondary)]';
};

const actionClassName = (action: WorkbenchDocumentCardActionView): string => {
  const base =
    'rounded-full px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50';

  if (action.tone === 'danger') {
    return `${base} bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)] hover:opacity-80`;
  }
  if (action.tone === 'warning') {
    return `${base} bg-amber-500/10 text-amber-700 hover:bg-amber-500/20 dark:text-amber-300`;
  }
  if (action.tone === 'primary') {
    return `${base} bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/20`;
  }
  return `${base} bg-[var(--control-bg)] text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)]`;
};

const messageIcon = (message: WorkbenchDocumentCardUserMessage) => {
  if (message.severity === 'error' || message.severity === 'warning') {
    return <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none" />;
  }
  if (message.severity === 'success') {
    return <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 flex-none" />;
  }
  return <Clock3 className="mt-0.5 h-3.5 w-3.5 flex-none" />;
};

const primaryActions = (cardView: WorkbenchDocumentCardView): WorkbenchDocumentCardActionView[] =>
  cardView.actions.filter(
    (action) => action.visible && action.enabled && action.tone === 'primary',
  );

const visibleSecondaryActions = (
  cardView: WorkbenchDocumentCardView,
): WorkbenchDocumentCardActionView[] =>
  cardView.actions.filter(
    (action) =>
      action.visible &&
      action.action_id !== 'delete_document' &&
      !(
        action.enabled &&
        action.tone === 'primary' &&
        primaryActions(cardView).some(
          (primaryAction) => primaryAction.action_id === action.action_id,
        )
      ),
  );

export const KnowledgeDocumentCard: React.FC<{
  doc: DocCardDocument;
  statusBadge: { className: string; label: string };
  isDeletePending: boolean;
  processingReport: KnowledgeProcessingReport | undefined;
  importQualityReport: KnowledgeImportQualityReport | undefined;
  priceFactsResponse: KnowledgePriceFactsResponse | undefined;
  commercialTruthReviewResponse: KnowledgeCommercialTruthReviewResponse | undefined;
  isPriceFactsLoading: boolean;
  isCommercialTruthReviewLoading: boolean;
  mutatingPriceFactId: string | null;
  importQualityLoading: boolean;
  commercialTruthReviewPolicy: KnowledgeCommercialTruthReviewPolicy;
  onPolicyChange: (policy: KnowledgeCommercialTruthReviewPolicy) => void;
  onPublishFact: (fact: KnowledgePriceFact) => void;
  onRejectFact: (fact: KnowledgePriceFact) => void;
  onRequestDelete: () => void;
  onCardAction?: (actionId: string) => void;
  actionsNode: React.ReactNode;
  processingNode: React.ReactNode;
  retightenReportNode: React.ReactNode;
  statusNode: React.ReactNode;
  hasDrafts: boolean;
  draftCount?: number;
  hasSourceUnits: boolean;
  isDocumentProcessing: boolean;
  onOpenDrafts: () => void;
  onOpenSourceUnits: () => void;
  onOpenCuration: () => void;
  onStopProcessing: () => void;
  formatSize: (bytes: number) => string;
  knowledgeProcessingModeLabel: (value: string) => string;
}> = ({
  doc,
  statusBadge,
  isDeletePending,
  importQualityReport,
  importQualityLoading,
  priceFactsResponse,
  isPriceFactsLoading,
  onPublishFact,
  onRejectFact,
  onRequestDelete,
  onCardAction,
  mutatingPriceFactId,
  commercialTruthReviewResponse,
  isCommercialTruthReviewLoading,
  commercialTruthReviewPolicy,
  onPolicyChange,
  actionsNode,
  processingNode,
  retightenReportNode,
  statusNode,
  hasDrafts,
  draftCount,
  hasSourceUnits,
  isDocumentProcessing,
  onOpenDrafts,
  onOpenSourceUnits,
  onOpenCuration,
  onStopProcessing,
  formatSize,
  knowledgeProcessingModeLabel,
}) => {
  const cardView = doc.card_view ?? null;
  const cardPrimaryActions = cardView ? primaryActions(cardView) : [];
  const cardSecondaryActions = cardView ? visibleSecondaryActions(cardView) : [];
  const deleteAction = cardView?.actions.find(
    (action) => action.action_id === 'delete_document',
  );

  const sectionProgressPercent = cardView && cardView.sections.total > 0
    ? Math.round(
        ((cardView.sections.processed + cardView.sections.failed) /
          cardView.sections.total) *
          100,
      )
    : 0;

  const sectionProgressText = cardView
    ? `${formatNumber(cardView.sections.processed)} из ${formatNumber(
        cardView.sections.total,
      )} секций обработано${
        cardView.sections.failed > 0
          ? ` · ${formatNumber(cardView.sections.failed)} с ошибкой`
          : ''
      }`
    : '';

  const elapsedText = cardView
    ? `активно ${formatDuration(cardView.timer.active_elapsed_seconds)} · всего ${formatDuration(
        cardView.timer.wall_elapsed_seconds,
      )}`
    : '';

  const llmUsageText = cardView
    ? `${formatNumber(cardView.usage.total_tokens)} токенов · ${formatNumber(
        cardView.usage.llm_call_count,
      )} LLM-выз.`
    : '';

  const handleCardAction = (action: WorkbenchDocumentCardActionView): void => {
    if (!action.enabled) return;
    if (onCardAction) {
      onCardAction(action.action_id);
      return;
    }

    if (action.action_id === 'cancel_processing') onStopProcessing();
    if (action.action_id === 'open_curation') onOpenCuration();
    if (action.action_id === 'open_published_surfaces') onOpenCuration();
    if (action.action_id === 'delete_document') onRequestDelete();
  };

  return (
    <div
      id={`knowledge-doc-card-${doc.id}`}
      className="group rounded-2xl bg-[var(--surface-elevated)] p-4 transition-all hover:shadow-lg sm:p-5"
    >
      <div className="mb-4 flex items-start justify-between gap-2">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-secondary)] text-[var(--accent-primary)]">
          <FileText className="h-5 w-5" />
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          {cardView ? (
            <>
              {cardPrimaryActions.length > 0 ? (
                cardPrimaryActions.map((action) => (
                  <button
                    key={action.action_id}
                    type="button"
                    disabled={!action.enabled}
                    title={action.default_confirmation || action.default_label}
                    onClick={() => handleCardAction(action)}
                    className={actionClassName(action)}
                  >
                    {cardText(action.i18n_key, action.default_label)}
                  </button>
                ))
              ) : (
                <span className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]">
                  {cardText(
                    cardView.status_i18n_key,
                    cardView.default_status_label,
                  )}
                </span>
              )}
            </>
          ) : isDocumentProcessing ? (
            <button
              type="button"
              onClick={onStopProcessing}
              className="rounded-full bg-[var(--accent-danger-bg)] px-2.5 py-1 text-xs font-medium text-[var(--accent-danger-text)] transition-colors hover:opacity-80"
            >
              {t('knowledge.documentCard.primaryAction.stop')}
            </button>
          ) : hasDrafts ? (
            <button
              type="button"
              onClick={onOpenDrafts}
              className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20"
            >
              {t('knowledge.documentCard.primaryAction.openDrafts')}
            </button>
          ) : hasSourceUnits ? (
            <button
              type="button"
              onClick={onOpenSourceUnits}
              className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20"
            >
              {t('knowledge.documentCard.primaryAction.openSources')}
            </button>
          ) : (
            <span className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]">
              {t('knowledge.documentCard.primaryAction.details')}
            </span>
          )}

          {cardView ? (
            cardSecondaryActions.slice(0, 3).map((action) => (
              <button
                key={action.action_id}
                type="button"
                disabled={!action.enabled}
                title={action.default_confirmation || action.default_label}
                onClick={() => handleCardAction(action)}
                className={actionClassName(action)}
              >
                {cardText(action.i18n_key, action.default_label)}
              </button>
            ))
          ) : (
            <button
              type="button"
              onClick={onOpenCuration}
              className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20"
            >
              {cardText(
                'knowledge.workbench.card.actions.open_curation',
                'Открыть курацию',
              )}
            </button>
          )}

          <button
            type="button"
            onClick={
              deleteAction && deleteAction.enabled
                ? () => handleCardAction(deleteAction)
                : onRequestDelete
            }
            disabled={isDeletePending}
            title={deleteAction?.default_confirmation || t('common.actions.delete')}
            className="rounded-lg p-2 text-[var(--accent-danger-text)] transition-colors hover:bg-[var(--accent-danger-bg)] disabled:cursor-wait disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="line-clamp-2 font-semibold text-[var(--text-primary)]">
              {doc.file_name}
            </h3>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              {formatSize(doc.file_size)} ·{' '}
              {knowledgeProcessingModeLabel(doc.preprocessing_mode || 'faq')}
            </p>
          </div>
          <span
            className={
              cardView
                ? 'rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)]'
                : statusBadge.className
            }
          >
            {cardView
              ? cardText(cardView.status_i18n_key, cardView.default_status_label)
              : statusBadge.label}
          </span>
        </div>

        {cardView && (
          <div className="mt-2 rounded-xl bg-[var(--surface-secondary)] px-3 py-2 text-sm leading-relaxed text-[var(--text-secondary)]">
            <div className="font-medium text-[var(--text-primary)]">
              Что происходит с документом
            </div>
            <p className="mt-1">
              {cardText(
                cardView.status_description_i18n_key,
                cardView.default_status_description,
              )}
            </p>
          </div>
        )}
      </div>

      {cardView && (
        <div className="mb-4 space-y-3">
          <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
            <div className="rounded-xl bg-[var(--surface-secondary)] p-3">
              <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
                <Clock3 className="h-3.5 w-3.5" />
                {cardText(cardView.timer.i18n_key, cardView.timer.default_label)}
              </div>
              <div className="text-[var(--text-muted)]">
                {elapsedText}
                {cardView.timer.mode === 'running' ? ' · live' : ''}
              </div>
            </div>

            <div className="rounded-xl bg-[var(--surface-secondary)] p-3">
              <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
                <Zap className="h-3.5 w-3.5" />
                ИИ
              </div>
              <div className="text-[var(--text-muted)]">
                {llmUsageText}
              </div>
            </div>

            <div className="rounded-xl bg-[var(--surface-secondary)] p-3">
              <div className="mb-1 font-medium text-[var(--text-primary)]">
                Прогресс
              </div>
              <div className="text-[var(--text-muted)]">
                {sectionProgressText}
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--control-bg)]">
                <div
                  className="h-full rounded-full bg-[var(--accent-primary)]"
                  style={{ width: `${sectionProgressPercent}%` }}
                />
              </div>
              <div className="mt-1 text-[var(--text-muted)]">
                {sectionProgressPercent}%
              </div>
            </div>

            <div className="rounded-xl bg-[var(--surface-secondary)] p-3">
              <div className="mb-1 font-medium text-[var(--text-primary)]">
                Runtime
              </div>
              <div className="text-[var(--text-muted)]">
                {formatNumber(cardView.runtime.runtime_entry_count)} записей
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              Факты: {formatNumber(cardView.registry.entry_count)}
              {cardView.registry.retained ? ' · registry сохранён' : ''}
            </span>
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              Runtime: {formatNumber(cardView.runtime.runtime_entry_count)} записей
            </span>
            {cardView.registry.final_snapshot_id && (
              <span
                className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]"
                title={cardView.registry.final_snapshot_id}
              >
                Snapshot: {cardView.registry.final_snapshot_id}
              </span>
            )}
            {cardView.transient_purged && (
              <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-emerald-700 dark:text-emerald-300">
                Промежуточные данные очищены
              </span>
            )}
            {cardView.recovery.mode === 'scheduled_auto_resume' && (
              <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-amber-700 dark:text-amber-300">
                {cardText(
                  cardView.recovery.i18n_key,
                  cardView.recovery.default_message,
                )}
              </span>
            )}
          </div>

          {cardView.messages.length > 0 && (
            <div className="space-y-2">
              {cardView.messages.map((message) => (
                <div
                  key={`${message.code}-${message.default_message}`}
                  className={`flex gap-2 rounded-xl border px-3 py-2 text-xs ${messageClassName(
                    message.severity,
                  )}`}
                >
                  {messageIcon(message)}
                  <span>{cardText(message.i18n_key, message.default_message)}</span>
                </div>
              ))}
            </div>
          )}

          {cardView.error && (
            <div className="rounded-xl border border-[var(--accent-danger)]/30 bg-[var(--accent-danger-bg)] px-3 py-2 text-xs text-[var(--accent-danger-text)]">
              {cardText(
                cardView.error.user_message.i18n_key,
                cardView.error.user_message.default_message,
              )}
            </div>
          )}
        </div>
      )}

      {!cardView && (
        <div className="mb-3 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
            {t('knowledge.documentCard.counters.chunks')}: {doc.chunk_count}
          </span>
          {typeof doc.structured_entries === 'number' && doc.structured_entries > 0 && (
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              {t('knowledge.documentCard.counters.runtimeEntries')}:{' '}
              {doc.structured_entries}
            </span>
          )}
          {typeof draftCount === 'number' && draftCount > 0 && (
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              {t('knowledge.documentCard.counters.drafts')}: {draftCount}
            </span>
          )}
        </div>
      )}

      {!cardView && statusNode}

      <div className="mt-4 space-y-3">
        {!cardView && actionsNode}

        {doc.preprocessing_mode === 'faq' ? (
          <>

            <details className="rounded-xl bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-secondary)]">
              <summary className="cursor-pointer font-semibold text-[var(--text-primary)]">
                {cardView ? 'Подробности обработки' : 'Legacy-диагностика импорта'}
              </summary>
              {cardView ? (
                <div className="mt-3 space-y-3">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <div className="rounded-lg bg-[var(--surface-elevated)] p-2">
                      <div className="font-medium text-[var(--text-primary)]">
                        Секции
                      </div>
                      <div className="mt-1">
                        Обработано {formatNumber(cardView.sections.processed)} из{' '}
                        {formatNumber(cardView.sections.total)}
                        {cardView.sections.failed > 0
                          ? ` · ошибок: ${formatNumber(cardView.sections.failed)}`
                          : ''}
                      </div>
                    </div>

                    <div className="rounded-lg bg-[var(--surface-elevated)] p-2">
                      <div className="font-medium text-[var(--text-primary)]">
                        Расход ИИ
                      </div>
                      <div className="mt-1">
                        {formatNumber(cardView.usage.total_tokens)} токенов ·{' '}
                        {formatNumber(cardView.usage.llm_call_count)} LLM-выз.
                      </div>
                    </div>

                    <div className="rounded-lg bg-[var(--surface-elevated)] p-2">
                      <div className="font-medium text-[var(--text-primary)]">
                        Итоговые факты
                      </div>
                      <div className="mt-1">
                        {formatNumber(cardView.registry.entry_count)} фактов ·{' '}
                        {formatNumber(cardView.runtime.runtime_entry_count)} runtime-записей
                      </div>
                    </div>

                    <div className="rounded-lg bg-[var(--surface-elevated)] p-2">
                      <div className="font-medium text-[var(--text-primary)]">
                        Время
                      </div>
                      <div className="mt-1">{elapsedText}</div>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={onOpenCuration}
                      className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20"
                    >
                      Открыть trace и курацию
                    </button>
                    {cardView.registry.final_snapshot_id && (
                      <span
                        className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-[var(--text-muted)]"
                        title={cardView.registry.final_snapshot_id}
                      >
                        Snapshot сохранён
                      </span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="mt-3 space-y-3">
                  <ImportQualitySummary
                    report={importQualityReport}
                    isLoading={importQualityLoading}
                  />
                  {processingNode}
                  {retightenReportNode}
                  <PriceFactsSummary
                    response={priceFactsResponse}
                    isLoading={isPriceFactsLoading}
                    onPublishFact={onPublishFact}
                    onRejectFact={onRejectFact}
                    mutatingFactId={mutatingPriceFactId}
                  />
                  <CommercialTruthReviewSummary
                    response={commercialTruthReviewResponse}
                    isLoading={isCommercialTruthReviewLoading}
                    policy={commercialTruthReviewPolicy}
                    onPolicyChange={onPolicyChange}
                  />
                </div>
              )}
            </details>
          </>
        ) : (
          <>
            <ImportQualitySummary
              report={importQualityReport}
              isLoading={importQualityLoading}
            />
            <PriceFactsSummary
              response={priceFactsResponse}
              isLoading={isPriceFactsLoading}
              onPublishFact={onPublishFact}
              onRejectFact={onRejectFact}
              mutatingFactId={mutatingPriceFactId}
            />
            <CommercialTruthReviewSummary
              response={commercialTruthReviewResponse}
              isLoading={isCommercialTruthReviewLoading}
              policy={commercialTruthReviewPolicy}
              onPolicyChange={onPolicyChange}
            />
            {processingNode}
            {retightenReportNode}
          </>
        )}
      </div>
    </div>
  );
};
