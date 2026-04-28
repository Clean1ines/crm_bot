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
    return <div className="flex justify-center p-4 text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">Загрузка участников проекта...</div>;
  }

  if (isError) {
    return (
      <div className="p-4 text-center text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">
        Не удалось загрузить участников проекта: {getErrorMessage(error)}
      </div>
    );
  }

  return (
    <div className="relative mx-auto max-w-7xl space-y-6 overflow-hidden p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="mb-2 text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">Команда проекта</h1>
          <p className="text-[var(--text-muted)]">
            Список участников проекта с ролями владельца, администратора и менеджера.
          </p>
        </div>
        <div className="flex w-full flex-col gap-3 sm:flex-row sm:flex-wrap lg:w-auto">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
            <input
              type="text"
              placeholder="Поиск по участникам..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] py-2 pl-10 pr-4 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-all focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 sm:w-64"
            />
          </div>
          <input
            type="text"
            placeholder="ID участника"
            value={newMemberUserId}
            onChange={(e) => setNewMemberUserId(e.target.value)}
            className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-all focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 sm:w-52"
          />
          <select
            value={newMemberRole}
            onChange={(e) => setNewMemberRole(e.target.value as (typeof ROLE_OPTIONS)[number])}
            className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-all focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 sm:w-auto"
          >
            {ROLE_OPTIONS.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
          <Button
            variant="primary"
            className="flex w-full items-center gap-2 sm:w-auto"
            onClick={() => addMemberMutation.mutate()}
            disabled={addMemberMutation.isPending}
          >
            <Shield className="h-4 w-4" />
            Добавить
          </Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl bg-[var(--surface-card)] shadow-sm">
        <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-left">
          <thead className="shadow-[0_1px_0_var(--divider-soft)] bg-[var(--surface-secondary)]">
            <tr>
              <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)] lg:px-5">Участник</th>
              <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)] lg:px-5">User ID</th>
              <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)] lg:px-5">Роль</th>
              <th className="px-4 py-3 text-right text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)] lg:px-5">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--surface-secondary)]">
            {filteredManagers.map((manager) => (
              <tr key={manager.user_id} className="group transition-colors hover:bg-[var(--surface-secondary)]">
                <td className="px-4 py-3 lg:px-5">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
                      <User className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="font-medium text-[var(--text-primary)]">
                        {manager.full_name || manager.username || manager.email || manager.user_id}
                      </div>
                      <div className="text-xs text-[var(--text-muted)]">
                        {manager.username ? `@${manager.username}` : manager.email || 'Участник проекта'}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-[var(--text-muted)] lg:px-5">{manager.user_id}</td>
                <td className="px-4 py-3 lg:px-5">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-[var(--accent-success)]" />
                    <span className="text-sm text-[var(--text-primary)]">{manager.role}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-right lg:px-5">
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => openHistory(manager)}
                      className="rounded-lg p-2 text-[var(--text-muted)] transition-colors hover:bg-[var(--accent-primary)]/10 hover:text-[var(--accent-primary)]"
                      title="История ответов"
                    >
                      <History className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => removeMemberMutation.mutate(manager.user_id)}
                      disabled={removeMemberMutation.isPending}
                      className="rounded-lg p-2 text-[var(--text-muted)] transition-colors hover:bg-[var(--accent-danger-bg)] hover:text-[var(--accent-danger-text)] disabled:opacity-50"
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
                <td colSpan={4} className="px-4 py-8 text-center text-sm text-[var(--text-muted)] lg:px-5">
                  Участники проекта пока не найдены.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>

        <div className="grid gap-3 p-3 md:hidden">
          {filteredManagers.length === 0 ? (
            <div className="rounded-2xl bg-[var(--surface-secondary)] px-4 py-10 text-center text-sm text-[var(--text-muted)]">
              Участники проекта пока не найдены.
            </div>
          ) : (
            filteredManagers.map((manager) => (
              <article
                key={manager.user_id}
                className="rounded-2xl bg-[var(--surface-secondary)] p-4"
              >
                <div className="flex items-start gap-3">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
                    <User className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h2 className="truncate font-semibold text-[var(--text-primary)]">
                      {manager.full_name || manager.username || manager.email || manager.user_id}
                    </h2>
                    <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]">
                      {manager.username ? `@${manager.username}` : manager.email || 'Участник проекта'}
                    </p>
                  </div>
                </div>

                <div className="mt-4 grid gap-2 text-xs">
                  <div className="rounded-xl bg-[var(--surface-card)] p-3">
                    <div className="text-[var(--text-muted)]">User ID</div>
                    <div className="mt-1 break-all font-mono font-semibold text-[var(--text-primary)]">
                      {manager.user_id}
                    </div>
                  </div>
                  <div className="rounded-xl bg-[var(--surface-card)] p-3">
                    <div className="text-[var(--text-muted)]">Роль</div>
                    <div className="mt-1 flex items-center gap-2 font-semibold text-[var(--text-primary)]">
                      <CheckCircle2 className="h-4 w-4 text-[var(--accent-success)]" />
                      {manager.role}
                    </div>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2">
                  <button
                    onClick={() => openHistory(manager)}
                    className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--surface-card)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--accent-primary)]/10 hover:text-[var(--accent-primary)]"
                    title="История ответов"
                  >
                    <History className="h-4 w-4" />
                    История
                  </button>
                  <button
                    onClick={() => removeMemberMutation.mutate(manager.user_id)}
                    disabled={removeMemberMutation.isPending}
                    className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--surface-card)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--accent-danger-bg)] hover:text-[var(--accent-danger-text)] disabled:opacity-50"
                    title="Удалить участника"
                  >
                    <Trash2 className="h-4 w-4" />
                    Удалить
                  </button>
                </div>
              </article>
            ))
          )}
        </div>
      </div>

      {isHistoryOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm transition-opacity"
            onClick={() => setIsHistoryOpen(false)}
          />
          <div className="fixed right-0 top-0 z-50 flex h-full w-full flex-col bg-[var(--surface-card)] p-4 shadow-[-1px_0_0_var(--divider-soft)] animate-in slide-in-from-right duration-300 sm:w-[450px] sm:p-6">
            <div className="mb-6 flex items-center justify-between sm:mb-8">
              <h2 className="text-xl font-semibold leading-tight text-[var(--text-primary)]">История ответов</h2>
              <button
                onClick={() => setIsHistoryOpen(false)}
                className="rounded-full p-2 transition-colors hover:bg-[var(--surface-secondary)]"
              >
                <XCircle className="h-6 w-6 text-[var(--text-muted)]" />
              </button>
            </div>

            <div className="mb-8 flex items-center gap-4 rounded-xl bg-[var(--surface-secondary)] p-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
                <User className="h-6 w-6" />
              </div>
              <div>
                <div className="font-semibold text-[var(--text-primary)]">{selectedManager?.full_name || selectedManager?.user_id}</div>
                <div className="text-sm text-[var(--text-muted)]">{selectedManager?.username || selectedManager?.email}</div>
              </div>
            </div>

            <div className="flex-1 rounded-xl bg-[var(--surface-secondary)] p-6 text-sm text-[var(--text-muted)]">
              История ответов пока не подключена к API. Фейковые ответы скрыты, чтобы не вводить менеджера в заблуждение.
            </div>
          </div>
        </>
      )}
    </div>
  );
};
