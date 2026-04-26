import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';

import { api } from '@shared/api/client';

type TicketListItem = {
  thread_id: string;
  client?: {
    full_name?: string | null;
    username?: string | null;
  } | null;
  last_message?: {
    content?: string | null;
  } | null;
};

const normalizeTickets = (payload: unknown): TicketListItem[] => {
  return Array.isArray(payload) ? (payload as TicketListItem[]) : [];
};

export const TicketsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();

  const { data: tickets = [], isLoading } = useQuery<TicketListItem[]>({
    queryKey: ['tickets', 'manual', projectId],
    queryFn: async () => {
      if (!projectId) return [];

      const { data, error } = await api.GET('/api/threads', {
        params: {
          query: {
            project_id: projectId,
            status: 'manual',
          },
        },
      });

      if (error) throw error;
      return normalizeTickets(data);
    },
    enabled: !!projectId,
  });

  if (!projectId) return <div className="p-6 text-[var(--text-muted)]">Выберите проект</div>;

  if (isLoading) {
    return <div className="p-6 text-[var(--text-muted)]">Загрузка тикетов...</div>;
  }

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Тикеты</h1>

      {tickets.length === 0 ? (
        <div className="text-[var(--text-muted)]">Нет активных тикетов.</div>
      ) : (
        <div className="space-y-2">
          {tickets.map((ticket) => (
            <Link
              key={ticket.thread_id}
              to={`/projects/${projectId}/tickets/${ticket.thread_id}`}
              className="block rounded-lg border border-[var(--border-subtle)] bg-white p-4 hover:shadow-sm"
            >
              <div className="font-medium text-[var(--text-primary)]">
                {ticket.client?.full_name || ticket.client?.username || ticket.thread_id}
              </div>
              <div className="text-sm text-[var(--text-muted)]">
                {ticket.last_message?.content || 'Без последнего сообщения'}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};
