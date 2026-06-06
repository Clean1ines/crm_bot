import React, { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock3, FileText, Trash2, Zap } from 'lucide-react';

import { t } from '@shared/i18n';
import {
  type WorkbenchDocumentCardActionView,
  type WorkbenchDocumentCardUserMessage,
  type WorkbenchDocumentCardView,
} from '@shared/api/modules/knowledge';

type DocCardDocument = {
  id: string;
  file_name: string;
  file_size: number;
  preprocessing_mode?: string | null;
  card_view?: WorkbenchDocumentCardView | null;
};

type KnowledgeDocumentCardProps = {
  doc: DocCardDocument;
  isDeletePending: boolean;
  onRequestDelete: () => void;
  onCardAction: (actionId: string) => void;
  onOpenCuration: () => void;
  onStopProcessing: () => void;
  formatSize: (bytes: number) => string;
  knowledgeProcessingModeLabel: (value: string) => string;
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

type WorkbenchPhaseMetadata = Record<
  string,
  string | number | boolean | null | undefined
>;

type WorkbenchLocalClaimPreview = {
  claim_id?: string | null;
  node_run_id?: string | null;
  section_id?: string | null;
  section_index?: number | string | null;
  section_title?: string | null;
  local_ref?: string | null;
  claim?: string | null;
  claim_kind?: string | null;
  granularity?: string | null;
  evidence_block?: string | null;
  scope?: string | null;
  exclusion_scope?: string | null;
  possible_questions?: string[] | null;
  triples?: object[] | null;
  local_relations?: object[] | null;
  confidence?: number | string | null;
};

type WorkbenchCardMetadata = {
  workbench_phase?: WorkbenchPhaseMetadata | null;
  workbench_claim_preview?: WorkbenchLocalClaimPreview[] | null;
  workbench_claim_preview_count?: number | string | null;
};

const metadataNumber = (
  metadata: WorkbenchCardMetadata | undefined,
  key: string,
): number => {
  const phase = metadata?.workbench_phase;
  if (!phase || typeof phase !== 'object' || Array.isArray(phase)) return 0;

  const value = phase[key];
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const metadataRootNumber = (
  metadata: WorkbenchCardMetadata | undefined,
  key: keyof WorkbenchCardMetadata,
): number => {
  const value = metadata?.[key];
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const metadataText = (value: string | number | null | undefined): string => {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
};

const stringifyDetails = (value: object[] | null | undefined): string => {
  if (!Array.isArray(value) || value.length === 0) return '';
  return JSON.stringify(value, null, 2);
};

const translateDynamic = t as (key: string) => string;

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

export const KnowledgeDocumentCard: React.FC<KnowledgeDocumentCardProps> = ({
  doc,
  isDeletePending,
  onRequestDelete,
  onCardAction,
  onOpenCuration,
  onStopProcessing,
  formatSize,
  knowledgeProcessingModeLabel,
}) => {
  const cardView = doc.card_view;
  const timerStartedAt = cardView?.timer.current_active_started_at || null;
  const isLiveTimer = cardView?.timer.mode === 'running' && Boolean(timerStartedAt);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [expandedClaimIds, setExpandedClaimIds] = useState<Set<string>>(
    () => new Set(),
  );

  useEffect(() => {
    if (!isLiveTimer) return undefined;

    setNowMs(Date.now());
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [isLiveTimer, timerStartedAt]);

  if (!cardView) {
    return null;
  }

  const cardPrimaryActions = primaryActions(cardView);
  const cardSecondaryActions = visibleSecondaryActions(cardView);
  const deleteAction = cardView.actions.find(
    (action) => action.action_id === 'delete_document',
  );

  const cardMetadata = cardView.metadata as WorkbenchCardMetadata | undefined;

  const promptACompleted = metadataNumber(
    cardMetadata,
    'prompt_a_completed_sections',
  );
  const sectionQueueLeased = metadataNumber(
    cardMetadata,
    'section_queue_leased_count',
  );
  const sectionQueueReady = metadataNumber(
    cardMetadata,
    'section_queue_ready_count',
  );
  const registryApplicationPending =
    metadataNumber(cardMetadata, 'registry_application_ready_count') +
    metadataNumber(cardMetadata, 'registry_application_leased_count') +
    metadataNumber(
      cardMetadata,
      'registry_application_waiting_for_fresh_registry_count',
    );
  const embeddingIndexedClaims = metadataNumber(
    cardMetadata,
    'embedding_indexed_claims',
  );
  const claimPreview = Array.isArray(cardMetadata?.workbench_claim_preview)
    ? cardMetadata.workbench_claim_preview
    : [];
  const claimPreviewCount =
    metadataRootNumber(cardMetadata, 'workbench_claim_preview_count') ||
    claimPreview.length;

  const toggleClaimPreview = (claimId: string): void => {
    setExpandedClaimIds((current) => {
      const next = new Set(current);
      if (next.has(claimId)) {
        next.delete(claimId);
      } else {
        next.add(claimId);
      }
      return next;
    });
  };

  const sectionProgressCurrent =
    promptACompleted > 0 || sectionQueueLeased > 0 || sectionQueueReady > 0
      ? promptACompleted
      : cardView.sections.processed + cardView.sections.failed;

  const sectionProgressPercent =
    cardView.sections.total > 0
      ? Math.round((sectionProgressCurrent / cardView.sections.total) * 100)
      : 0;

  const sectionProgressText =
    promptACompleted > 0 || sectionQueueLeased > 0 || sectionQueueReady > 0
      ? `Prompt A: ${formatNumber(promptACompleted)} из ${formatNumber(
          cardView.sections.total,
        )} секций${
          sectionQueueLeased > 0
            ? ` · активно ${formatNumber(sectionQueueLeased)}`
            : ''
        }${
          sectionQueueReady > 0
            ? ` · в очереди ${formatNumber(sectionQueueReady)}`
            : ''
        }`
      : `${formatNumber(cardView.sections.processed)} из ${formatNumber(
          cardView.sections.total,
        )} секций обработано${
          cardView.sections.failed > 0
            ? ` · ${formatNumber(cardView.sections.failed)} с ошибкой`
            : ''
        }`;

  const timerStartedAtMs = timerStartedAt ? Date.parse(timerStartedAt) : Number.NaN;
  const liveActiveElapsedSeconds =
    isLiveTimer && Number.isFinite(timerStartedAtMs)
      ? Math.max(
          cardView.timer.active_elapsed_seconds,
          Math.floor((nowMs - timerStartedAtMs) / 1000),
        )
      : cardView.timer.active_elapsed_seconds;
  const liveWallElapsedSeconds =
    isLiveTimer && Number.isFinite(timerStartedAtMs)
      ? Math.max(cardView.timer.wall_elapsed_seconds, liveActiveElapsedSeconds)
      : cardView.timer.wall_elapsed_seconds;

  const elapsedText = `активно ${formatDuration(
    liveActiveElapsedSeconds,
  )} · всего ${formatDuration(liveWallElapsedSeconds)}`;

  const llmUsageText = `${formatNumber(
    cardView.usage.total_tokens,
  )} токенов · ${formatNumber(cardView.usage.llm_call_count)} LLM-выз.`;

  const handleCardAction = (action: WorkbenchDocumentCardActionView): void => {
    if (!action.enabled) return;

    if (action.action_id === 'cancel_processing') {
      onStopProcessing();
      return;
    }

    if (
      action.action_id === 'open_curation' ||
      action.action_id === 'open_published_surfaces'
    ) {
      onOpenCuration();
      return;
    }

    if (action.action_id === 'delete_document') {
      onRequestDelete();
      return;
    }

    onCardAction(action.action_id);
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
              {cardText(cardView.status_i18n_key, cardView.default_status_label)}
            </span>
          )}

          {cardSecondaryActions.slice(0, 3).map((action) => (
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
          ))}

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
          <span className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)]">
            {cardText(cardView.status_i18n_key, cardView.default_status_label)}
          </span>
        </div>

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
      </div>

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
            <div className="text-[var(--text-muted)]">{llmUsageText}</div>
          </div>

          <div className="rounded-xl bg-[var(--surface-secondary)] p-3">
            <div className="mb-1 font-medium text-[var(--text-primary)]">
              Прогресс
            </div>
            <div className="text-[var(--text-muted)]">{sectionProgressText}</div>
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
          {(promptACompleted > 0 || sectionQueueLeased > 0 || sectionQueueReady > 0) && (
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              Prompt A: {formatNumber(promptACompleted)} /{' '}
              {formatNumber(cardView.sections.total)}
              {sectionQueueLeased > 0
                ? ` · активно ${formatNumber(sectionQueueLeased)}`
                : ''}
              {sectionQueueReady > 0
                ? ` · очередь ${formatNumber(sectionQueueReady)}`
                : ''}
            </span>
          )}
          {claimPreviewCount > 0 && (
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              Локальные claims: {formatNumber(claimPreviewCount)}
            </span>
          )}
          {registryApplicationPending > 0 && (
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              Registry queue: {formatNumber(registryApplicationPending)}
            </span>
          )}
          {embeddingIndexedClaims > 0 && (
            <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              Embeddings: {formatNumber(embeddingIndexedClaims)}
            </span>
          )}
          {cardView.transient_purged && (
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-emerald-700 dark:text-emerald-300">
              Промежуточные данные очищены
            </span>
          )}
          {cardView.recovery.mode === 'scheduled_auto_resume' && (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-amber-700 dark:text-amber-300">
              {cardText(cardView.recovery.i18n_key, cardView.recovery.default_message)}
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

        {claimPreview.length > 0 && (
          <div className="rounded-xl bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-secondary)]">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="font-semibold text-[var(--text-primary)]">
                Локально извлечённые claims Prompt A
              </div>
              <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                {formatNumber(claimPreviewCount)}
              </span>
            </div>

            <div className="space-y-2">
              {claimPreview.map((claim, index) => {
                const claimId =
                  metadataText(claim.claim_id) ||
                  metadataText(claim.node_run_id) ||
                  `claim-${index + 1}`;
                const isExpanded = expandedClaimIds.has(claimId);
                const claimText =
                  metadataText(claim.claim) || `Claim ${index + 1}`;
                const evidence = metadataText(claim.evidence_block);
                const triples = stringifyDetails(claim.triples);
                const relations = stringifyDetails(claim.local_relations);
                const possibleQuestions = Array.isArray(claim.possible_questions)
                  ? claim.possible_questions.filter(Boolean)
                  : [];

                return (
                  <div
                    key={claimId}
                    className="rounded-lg bg-[var(--surface-elevated)] p-2"
                  >
                    <button
                      type="button"
                      onClick={() => toggleClaimPreview(claimId)}
                      className="flex w-full items-start justify-between gap-2 text-left"
                    >
                      <span>
                        <span className="font-medium text-[var(--text-primary)]">
                          {claimText}
                        </span>
                        <span className="mt-1 block text-[var(--text-muted)]">
                          {metadataText(claim.claim_kind) || 'claim'} · секция{' '}
                          {metadataText(claim.section_index) || '?'}
                          {metadataText(claim.local_ref)
                            ? ` · ${metadataText(claim.local_ref)}`
                            : ''}
                        </span>
                      </span>
                      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                        {isExpanded ? 'скрыть' : 'детали'}
                      </span>
                    </button>

                    {isExpanded && (
                      <div className="mt-2 space-y-2 border-t border-[var(--border-subtle)] pt-2">
                        {evidence && (
                          <div>
                            <div className="font-medium text-[var(--text-primary)]">
                              Evidence
                            </div>
                            <div className="mt-1 whitespace-pre-wrap">
                              {evidence}
                            </div>
                          </div>
                        )}
                        {metadataText(claim.scope) && (
                          <div>
                            <span className="font-medium text-[var(--text-primary)]">
                              Scope:
                            </span>{' '}
                            {metadataText(claim.scope)}
                          </div>
                        )}
                        {possibleQuestions.length > 0 && (
                          <div>
                            <div className="font-medium text-[var(--text-primary)]">
                              Возможные вопросы
                            </div>
                            <ul className="mt-1 list-disc pl-4">
                              {possibleQuestions.map((question) => (
                                <li key={question}>{question}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {triples && (
                          <div>
                            <div className="font-medium text-[var(--text-primary)]">
                              Triples
                            </div>
                            <pre className="mt-1 overflow-x-auto rounded bg-[var(--control-bg)] p-2">
                              {triples}
                            </pre>
                          </div>
                        )}
                        {relations && (
                          <div>
                            <div className="font-medium text-[var(--text-primary)]">
                              Relations
                            </div>
                            <pre className="mt-1 overflow-x-auto rounded bg-[var(--control-bg)] p-2">
                              {relations}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 space-y-3">
        <details className="rounded-xl bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-secondary)]">
          <summary className="cursor-pointer font-semibold text-[var(--text-primary)]">
            Подробности обработки
          </summary>

          <div className="mt-3 space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="rounded-lg bg-[var(--surface-elevated)] p-2">
                <div className="font-medium text-[var(--text-primary)]">
                  Секции
                </div>
                <div className="mt-1">
                  {promptACompleted > 0 || sectionQueueLeased > 0 || sectionQueueReady > 0
                    ? `Prompt A: ${formatNumber(promptACompleted)} из ${formatNumber(
                        cardView.sections.total,
                      )} · активно ${formatNumber(
                        sectionQueueLeased,
                      )} · в очереди ${formatNumber(sectionQueueReady)}`
                    : `Обработано ${formatNumber(
                        cardView.sections.processed,
                      )} из ${formatNumber(cardView.sections.total)}${
                        cardView.sections.failed > 0
                          ? ` · ошибок: ${formatNumber(cardView.sections.failed)}`
                          : ''
                      }`}
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
                  Canonical / runtime итог
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
        </details>
      </div>
    </div>
  );
};
