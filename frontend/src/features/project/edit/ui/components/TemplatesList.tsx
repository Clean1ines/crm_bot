import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@shared/api/client';
import { useNotification } from '@/shared/lib/notification/useNotifications';

export const TemplatesList: React.FC<{ projectId: string }> = ({ projectId }) => {
  const queryClient = useQueryClient();
  const { showNotification } = useNotification();

  const { data: templates, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => api.templates.list().then(res => res.data || []),
  });

  const applyMutation = useMutation({
    mutationFn: (slug: string) => api.templates.apply(projectId, slug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      showNotification('Шаблон применён', 'success');
    },
    onError: () => showNotification('Ошибка применения', 'error'),
  });

  if (isLoading) return <div>Загрузка...</div>;

  return (
    <div className="space-y-2">
      {templates?.map(t => (
        <div key={t.id} className="border p-3 rounded">
          <div className="font-bold">{t.name}</div>
          <div className="text-sm text-gray-600">{t.description}</div>
          <button
            onClick={() => applyMutation.mutate(t.slug)}
            className="mt-2 bg-blue-600 text-white px-3 py-1 rounded"
          >
            Применить
          </button>
        </div>
      ))}
    </div>
  );
};