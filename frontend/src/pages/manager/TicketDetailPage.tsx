import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import { useAppStore } from '../../app/store';
import type { Message } from '../../entities/thread/model/types';

export const TicketDetailPage: React.FC = () => {
  const { threadId } = useParams<{ threadId: string }>();
  const { selectedProjectId } = useAppStore();
  const queryClient = useQueryClient();
  const [replyText, setReplyText] = useState('');

  // Load messages for the thread
  const { data: messagesData, isLoading: messagesLoading, error: messagesError } = useQuery({
    queryKey: ['ticket_messages', threadId],
    queryFn: async () => {
      if (!threadId) throw new Error('No thread ID');
      const { data, error } = await api.threads.getMessages(threadId);
      if (error) throw error;
      return data;
    },
    enabled: !!threadId,
  });

  const messages: Message[] =
    messagesData && typeof messagesData === 'object' && 'messages' in messagesData && Array.isArray(messagesData.messages)
      ? (messagesData.messages as Message[])
      : [];

  // Load ticket info (to get client name)
  const { data: ticketInfo } = useQuery({
    queryKey: ['ticket_info', threadId, selectedProjectId],
    queryFn: async () => {
      if (!selectedProjectId || !threadId) return null;
      const { data, error } = await api.threads.list({
        project_id: selectedProjectId,
        status_filter: 'manual',
      });
      if (error) throw error;
      return data?.find(t => t.thread_id === threadId) || null;
    },
    enabled: !!selectedProjectId && !!threadId,
  });

  const clientName = (ticketInfo?.client as unknown as { full_name?: string; username?: string })?.full_name ||
                     (ticketInfo?.client as unknown as { full_name?: string; username?: string })?.username ||
                     'Клиент';

  const replyMutation = useMutation({
    mutationFn: (message: string) => api.threads.reply(threadId!, message),
    onSuccess: () => {
      setReplyText('');
      queryClient.invalidateQueries({ queryKey: ['ticket_messages', threadId] });
      queryClient.invalidateQueries({ queryKey: ['tickets', 'manual'] });
      queryClient.invalidateQueries({ queryKey: ['ticket_info', threadId] });
    },
  });

  if (!threadId) return <div className="p-6 text-[var(--text-muted)]">Некорректный ID тикета</div>;
  if (messagesLoading) return <div className="p-6 text-[var(--text-muted)]">Загрузка...</div>;
  if (messagesError) return <div className="p-6 text-[var(--accent-danger)]">Ошибка: {String(messagesError)}</div>;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Тикет от {clientName}</h1>
        <div className="mt-2 flex gap-4 text-sm text-[var(--text-secondary)]">
          <span>Статус: <span className="font-medium">{ticketInfo?.status || 'manual'}</span></span>
          <span>Создан: {ticketInfo ? new Date(ticketInfo.thread_created_at).toLocaleString() : '—'}</span>
        </div>
      </div>

      <div className="bg-[var(--surface-card)] border border-[var(--border-subtle)] rounded-xl p-4 mb-6 max-h-96 overflow-y-auto shadow-sm">
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
                    : 'bg-[var(--surface-secondary)] text-[var(--text-primary)] border border-[var(--border-subtle)]'
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

      <div className="bg-[var(--surface-card)] border border-[var(--border-subtle)] rounded-xl p-4 shadow-sm">
        <textarea
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          className="w-full border border-[var(--border-subtle)] rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)] focus:border-transparent bg-white text-[var(--text-primary)]"
          rows={4}
          placeholder="Введите ответ..."
        />
        <button
          onClick={() => replyMutation.mutate(replyText)}
          disabled={replyMutation.isPending || !replyText.trim()}
          className="mt-3 px-4 py-2 bg-[var(--accent-primary)] text-white rounded-lg hover:bg-[var(--accent-primary)]/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {replyMutation.isPending ? 'Отправка...' : 'Отправить ответ'}
        </button>
      </div>
    </div>
  );
};
