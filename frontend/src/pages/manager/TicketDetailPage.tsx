import { t } from '@shared/i18n';
import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { getErrorMessage } from '../../shared/api/core/errors';
import { threadStatusLabel } from '../../shared/lib/uiLabels';

import type { Client, Message, ThreadState } from '../../entities/thread/model/types';
import { threadsApi } from '../../shared/api/modules/threads';
import type { TicketResolution } from '../../shared/api/modules/threads';
import { getClientDisplayName } from '../../shared/lib/clients';
import { getMessagePresentation } from '../../shared/lib/threadMessages';

const getMutationErrorMessage = (error: unknown): string => (
  getErrorMessage(
    error,
    t('manager.ticket.replyDeliveryFailed'),
  )
);

const resolutionStatusLabel = (status: TicketResolution['status'] | undefined): string => {
  switch (status) {
    case 'pending':
      return t('manager.ticket.resolution.status.pending');
    case 'generated':
      return t('manager.ticket.resolution.status.generated');
    case 'edited':
      return t('manager.ticket.resolution.status.edited');
    case 'failed':
      return t('manager.ticket.resolution.status.failed');
    default:
      return t('manager.ticket.resolution.status.missing');
  }
};

export const TicketDetailPage: React.FC = () => {
  const { projectId, threadId } = useParams<{ projectId: string; threadId: string }>();
  const queryClient = useQueryClient();
  const [replyText, setReplyText] = useState('');
  const [resolutionDraft, setResolutionDraft] = useState({ key: '', text: '' });

  const {
    data: messagesData,
    isLoading: messagesLoading,
    error: messagesError,
  } = useQuery({
    queryKey: ['ticket_messages', threadId],
    queryFn: async () => {
      if (!threadId) throw new Error(t('manager.ticket.threadNotSelected'));

      const { data, error } = await threadsApi.getMessages(threadId);
      if (error) throw error;

      return data;
    },
    enabled: !!threadId,
  });

  const messages: Message[] =
    messagesData &&
    typeof messagesData === 'object' &&
    'messages' in messagesData &&
    Array.isArray(messagesData.messages)
      ? (messagesData.messages as Message[])
      : [];

  const { data: ticketInfo } = useQuery({
    queryKey: ['ticket_info', threadId, projectId],
    queryFn: async () => {
      if (!projectId || !threadId) return null;

      const { data, error } = await threadsApi.list({
        project_id: projectId,
        limit: 100,
      });
      if (error) throw error;

      const tickets = Array.isArray(data) ? data : [];
      return tickets.find((ticket) => ticket.thread_id === threadId) || null;
    },
    enabled: !!projectId && !!threadId,
  });

  const { data: ticketState } = useQuery({
    queryKey: ['ticket_state', threadId],
    queryFn: async () => {
      if (!threadId) return null;

      const { data, error } = await threadsApi.getState(threadId);
      if (error) throw error;

      if (data && typeof data === 'object' && 'state' in data) {
        return data.state as ThreadState;
      }
      return null;
    },
    enabled: !!threadId,
  });

  const { data: ticketResolution, isLoading: isResolutionLoading } = useQuery({
    queryKey: ['ticket_resolution', threadId],
    queryFn: async () => {
      if (!threadId) throw new Error(t('manager.ticket.threadNotSelected'));

      const { data, error } = await threadsApi.getResolution(threadId);
      if (error) throw error;

      return data as TicketResolution;
    },
    enabled: !!threadId,
  });

  const resolutionDraftKey = `${threadId ?? ''}:${ticketResolution?.version ?? 'none'}`;
  if (resolutionDraft.key !== resolutionDraftKey) {
    setResolutionDraft({
      key: resolutionDraftKey,
      text: ticketResolution?.summary_text ?? '',
    });
  }
  const resolutionText = resolutionDraft.text;

  const ticketClient =
    (ticketInfo?.client as Client | undefined) ?? ticketState?.client ?? null;
  const clientName = getClientDisplayName(ticketClient, t('ui.client.fallback'));
  const ticketStatus = ticketInfo?.status || ticketState?.status || 'waiting_manager';
  const isClosed = ticketStatus === 'closed';
  const hasResolution = ticketResolution !== undefined;
  const canEdit =
    isClosed &&
    hasResolution &&
    ['generated', 'edited', 'failed'].includes(ticketResolution.status);
  const canRegenerate =
    isClosed &&
    hasResolution &&
    ['generated', 'edited', 'failed', 'missing'].includes(ticketResolution.status);

  const claimMutation = useMutation({
    mutationFn: async () => {
      if (!threadId) throw new Error(t('manager.ticket.threadNotSelected'));
      const { error } = await threadsApi.claim(threadId);
      if (error) throw error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ticket_info', threadId] });
      void queryClient.invalidateQueries({ queryKey: ['ticket_state', threadId] });
      void queryClient.invalidateQueries({ queryKey: ['tickets'] });
    },
  });

  const closeMutation = useMutation({
    mutationFn: async () => {
      if (!threadId) throw new Error(t('manager.ticket.threadNotSelected'));
      const { error } = await threadsApi.close(threadId);
      if (error) throw error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ticket_info', threadId] });
      void queryClient.invalidateQueries({ queryKey: ['ticket_state', threadId] });
      void queryClient.invalidateQueries({ queryKey: ['tickets'] });
      void queryClient.invalidateQueries({ queryKey: ['ticket_resolution', threadId] });
    },
  });

  const saveResolutionMutation = useMutation({
    mutationFn: async () => {
      if (!threadId) throw new Error(t('manager.ticket.threadNotSelected'));
      const { error } = await threadsApi.updateResolution(threadId, {
        summary_text: resolutionText,
        expected_version: ticketResolution?.version ?? 0,
      });
      if (error) throw error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ticket_resolution', threadId] });
      void queryClient.invalidateQueries({ queryKey: ['ticket_state', threadId] });
    },
  });

  const regenerateResolutionMutation = useMutation({
    mutationFn: async () => {
      if (!threadId) throw new Error(t('manager.ticket.threadNotSelected'));
      const { error } = await threadsApi.regenerateResolution(threadId);
      if (error) throw error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ticket_resolution', threadId] });
      void queryClient.invalidateQueries({ queryKey: ['ticket_state', threadId] });
    },
  });

  useEffect(() => {
    if (!threadId || !ticketInfo) {
      return;
    }
    if (ticketInfo.status === 'waiting_manager' && !claimMutation.isPending) {
      claimMutation.mutate();
    }
  }, [claimMutation, threadId, ticketInfo]);

  const replyMutation = useMutation({
    mutationFn: async (message: string) => {
      if (!threadId) throw new Error(t('manager.ticket.threadNotSelected'));
      const { error } = await threadsApi.reply(threadId, message);
      if (error) throw error;
    },
    onSuccess: () => {
      setReplyText('');
      void queryClient.invalidateQueries({ queryKey: ['ticket_messages', threadId] });
      void queryClient.invalidateQueries({ queryKey: ['ticket_info', threadId] });
      void queryClient.invalidateQueries({ queryKey: ['ticket_state', threadId] });
      void queryClient.invalidateQueries({ queryKey: ['tickets'] });
    },
  });

  const ticketCreatedAt = ticketInfo?.thread_created_at
    ? new Date(ticketInfo.thread_created_at).toLocaleString()
    : '—';

  if (!threadId) {
    return (
      <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6">
        {t('manager.ticket.openFailed')}
      </div>
    );
  }
  if (messagesLoading) {
    return <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6">{t('common.states.loading')}</div>;
  }
  if (messagesError) {
    return (
      <div className="p-4 text-sm text-[var(--accent-danger-text)] sm:p-6">
        {t('common.feedback.error')}: {getErrorMessage(messagesError, t('manager.ticket.messagesLoadFailed'))}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6 lg:p-8">
      <div className="mb-6 flex flex-col gap-4 rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)]">
            {t('manager.ticket.title', { clientName })}
          </h1>
          <div className="mt-2 flex flex-wrap gap-4 text-sm text-[var(--text-secondary)]">
            <span>
              {t('manager.ticket.statusPrefix')} <span className="font-medium">{threadStatusLabel(ticketStatus)}</span>
            </span>
            <span>{t('manager.ticket.createdPrefix')} {ticketCreatedAt}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => closeMutation.mutate()}
          disabled={closeMutation.isPending || isClosed}
          className="min-h-10 rounded-lg border border-[var(--divider-soft)] bg-[var(--surface-secondary)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {closeMutation.isPending ? t('manager.ticket.closing') : t('manager.ticket.close')}
        </button>
      </div>

      <div className="mb-6 max-h-96 overflow-y-auto rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
        <h2 className="mb-3 font-medium text-[var(--text-primary)]">{t('manager.ticket.historyTitle')}</h2>
        {messages.length === 0 && <p className="text-[var(--text-muted)]">{t('manager.ticket.noMessages')}</p>}
        <div className="space-y-3">
          {messages.map((msg) => {
            const presentation = getMessagePresentation(msg, ticketClient);
            const isClientMessage = msg.role === 'user';
            const isManagerMessage = msg.role === 'manager';

            return (
              <div
                key={msg.id}
                className={`flex ${isClientMessage ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[70%] rounded-2xl px-4 py-2 shadow-sm ${
                    isClientMessage
                      ? 'bg-[var(--accent-primary)] text-white'
                      : isManagerMessage
                        ? 'bg-[var(--accent-muted)] text-[var(--accent-primary)] shadow-[var(--shadow-sm)]'
                        : 'bg-[var(--surface-secondary)] text-[var(--text-primary)] shadow-[var(--shadow-sm)]'
                  }`}
                >
                  <div className="mb-1 text-xs opacity-80">{presentation.label}</div>
                  <div className="whitespace-pre-wrap text-sm">{presentation.content}</div>
                  <div className="mt-1 text-right text-xs opacity-70">
                    {new Date(msg.created_at).toLocaleString()}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mb-6 rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="font-medium text-[var(--text-primary)]">{t('manager.ticket.resolution.title')}</h2>
          <span className="text-xs text-[var(--text-muted)]">
            {resolutionStatusLabel(ticketResolution?.status)} · v{ticketResolution?.version ?? 0}
          </span>
        </div>
        <textarea
          value={resolutionText}
          onChange={(event) =>
            setResolutionDraft({
              key: resolutionDraftKey,
              text: event.target.value,
            })
          }
          className="min-h-28 w-full rounded-lg bg-[var(--control-bg)] p-3 text-sm leading-relaxed text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          rows={4}
          disabled={saveResolutionMutation.isPending || regenerateResolutionMutation.isPending}
        />
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => saveResolutionMutation.mutate()}
            disabled={
              isResolutionLoading ||
              saveResolutionMutation.isPending ||
              !canEdit ||
              !resolutionText.trim()
            }
            className="min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saveResolutionMutation.isPending ? t('manager.ticket.resolution.saving') : t('manager.ticket.resolution.save')}
          </button>
          <button
            type="button"
            onClick={() => regenerateResolutionMutation.mutate()}
            disabled={
              isResolutionLoading ||
              regenerateResolutionMutation.isPending ||
              !canRegenerate
            }
            className="min-h-10 rounded-lg border border-[var(--divider-soft)] bg-[var(--surface-secondary)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {regenerateResolutionMutation.isPending ? t('manager.ticket.resolution.regenerating') : t('manager.ticket.resolution.regenerate')}
          </button>
        </div>
        {(saveResolutionMutation.isError || regenerateResolutionMutation.isError) && (
          <div className="mt-3 rounded-lg bg-[var(--accent-danger-bg)] p-3 text-sm text-[var(--accent-danger-text)]">
            {getErrorMessage(
              saveResolutionMutation.error || regenerateResolutionMutation.error,
              t('manager.ticket.resolution.saveFailed'),
            )}
          </div>
        )}
      </div>

      <div className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
        <textarea
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          className="min-h-28 w-full rounded-lg bg-[var(--control-bg)] p-3 text-sm leading-relaxed text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          rows={4}
          placeholder={t('manager.ticket.replyPlaceholder')}
          disabled={isClosed}
        />
        <button
          type="button"
          onClick={() => replyMutation.mutate(replyText)}
          disabled={isClosed || replyMutation.isPending || !replyText.trim()}
          className="mt-3 min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {replyMutation.isPending ? t('manager.ticket.sending') : t('manager.ticket.sendReply')}
        </button>
        {replyMutation.isError && (
          <div className="mt-3 rounded-lg bg-[var(--accent-danger-bg)] p-3 text-sm text-[var(--accent-danger-text)]">
            {getMutationErrorMessage(replyMutation.error)}
          </div>
        )}
      </div>
    </div>
  );
};
