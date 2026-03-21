import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAppStore } from '@/app/store';
import { api } from '@shared/api';

// Локальный тип для артефакта (соответствует тому, что приходит с API)
interface ApiArtifactType {
  type: string;
  allowed_parents: string[];
  requires_clarification: boolean;
  schema?: unknown;
  icon?: unknown;
}

const fetchArtifactTypes = async (): Promise<ApiArtifactType[]> => {
  const { data, error } = await api.artifactTypes.list();
  if (error) throw error;
  return (data as ApiArtifactType[]) || [];
};

/**
 * Хук для загрузки списка типов артефактов.
 * Сохраняет результат в Zustand store при успешной загрузке.
 */
export const useArtifactTypes = () => {
  const setArtifactTypes = useAppStore((s) => s.setArtifactTypes);

  const query = useQuery({
    queryKey: ['artifactTypes'],
    queryFn: fetchArtifactTypes,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (query.data) {
      const types = query.data.map((t) => ({
        type: t.type,
        allowed_parents: t.allowed_parents,
        requires_clarification: t.requires_clarification,
        schema: t.schema,
        icon: t.icon,
      }));
      setArtifactTypes(types);
    }
  }, [query.data, setArtifactTypes]);

  useEffect(() => {
    if (query.error) {
      console.warn('Failed to load artifact types:', query.error);
    }
  }, [query.error]);

  return query;
};
