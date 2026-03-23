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

  if (!threadId) return <div>Некорректный ID тикета</div>;
  if (messagesLoading) return <div>Загрузка...</div>;
  if (messagesError) return <div>Ошибка: {String(messagesError)}</div>;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Тикет от {clientName}</h1>
      <div className="mb-4">
        <p className="text-gray-600">Статус: {ticketInfo?.status || 'manual'}</p>
        <p className="text-gray-600">Создан: {ticketInfo ? new Date(ticketInfo.thread_created_at).toLocaleString() : '—'}</p>
      </div>
      <div className="border rounded p-4 mb-4 max-h-96 overflow-y-auto">
        <h2 className="font-semibold mb-2">История диалога</h2>
        {messages.length === 0 && <p className="text-gray-500">Нет сообщений</p>}
        {messages.map((msg) => (
          <div key={msg.id} className={`mb-2 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
            <div className={`inline-block p-2 rounded ${msg.role === 'user' ? 'bg-blue-100' : 'bg-gray-100'}`}>
              <div className="text-xs text-gray-500">{msg.role === 'user' ? 'Клиент' : 'Бот'}</div>
              <div>{msg.content}</div>
              <div className="text-xs text-gray-400">{new Date(msg.created_at).toLocaleString()}</div>
            </div>
          </div>
        ))}
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
          disabled={replyMutation.isPending || !replyText.trim()}
          className="mt-2 bg-green-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          {replyMutation.isPending ? 'Отправка...' : 'Отправить ответ'}
        </button>
      </div>
    </div>
  );
};
