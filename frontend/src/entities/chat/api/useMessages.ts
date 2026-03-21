import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useProjectStore } from '@entities/project';
import { useAppStore } from '@/app/store';
import { api } from '@shared/api';

interface MessageArtifact {
  id?: string;
  type?: string;
  parent_id?: string | null;
  content?: {
    role?: string;
    content?: string;
  };
  created_at?: string;
  updated_at?: string;
  version?: string;
  status?: string;
  summary?: string;
}

/**
 * Хук для загрузки сообщений выбранного проекта.
 * Сохраняет результат в Zustand store при успешной загрузке.
 */
export const useMessages = () => {
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const setMessages = useAppStore((s) => s.setMessages);

  const query = useQuery({
    queryKey: ['messages', currentProjectId],
    queryFn: async (): Promise<MessageArtifact[]> => {
      if (!currentProjectId) return [];
      const { data, error } = await api.messages.list(currentProjectId);
      if (error) throw error;
      return (data as MessageArtifact[]) || [];
    },
    enabled: !!currentProjectId,
  });

  useEffect(() => {
    if (query.data) {
      const messages = query.data.map((m) => {
        const role = m.content?.role;
        const validRole = (role === 'user' || role === 'assistant')
          ? (role as 'user' | 'assistant')
          : 'assistant';
        return {
          role: validRole,
          content: m.content?.content || '',
          timestamp: new Date(m.created_at || '').getTime(),
        };
      });
      setMessages(messages);
    }
  }, [query.data, setMessages]);

  useEffect(() => {
    if (query.error) {
      console.warn('Failed to load messages:', query.error);
    }
  }, [query.error]);

  return query;
};
