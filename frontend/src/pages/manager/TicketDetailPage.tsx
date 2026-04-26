import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import { api } from '@shared/api/client';

type TicketMessage = {
  id?: string | null;
  role?: string | null;
  content?: string | null;
  created_at?: string | null;
};

type TicketMessagesResponse = {
  messages?: TicketMessage[];
};

const normalizeTicketMessages = (payload: unknown): TicketMessage[] => {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return [];
  }

  const messages = (payload as TicketMessagesResponse).messages;
  return Array.isArray(messages) ? messages : [];
};

export const TicketDetailPage: React.FC = () => {
  const { projectId, threadId } = useParams<{ projectId: string; threadId: string }>();

  const { data: messages = [], isLoading } = useQuery<TicketMessage[]>({
    queryKey: ['ticket_info', threadId, projectId],
    queryFn: async () => {
      if (!projectId || !threadId) return [];

      const { data, error } = await api.GET('/api/threads/{thread_id}/messages', {
        params: {
          path: { thread_id: threadId },
          query: {
            limit: 100,
            offset: 0,
          },
        },
      });

      if (error) throw error;
      return normalizeTicketMessages(data);
    },
    enabled: !!projectId && !!threadId,
  });

  if (!projectId || !threadId) {
    return <div className="p-6 text-[var(--text-muted)]">Тикет не выбран</div>;
  }

  if (isLoading) {
    return <div className="p-6 text-[var(--text-muted)]">Загрузка тикета...</div>;
  }

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Тикет</h1>

      <div className="space-y-2">
        {messages.map((message) => (
          <div
            key={message.id || `${message.role}-${message.created_at}-${message.content}`}
            className="rounded-lg border border-[var(--border-subtle)] bg-white p-4"
          >
            <div className="mb-1 text-xs uppercase tracking-wide text-[var(--text-muted)]">
              {message.role || 'message'}
            </div>
            <div className="text-sm text-[var(--text-primary)]">{message.content || ''}</div>
          </div>
        ))}

        {messages.length === 0 ? (
          <div className="text-[var(--text-muted)]">Сообщений пока нет.</div>
        ) : null}
      </div>
    </div>
  );
};
