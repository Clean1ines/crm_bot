import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { History, Search, Shield, Trash2, User, XCircle, CheckCircle2 } from 'lucide-react';
import { useParams } from 'react-router-dom';

import { useProjectManagers, type ProjectMember } from '@entities/project/api/useCrmData';
import { getErrorMessage } from '@shared/api/core/errors';
import { membersApi } from '@shared/api/modules/members';
import { projectsApi } from '@shared/api/modules/projects';
import { Button } from '@shared/ui';

const ROLE_OPTIONS = ['manager', 'admin', 'owner'] as const;

export const ManagersPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();

  const [searchQuery, setSearchQuery] = useState('');
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [selectedManager, setSelectedManager] = useState<ProjectMember | null>(null);
  const [newMemberUserId, setNewMemberUserId] = useState('');
  const [newMemberRole, setNewMemberRole] = useState<(typeof ROLE_OPTIONS)[number]>('manager');

  const { data: managers = [], isLoading, isError, error } = useProjectManagers(projectId);
  const safeManagers = Array.isArray(managers) ? managers : [];

  const invalidateMembers = async () => {
    await queryClient.invalidateQueries({ queryKey: ['members', projectId] });
  };

  const addMemberMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) {
        throw new Error('Project is not selected');
      }

      const normalizedUserId = newMemberUserId.trim();
      if (!normalizedUserId) {
        throw new Error(newMemberRole === 'manager' ? 'Укажите Telegram chat_id менеджера' : 'Укажите user_id участника');
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
      await invalidateMembers();
      setNewMemberUserId('');
      setNewMemberRole('manager');
      toast.success(newMemberRole === 'manager' ? 'Менеджер добавлен' : 'Участник проекта сохранён');
    },
    onError: (error) => {
      toast.error(getErrorMessage(error));
    },
  });

  const removeMemberMutation = useMutation({
    mutationFn: async (memberUserId: string) => {
      if (!projectId) {
        throw new Error('Project is not selected');
      }
      await membersApi.remove(projectId, memberUserId);
    },
    onSuccess: async () => {
      await invalidateMembers();
      toast.success('Участник проекта удалён');
    },
    onError: (error) => {
      toast.error(getErrorMessage(error));
    },
  });

  const filteredManagers = safeManagers.filter((manager) => {
    if (!searchQuery.trim()) {
      return true;
    }

    const haystack = [
      manager.full_name,
      manager.username,
      manager.email,
      manager.user_id,
      manager.role,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();

    return haystack.includes(searchQuery.toLowerCase());
  });

  const openHistory = (manager: ProjectMember) => {
    setSelectedManager(manager);
    setIsHistoryOpen(true);
  };

  if (isLoading) {
    return <div className="p-8 flex justify-center text-[#6B6B6B]">Загрузка участников проекта...</div>;
  }

  if (isError) {
    return (
      <div className="p-8 text-center text-[#6B6B6B]">
        Не удалось загрузить участников проекта: {getErrorMessage(error)}
      </div>
    );
  }

  return (
    <div className="relative mx-auto max-w-7xl space-y-8 overflow-hidden p-8 animate-in fade-in duration-500">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="mb-2 text-3xl font-bold text-[#1E1E1E]">Команда проекта</h1>
          <p className="text-[#6B6B6B]">
            Список участников проекта с ролями владельца, администратора и менеджера.
          </p>
        </div>
        <div className="flex gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#6B6B6B]" />
            <input
              type="text"
              placeholder="Поиск по участникам..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-64 rounded-lg border border-[#E5E2DA] bg-white py-2 pl-10 pr-4 text-sm transition-all focus:outline-none focus:ring-2 focus:ring-[#B87333]/20"
            />
          </div>
          <input
            type="text"
            placeholder="ID участника"
            value={newMemberUserId}
            onChange={(e) => setNewMemberUserId(e.target.value)}
            className="w-52 rounded-lg border border-[#E5E2DA] bg-white px-3 py-2 text-sm transition-all focus:outline-none focus:ring-2 focus:ring-[#B87333]/20"
          />
          <select
            value={newMemberRole}
            onChange={(e) => setNewMemberRole(e.target.value as (typeof ROLE_OPTIONS)[number])}
            className="rounded-lg border border-[#E5E2DA] bg-white px-3 py-2 text-sm transition-all focus:outline-none focus:ring-2 focus:ring-[#B87333]/20"
          >
            {ROLE_OPTIONS.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
          <Button
            variant="primary"
            className="flex items-center gap-2"
            onClick={() => addMemberMutation.mutate()}
            disabled={addMemberMutation.isPending}
          >
            <Shield className="h-4 w-4" />
            Добавить
          </Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-[#E5E2DA] bg-white shadow-sm">
        <table className="w-full border-collapse text-left">
          <thead className="border-b border-[#E5E2DA] bg-[#FAF9F6]">
            <tr>
              <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-[#6B6B6B]">Участник</th>
              <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-[#6B6B6B]">User ID</th>
              <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-[#6B6B6B]">Роль</th>
              <th className="px-6 py-4 text-right text-xs font-bold uppercase tracking-wider text-[#6B6B6B]">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#F4F1EA]">
            {filteredManagers.map((manager) => (
              <tr key={manager.user_id} className="group transition-colors hover:bg-[#FAF9F6]">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#B87333]/10 text-[#B87333]">
                      <User className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="font-semibold text-[#1E1E1E]">
                        {manager.full_name || manager.username || manager.email || manager.user_id}
                      </div>
                      <div className="text-xs text-[#6B6B6B]">
                        {manager.username ? `@${manager.username}` : manager.email || 'Участник проекта'}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 font-mono text-sm text-[#6B6B6B]">{manager.user_id}</td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-[#10B981]" />
                    <span className="text-sm text-[#1E1E1E]">{manager.role}</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-right">
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => openHistory(manager)}
                      className="rounded-lg p-2 text-[#6B6B6B] transition-colors hover:bg-[#B87333]/10 hover:text-[#B87333]"
                      title="История ответов"
                    >
                      <History className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => removeMemberMutation.mutate(manager.user_id)}
                      disabled={removeMemberMutation.isPending}
                      className="rounded-lg p-2 text-[#6B6B6B] transition-colors hover:bg-red-50 hover:text-red-500 disabled:opacity-50"
                      title="Удалить участника"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {filteredManagers.length === 0 && (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-sm text-[#6B6B6B]">
                  Участники проекта пока не найдены.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {isHistoryOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm transition-opacity"
            onClick={() => setIsHistoryOpen(false)}
          />
          <div className="fixed right-0 top-0 z-50 flex h-full w-[450px] flex-col border-l border-[#E5E2DA] bg-white p-8 shadow-2xl animate-in slide-in-from-right duration-300">
            <div className="mb-8 flex items-center justify-between">
              <h2 className="text-2xl font-bold text-[#1E1E1E]">История ответов</h2>
              <button
                onClick={() => setIsHistoryOpen(false)}
                className="rounded-full p-2 transition-colors hover:bg-gray-100"
              >
                <XCircle className="h-6 w-6 text-[#6B6B6B]" />
              </button>
            </div>

            <div className="mb-8 flex items-center gap-4 rounded-xl border border-[#E5E2DA] bg-[#FAF9F6] p-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#B87333]/10 text-[#B87333]">
                <User className="h-6 w-6" />
              </div>
              <div>
                <div className="font-bold text-[#1E1E1E]">{selectedManager?.full_name || selectedManager?.user_id}</div>
                <div className="text-sm text-[#6B6B6B]">{selectedManager?.username || selectedManager?.email}</div>
              </div>
            </div>

            <div className="flex-1 rounded-xl border border-dashed border-[#E5E2DA] bg-[#FAF9F6] p-6 text-sm text-[#6B6B6B]">
              История ответов пока не подключена к API. Фейковые ответы скрыты, чтобы не вводить менеджера в заблуждение.
            </div>
          </div>
        </>
      )}
    </div>
  );
};
