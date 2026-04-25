import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { useNotification } from '@/shared/lib/notification/useNotifications';
import { useProjectManagers } from '@entities/project/api/useCrmData';
import { api, getErrorMessage } from '@shared/api/client';

const ROLE_OPTIONS = ['manager', 'admin', 'owner'] as const;

export const ManagersList: React.FC<{ projectId: string }> = ({ projectId }) => {
  const queryClient = useQueryClient();
  const { showNotification } = useNotification();
  const [newMemberUserId, setNewMemberUserId] = useState('');
  const [newMemberRole, setNewMemberRole] = useState<(typeof ROLE_OPTIONS)[number]>('manager');

  const { data: managers = [], isLoading } = useProjectManagers(projectId);

  const invalidateManagers = async () => {
    await queryClient.invalidateQueries({ queryKey: ['members', projectId] });
  };

  const addMutation = useMutation({
    mutationFn: async () => {
      const normalizedUserId = newMemberUserId.trim();
      if (!normalizedUserId) {
        throw new Error('Введите user_id участника платформы');
      }

      await api.members.upsert(projectId, {
        user_id: normalizedUserId,
        role: newMemberRole,
      });
    },
    onSuccess: async () => {
      await invalidateManagers();
      setNewMemberUserId('');
      setNewMemberRole('manager');
      showNotification('Участник проекта сохранён', 'success');
    },
    onError: (error) => showNotification(getErrorMessage(error), 'error'),
  });

  const removeMutation = useMutation({
    mutationFn: async (memberUserId: string) => {
      await api.members.remove(projectId, memberUserId);
    },
    onSuccess: async () => {
      await invalidateManagers();
      showNotification('Участник проекта удалён', 'success');
    },
    onError: (error) => showNotification(getErrorMessage(error), 'error'),
  });

  if (isLoading) {
    return <div>Загрузка...</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-medium">Команда проекта</h3>
        <ul>
          {managers.map((manager) => (
            <li key={manager.user_id} className="flex items-center justify-between py-1">
              <span>
                {manager.full_name || manager.username || manager.email || manager.user_id}
                <span className="ml-2 text-xs text-gray-500">({manager.role})</span>
              </span>
              <button
                onClick={() => removeMutation.mutate(manager.user_id)}
                className="text-red-600 hover:underline"
              >
                Удалить
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-wrap gap-2">
        <input
          type="text"
          value={newMemberUserId}
          onChange={(e) => setNewMemberUserId(e.target.value)}
          placeholder="user_id участника"
          className="rounded border p-1"
        />
        <select
          value={newMemberRole}
          onChange={(e) => setNewMemberRole(e.target.value as (typeof ROLE_OPTIONS)[number])}
          className="rounded border p-1"
        >
          {ROLE_OPTIONS.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
        <button
          onClick={() => addMutation.mutate()}
          className="rounded bg-green-600 px-3 py-1 text-white"
        >
          Добавить
        </button>
      </div>
    </div>
  );
};
