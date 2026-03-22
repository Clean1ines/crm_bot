import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@shared/api/client';
import { useNotification } from '@/shared/lib/notification/useNotifications';

export const ManagersList: React.FC<{ projectId: string }> = ({ projectId }) => {
  const queryClient = useQueryClient();
  const { showNotification } = useNotification();
  const [newManagerId, setNewManagerId] = useState('');

  const { data: managers, isLoading } = useQuery({
    queryKey: ['managers', projectId],
    queryFn: () => api.projects.getManagers(projectId).then(res => res.data || []),
  });

  const addMutation = useMutation({
    mutationFn: (chatId: number) => api.projects.addManager(projectId, chatId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['managers', projectId] });
      setNewManagerId('');
      showNotification('Менеджер добавлен', 'success');
    },
    onError: () => showNotification('Ошибка добавления', 'error'),
  });

  const removeMutation = useMutation({
    mutationFn: (chatId: number) => api.projects.removeManager(projectId, chatId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['managers', projectId] });
      showNotification('Менеджер удалён', 'success');
    },
    onError: () => showNotification('Ошибка удаления', 'error'),
  });

  const handleAdd = () => {
    const chatId = parseInt(newManagerId, 10);
    if (isNaN(chatId)) {
      showNotification('Введите корректный chat_id', 'error');
      return;
    }
    addMutation.mutate(chatId);
  };

  if (isLoading) return <div>Загрузка...</div>;

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-medium">Менеджеры</h3>
        <ul>
          {managers?.map(m => (
            <li key={m} className="flex justify-between items-center py-1">
              <span>{m}</span>
              <button
                onClick={() => removeMutation.mutate(m)}
                className="text-red-600 hover:underline"
              >
                Удалить
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <input
          type="number"
          value={newManagerId}
          onChange={e => setNewManagerId(e.target.value)}
          placeholder="chat_id"
          className="border rounded p-1"
        />
        <button onClick={handleAdd} className="ml-2 bg-green-600 text-white px-3 py-1 rounded">
          Добавить
        </button>
      </div>
    </div>
  );
};