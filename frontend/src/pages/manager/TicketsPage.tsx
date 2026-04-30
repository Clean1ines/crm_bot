import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { MANAGER_THREAD_FILTER } from '../../entities/thread/model/status';
import type { Thread, Client, LastMessage } from '../../entities/thread/model/types';
import { getClientDisplayName } from '../../shared/lib/clients';
import { threadsApi } from '../../shared/api/modules/threads';

export const TicketsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();

  const { data, isLoading, error } = useQuery({
    queryKey: ['tickets', MANAGER_THREAD_FILTER, projectId],
    queryFn: async () => {
      if (!projectId) return [];

      const { data, error } = await threadsApi.list({
        project_id: projectId,
        status_filter: MANAGER_THREAD_FILTER,
        limit: 100,
      });

      if (error) throw error;
      return Array.isArray(data) ? data : [];
    },
    enabled: !!projectId,
  });

  if (!projectId) return <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6">Выберите проект</div>;
  if (isLoading) return <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6">Загрузка тикетов...</div>;
  if (error) return <div className="p-4 text-sm text-[var(--accent-danger-text)] sm:p-6">Ошибка: {String(error)}</div>;
  if (!data || data.length === 0) return <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6">Нет открытых тикетов</div>;

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6 lg:p-8">
      <h1 className="mb-5 text-2xl font-semibold leading-tight text-[var(--text-primary)]">Тикеты (ожидают ответа)</h1>
      <div className="space-y-3">
        {data.map((ticket: Thread) => {
          const client = ticket.client as unknown as Client;
          const lastMsg = ticket.last_message as unknown as LastMessage | null;
          const clientName = getClientDisplayName(client, 'Клиент');

          return (
            <div
              key={ticket.thread_id}
              className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] transition-shadow hover:shadow-md"
            >
              <Link
                to={`/projects/${projectId}/tickets/${ticket.thread_id}`}
                className="font-medium text-[var(--accent-primary)] hover:underline"
              >
                Заявка от {clientName}
              </Link>
              <p className="mt-1 line-clamp-2 text-sm text-[var(--text-secondary)]">
                {lastMsg?.content || 'Нет сообщений'}
              </p>
              <p className="mt-2 text-xs text-[var(--text-muted)]">
                Создан: {new Date(ticket.thread_created_at).toLocaleString()}
              </p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                ID диалога: {ticket.thread_id.slice(0, 8)}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
