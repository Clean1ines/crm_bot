import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { useNotification } from '@/shared/lib/notification/useNotifications';
import { useProjectManagers } from '@entities/project/api/useCrmData';
import { getErrorMessage } from '@shared/api/core/errors';
import { membersApi } from '@shared/api/modules/members';
import { projectsApi } from '@shared/api/modules/projects';
import { Button } from '@shared/ui';

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
        throw new Error(newMemberRole === 'manager' ? 'Введите Telegram chat_id менеджера' : 'Введите user_id участника платформы');
      }

      if (newMemberRole === 'manager') {
        const chatId = Number(normalizedUserId);
        if (!Number.isInteger(chatId)) {
          throw new Error('Telegram chat_id менеджера должен быть числом');
        }

        const { error } = await projectsApi.addManager(projectId, chatId);
        if (error) {
          throw new Error(getErrorMessage(error));
        }
        return;
      }

      await membersApi.upsert(projectId, {
        user_id: normalizedUserId,
        role: newMemberRole,
      });
    },
    onSuccess: async () => {
      await invalidateManagers();
      setNewMemberUserId('');
      setNewMemberRole('manager');
      showNotification(newMemberRole === 'manager' ? 'Менеджер добавлен' : 'Участник проекта сохранён', 'success');
    },
    onError: (error) => showNotification(getErrorMessage(error), 'error'),
  });

  const removeMutation = useMutation({
    mutationFn: async (memberUserId: string) => {
      await membersApi.remove(projectId, memberUserId);
    },
    onSuccess: async () => {
      await invalidateManagers();
      showNotification('Участник проекта удалён', 'success');
    },
    onError: (error) => showNotification(getErrorMessage(error), 'error'),
  });

  if (isLoading) {
    return <div className="text-sm text-[var(--text-muted)]">Загрузка...</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-[var(--text-primary)]">Команда проекта</h3>
        <ul className="mt-3 space-y-2">
          {managers.map((manager) => (
            <li key={manager.user_id} className="flex items-center justify-between rounded-lg bg-[var(--surface-secondary)] px-3 py-2 text-sm">
              <span>
                {manager.full_name || manager.username || manager.email || manager.user_id}
                <span className="ml-2 inline-flex min-h-6 items-center rounded-full bg-[var(--accent-muted)] px-2 text-xs font-medium text-[var(--accent-primary)]">({manager.role})</span>
              </span>
              <button
                onClick={() => removeMutation.mutate(manager.user_id)}
                className="text-sm font-medium text-[var(--accent-danger-text)] hover:underline"
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
          placeholder={newMemberRole === 'manager' ? 'Telegram chat_id менеджера' : 'user_id участника'}
          className="min-h-10 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
        />
        <select
          value={newMemberRole}
          onChange={(e) => setNewMemberRole(e.target.value as (typeof ROLE_OPTIONS)[number])}
          className="min-h-10 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
        >
          {ROLE_OPTIONS.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
        <Button
          variant="primary"
          onClick={() => addMutation.mutate()}
          disabled={addMutation.isPending}
        >
          Добавить
        </Button>
      </div>
    </div>
  );
};
