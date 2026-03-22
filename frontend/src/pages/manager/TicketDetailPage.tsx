import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@shared/api/client';

export const TicketDetailPage: React.FC = () => {
  const { threadId } = useParams<{ threadId: string }>();
  const queryClient = useQueryClient();
  const [replyText, setReplyText] = useState('');

  // Загружаем историю сообщений треда (если есть API)
  // Предположим, что есть эндпоинт GET /api/threads/{id}/messages (его пока нет, но можно добавить)
  // Пока оставим заглушку
  const { data: ticket } = useQuery({
    queryKey: ['ticket', threadId],
    queryFn: () => api.threads.list().then(res => res.data?.find(t => t.id === threadId)), // временно
    enabled: !!threadId,
  });

  const replyMutation = useMutation({
    mutationFn: (message: string) => api.threads.reply(threadId!, message),
    onSuccess: () => {
      setReplyText('');
      queryClient.invalidateQueries({ queryKey: ['ticket', threadId] });
      queryClient.invalidateQueries({ queryKey: ['tickets'] });
    },
  });

  if (!ticket) return <div>Загрузка...</div>;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Тикет от {ticket.client_name || 'Клиент'}</h1>
      <div className="mb-4">
        <p className="text-gray-600">Статус: {ticket.status}</p>
        <p className="text-gray-600">Создан: {new Date(ticket.created_at).toLocaleString()}</p>
        {/* Здесь можно отобразить историю сообщений, но для этого нужен API */}
        <p className="mt-2">Последнее сообщение: {ticket.last_message}</p>
      </div>
      <div className="mt-4">
        <textarea
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          className="w-full border rounded p-2"
          rows={4}
          placeholder="Введите ответ..."
        />
        <button
          onClick={() => replyMutation.mutate(replyText)}
          disabled={replyMutation.isPending}
          className="mt-2 bg-green-600 text-white px-4 py-2 rounded"
        >
          {replyMutation.isPending ? 'Отправка...' : 'Отправить ответ'}
        </button>
      </div>
    </div>
  );
};