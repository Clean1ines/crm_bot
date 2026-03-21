import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAppStore } from '@/app/store';
import { api } from '@shared/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string; // ISO string from backend
}

export const useExecutionMessages = (executionId: string | null) => {
  const setMessages = useAppStore((s) => s.setMessages);

  const query = useQuery({
    queryKey: ['execution-messages', executionId],
    queryFn: async (): Promise<Message[]> => {
      if (!executionId) return [];
      const { data, error } = await api.executions.getMessages(executionId);
      if (error) throw error;
      const raw = data || [];
      // Преобразуем ответ в нужный формат, используя явный тип из API (или unknown)
      return raw.map((item: unknown) => {
        const msg = item as { role?: string; content?: string; timestamp?: string };
        return {
          role: msg.role === 'user' || msg.role === 'assistant' ? msg.role : 'assistant',
          content: msg.content || '',
          timestamp: msg.timestamp || new Date().toISOString(),
        };
      });
    },
    enabled: !!executionId,
  });

  useEffect(() => {
    if (query.data) {
      // Convert to store format (timestamp as number)
      const messages = query.data.map((msg) => ({
        role: msg.role,
        content: msg.content,
        timestamp: new Date(msg.timestamp).getTime(),
      }));
      setMessages(messages);
    }
  }, [query.data, setMessages]);

  return query;
};