import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAppStore } from '@/app/store';
import { api } from '@shared/api';

// Локальный тип для модели (API возвращает массив объектов с id)
interface ApiModel {
  id: string;
}

const fetchModels = async (): Promise<ApiModel[]> => {
  const { data, error } = await api.models.list();
  if (error) throw error;
  return (data as ApiModel[]) || [];
};

/**
 * Хук для загрузки списка доступных моделей LLM.
 * Сохраняет результат в Zustand store при успешной загрузке.
 */
export const useModels = () => {
  const setModels = useAppStore((s) => s.setModels);

  const query = useQuery({
    queryKey: ['models'],
    queryFn: fetchModels,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (query.data) {
      const models = query.data.map((m) => ({ id: m.id }));
      setModels(models);
    }
  }, [query.data, setModels]);

  useEffect(() => {
    if (query.error) {
      console.warn('Failed to load models:', query.error);
    }
  }, [query.error]);

  return query;
};
