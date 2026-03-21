import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAppStore } from '@/app/store';
import { api } from '@shared/api';

// Локальный тип для режима (API возвращает id, name, default)
interface ApiMode {
  id: string;
  name: string;
  default?: boolean;
}

const fetchModes = async (): Promise<ApiMode[]> => {
  const { data, error } = await api.modes.list();
  if (error) throw error;
  return (data as ApiMode[]) || [];
};

/**
 * Хук для загрузки списка доступных режимов промптов.
 * Сохраняет результат в Zustand store при успешной загрузке.
 */
export const useModes = () => {
  const setModes = useAppStore((s) => s.setModes);

  const query = useQuery({
    queryKey: ['modes'],
    queryFn: fetchModes,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (query.data) {
      const modes = query.data.map((m) => ({
        id: m.id,
        name: m.name,
        default: m.default,
      }));
      setModes(modes);
    }
  }, [query.data, setModes]);

  useEffect(() => {
    if (query.error) {
      console.warn('Failed to load modes:', query.error);
    }
  }, [query.error]);

  return query;
};
