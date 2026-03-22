import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@shared/api/client';
import { Link } from 'react-router-dom';

export const TicketsPage: React.FC = () => {
  const { data, isLoading, error } = useQuery({
    queryKey: ['tickets', 'manual'],
    queryFn: () => api.threads.list('manual').then(res => res.data),
  });

  if (isLoading) return <div>Загрузка тикетов...</div>;
  if (error) return <div>Ошибка: {error.message}</div>;
  if (!data || data.length === 0) return <div>Нет открытых тикетов</div>;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Тикеты (ожидают ответа)</h1>
      <div className="space-y-2">
        {data.map(ticket => (
          <div key={ticket.id} className="border p-3 rounded">
            <Link to={`/manager/tickets/${ticket.id}`} className="text-blue-600 hover:underline">
              Тикет #{ticket.id.slice(0, 8)} - {ticket.client_name || 'Клиент'}
            </Link>
            <p className="text-sm text-gray-600">{ticket.last_message || 'Нет сообщений'}</p>
            <p className="text-xs text-gray-400">Создан: {new Date(ticket.created_at).toLocaleString()}</p>
          </div>
        ))}
      </div>
    </div>
  );
};