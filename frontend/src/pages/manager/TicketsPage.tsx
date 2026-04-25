import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '../../shared/api/client';
import { useAppStore } from '../../app/store';
import type { Thread, Client, LastMessage } from '../../entities/thread/model/types';
import { getClientDisplayName } from '../../shared/lib/clients';

export const TicketsPage: React.FC = () => {
  const { selectedProjectId } = useAppStore();

  const { data, isLoading, error } = useQuery({
    queryKey: ['tickets', 'manual', selectedProjectId],
    queryFn: async () => {
      if (!selectedProjectId) return [];
      const { data, error } = await api.threads.list({
        project_id: selectedProjectId,
        status_filter: 'manual',
        limit: 100,
      });
      if (error) throw error;
      return data || [];
    },
    enabled: !!selectedProjectId,
  });

  if (!selectedProjectId) return <div className="p-6 text-[var(--text-muted)]">Выберите проект</div>;
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
              className="bg-[var(--surface-card)] border border-[var(--border-subtle)] rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow"
            >
              <Link
                to={`/projects/${selectedProjectId}/tickets/${ticket.thread_id}`}
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
