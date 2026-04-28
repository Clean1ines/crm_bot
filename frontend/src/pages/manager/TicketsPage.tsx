import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import type { Thread, Client, LastMessage } from '../../entities/thread/model/types';
import { getClientDisplayName } from '../../shared/lib/clients';
import { threadsApi } from '../../shared/api/modules/threads';

export const TicketsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();

  const { data, isLoading, error } = useQuery({
    queryKey: ['tickets', 'manual', projectId],
    queryFn: async () => {
      if (!projectId) return [];

      const { data, error } = await threadsApi.list({
        project_id: projectId,
        status_filter: 'manual',
        limit: 100,
      });

      if (error) throw error;
      return Array.isArray(data) ? data : [];
    },
    enabled: !!projectId,
  });

  if (!projectId) return <div className="p-6 text-[var(--text-muted)]">Выберите проект</div>;
  if (isLoading) return <div className="p-6 text-[var(--text-muted)]">Загрузка тикетов...</div>;
  if (error) return <div className="p-6 text-[var(--accent-danger)]">Ошибка: {String(error)}</div>;
  if (!data || data.length === 0) return <div className="p-6 text-[var(--text-muted)]">Нет открытых тикетов</div>;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-semibold text-[var(--text-primary)] mb-6">Тикеты (ожидают ответа)</h1>
      <div className="space-y-3">
        {data.map((ticket: Thread) => {
          const client = ticket.client as unknown as Client;
          const lastMsg = ticket.last_message as unknown as LastMessage | null;
          const clientName = getClientDisplayName(client, 'Клиент');

          return (
            <div
              key={ticket.thread_id}
              className="rounded-xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] hover:shadow-md transition-shadow"
            >
              <Link
                to={`/projects/${projectId}/tickets/${ticket.thread_id}`}
                className="text-[var(--accent-primary)] font-medium hover:underline"
              >
                Тикет #{ticket.thread_id.slice(0, 8)} - {clientName}
              </Link>
              <p className="text-sm text-[var(--text-secondary)] mt-1 line-clamp-2">
                {lastMsg?.content || 'Нет сообщений'}
              </p>
              <p className="text-xs text-[var(--text-muted)] mt-2">
                Создан: {new Date(ticket.thread_created_at).toLocaleString()}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
