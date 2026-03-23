import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '../../shared/api/client';
import { useAppStore } from '../../app/store';
import type { Thread, Client, LastMessage } from '../../entities/thread/model/types';

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

  if (!selectedProjectId) return <div>Выберите проект</div>;
  if (isLoading) return <div>Загрузка тикетов...</div>;
  if (error) return <div>Ошибка: {String(error)}</div>;
  if (!data || data.length === 0) return <div>Нет открытых тикетов</div>;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Тикеты (ожидают ответа)</h1>
      <div className="space-y-2">
        {data.map((ticket: Thread) => {
          const client = ticket.client as unknown as Client;
          const lastMsg = ticket.last_message as unknown as LastMessage | null;
          return (
            <div key={ticket.thread_id} className="border p-3 rounded">
              <Link to={`/manager/tickets/${ticket.thread_id}`} className="text-blue-600 hover:underline">
                Тикет #{ticket.thread_id.slice(0, 8)} - {client?.full_name || client?.username || 'Клиент'}
              </Link>
              <p className="text-sm text-gray-600">
                {lastMsg?.content || 'Нет сообщений'}
              </p>
              <p className="text-xs text-gray-400">
                Создан: {new Date(ticket.thread_created_at).toLocaleString()}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
