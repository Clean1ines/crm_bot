import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAppStore } from '@/app/store';
import { useProjectStore } from '@entities/project';
import { api } from '@shared/api';

// Локальный тип для артефакта (соответствует тому, что приходит с API)
interface ApiArtifact {
  id: string;
  type: string;
  parent_id?: string | null;
  content?: unknown;
  created_at: string;
  updated_at: string;
  version: string;
  status: string;
  summary?: string;
}

/**
 * Хук для загрузки артефактов выбранного проекта.
 * Сохраняет результат в Zustand store при успешной загрузке.
 */
export const useArtifacts = () => {
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const setArtifacts = useAppStore((s) => s.setArtifacts);

  const query = useQuery({
    queryKey: ['artifacts', currentProjectId],
    queryFn: async (): Promise<ApiArtifact[]> => {
      if (!currentProjectId) return [];
      const { data, error } = await api.artifacts.list(currentProjectId);
      if (error) throw error;
      return (data as ApiArtifact[]) || [];
    },
    enabled: !!currentProjectId,
  });

  useEffect(() => {
    if (query.data) {
      const artifacts = query.data.map((a) => ({
        id: a.id,
        type: a.type,
        parent_id: a.parent_id ?? null,
        content: (a.content ?? {}) as Record<string, unknown>,
        created_at: a.created_at,
        updated_at: a.updated_at,
        version: a.version,
        status: a.status,
        summary: a.summary,
      }));
      setArtifacts(artifacts);
    }
  }, [query.data, setArtifacts]);

  useEffect(() => {
    if (query.error) {
      console.warn('Failed to load artifacts:', query.error);
    }
  }, [query.error]);

  return query;
};
