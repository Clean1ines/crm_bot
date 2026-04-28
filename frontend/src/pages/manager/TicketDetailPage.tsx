import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Message, Client } from '../../entities/thread/model/types';
import { getClientDisplayName } from '../../shared/lib/clients';
import { threadsApi } from '../../shared/api/modules/threads';

export const TicketDetailPage: React.FC = () => {
  const { projectId, threadId } = useParams<{ projectId: string; threadId: string }>();
  const queryClient = useQueryClient();
  const [replyText, setReplyText] = useState('');

  const { data: messagesData, isLoading: messagesLoading, error: messagesError } = useQuery({
    queryKey: ['ticket_messages', threadId],
    queryFn: async () => {
      if (!threadId) throw new Error('No thread ID');

      const { data, error } = await threadsApi.getMessages(threadId);
      if (error) throw error;

      return data;
    },
    enabled: !!threadId,
  });

  const messages: Message[] =
    messagesData && typeof messagesData === 'object' && 'messages' in messagesData && Array.isArray(messagesData.messages)
      ? (messagesData.messages as Message[])
      : [];

  const { data: ticketInfo } = useQuery({
    queryKey: ['ticket_info', threadId, projectId],
    queryFn: async () => {
      if (!projectId || !threadId) return null;

      const { data, error } = await threadsApi.list({
        project_id: projectId,
        status_filter: 'manual',
      });

      if (error) throw error;

      const tickets = Array.isArray(data) ? data : [];
      return tickets.find((ticket) => ticket.thread_id === threadId) || null;
    },
    enabled: !!projectId && !!threadId,
  });

  const clientName = getClientDisplayName(ticketInfo?.client as unknown as Client | undefined, 'Клиент');

  const replyMutation = useMutation({
    mutationFn: (message: string) => {
      if (!threadId) throw new Error('No thread ID');
      return threadsApi.reply(threadId, message);
    },
    onSuccess: () => {
      setReplyText('');
      queryClient.invalidateQueries({ queryKey: ['ticket_messages', threadId] });
      queryClient.invalidateQueries({ queryKey: ['tickets', 'manual'] });
      queryClient.invalidateQueries({ queryKey: ['ticket_info', threadId] });
    },
  });

  if (!threadId) return <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6">Некорректный ID тикета</div>;
  if (messagesLoading) return <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6">Загрузка...</div>;
  if (messagesError) return <div className="p-4 text-sm text-[var(--accent-danger-text)] sm:p-6">Ошибка: {String(messagesError)}</div>;

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6 lg:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)]">Тикет от {clientName}</h1>
        <div className="mt-2 flex gap-4 text-sm text-[var(--text-secondary)]">
          <span>Статус: <span className="font-medium">{ticketInfo?.status || 'manual'}</span></span>
          <span>Создан: {ticketInfo ? new Date(ticketInfo.thread_created_at).toLocaleString() : '—'}</span>
        </div>
      </div>

      <div className="mb-6 max-h-96 overflow-y-auto rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
        <h2 className="font-medium text-[var(--text-primary)] mb-3">История диалога</h2>
        {messages.length === 0 && <p className="text-[var(--text-muted)]">Нет сообщений</p>}
        <div className="space-y-3">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[70%] rounded-2xl px-4 py-2 shadow-sm ${
                  msg.role === 'user'
                    ? 'bg-[var(--accent-primary)] text-white'
                    : 'bg-[var(--surface-secondary)] text-[var(--text-primary)] shadow-[var(--shadow-sm)]'
                }`}
              >
                <div className="text-xs opacity-80 mb-1">
                  {msg.role === 'user' ? 'Клиент' : 'Бот'}
                </div>
                <div className="text-sm">{msg.content}</div>
                <div className="text-xs opacity-70 mt-1 text-right">
                  {new Date(msg.created_at).toLocaleString()}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
        <textarea
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          className="min-h-28 w-full rounded-lg bg-[var(--control-bg)] p-3 text-sm leading-relaxed text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          rows={4}
          placeholder="Введите ответ..."
        />
        <button
          onClick={() => replyMutation.mutate(replyText)}
          disabled={replyMutation.isPending || !replyText.trim()}
          className="mt-3 min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {replyMutation.isPending ? 'Отправка...' : 'Отправить ответ'}
        </button>
      </div>
    </div>
  );
};
