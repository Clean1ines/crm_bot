import { t } from '@shared/i18n';
import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { useNotification } from '@/shared/lib/notification/useNotifications';
import { useProjectManagers } from '@entities/project/api/useCrmData';
import { getErrorMessage } from '@shared/api/core/errors';
import { getDisplayName } from '@shared/lib/displayNames';
import { roleLabel } from '@shared/lib/uiLabels';
import { membersApi } from '@shared/api/modules/members';
import { projectsApi } from '@shared/api/modules/projects';
import { Button } from '@shared/ui';

const ROLE_OPTIONS = ['manager', 'admin'] as const;

export const ManagersList: React.FC<{ projectId: string }> = ({ projectId }) => {
  const queryClient = useQueryClient();
  const { showNotification } = useNotification();
  const [newMemberUserId, setNewMemberUserId] = useState('');
  const [newMemberRole, setNewMemberRole] = useState<(typeof ROLE_OPTIONS)[number]>('manager');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteFirstName, setInviteFirstName] = useState('');
  const [inviteLastName, setInviteLastName] = useState('');
  const [inviteRole, setInviteRole] = useState<(typeof ROLE_OPTIONS)[number]>('manager');
  const [lastInviteLink, setLastInviteLink] = useState('');

  const { data: managers = [], isLoading } = useProjectManagers(projectId);

  const invalidateManagers = async () => {
    await queryClient.invalidateQueries({ queryKey: ['members', projectId] });
  };

  const addMutation = useMutation({
    mutationFn: async () => {
      const normalizedUserId = newMemberUserId.trim();
      if (!normalizedUserId) {
        throw new Error(newMemberRole === 'manager' ? t('managers.telegramIdRequired') : t('managers.memberIdRequired'));
      }

      if (newMemberRole === 'manager') {
        const chatId = Number(normalizedUserId);
        if (!Number.isInteger(chatId)) {
          throw new Error(t('managers.telegramIdMustBeNumber'));
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
      showNotification(newMemberRole === 'manager' ? t('managers.managerAdded') : t('managers.memberSaved'), 'success');
    },
    onError: (error) => showNotification(getErrorMessage(error), 'error'),
  });

  const inviteMutation = useMutation({
    mutationFn: async () => {
      const normalizedEmail = inviteEmail.trim();
      if (!normalizedEmail) {
        throw new Error(t('managers.emailRequired'));
      }

      const result = await membersApi.createInvitation(projectId, {
        email: normalizedEmail,
        first_name: inviteFirstName.trim() || undefined,
        last_name: inviteLastName.trim() || undefined,
        role: inviteRole,
      });

      if (!result.data) {
        throw new Error(t('managers.inviteCreateFailed'));
      }

      return result.data;
    },
    onSuccess: async (result) => {
      await invalidateManagers();
      setInviteEmail('');
      setInviteFirstName('');
      setInviteLastName('');
      setInviteRole('manager');
      setLastInviteLink(result.invite_link ?? '');
      showNotification(
        result.invite_link
          ? t('managers.inviteCreatedLink')
          : t('managers.inviteSentEmail'),
        'success',
      );
    },
    onError: (error) => showNotification(getErrorMessage(error), 'error'),
  });

  const removeMutation = useMutation({
    mutationFn: async (memberUserId: string) => {
      await membersApi.remove(projectId, memberUserId);
    },
    onSuccess: async () => {
      await invalidateManagers();
      showNotification(t('managers.memberDeleted'), 'success');
    },
    onError: (error) => showNotification(getErrorMessage(error), 'error'),
  });

  if (isLoading) {
    return <div className="text-sm text-[var(--text-muted)]">{t('common.states.loading')}</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-[var(--text-primary)]">{t('managers.title')}</h3>
        <ul className="mt-3 space-y-2">
          {managers.map((manager) => (
            <li key={manager.user_id} className="flex items-center justify-between rounded-lg bg-[var(--surface-secondary)] px-3 py-2 text-sm">
              <span>
                {getDisplayName(manager, t('managers.fallback.manager'))}
                <span className="ml-2 inline-flex min-h-6 items-center rounded-full bg-[var(--accent-muted)] px-2 text-xs font-medium text-[var(--accent-primary)]">({roleLabel(manager.role)})</span>
              </span>
              <button
                onClick={() => removeMutation.mutate(manager.user_id)}
                className="text-sm font-medium text-[var(--accent-danger-text)] hover:underline"
              >
                {t('managers.delete')}
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
          placeholder={newMemberRole === 'manager' ? t('managers.telegramIdPlaceholder') : t('managers.memberIdPlaceholder')}
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
          {t('managers.add')}
        </Button>
      </div>
      <div className="rounded-2xl bg-[var(--surface-secondary)] p-4">
        <div className="mb-3">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">{t('managers.inviteEmail.title')}</h4>
          <p className="text-xs text-[var(--text-muted)]">
            {t('managers.inviteEmail.description')}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            type="email"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            placeholder="manager@example.com"
            className="min-h-10 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          />
          <input
            type="text"
            value={inviteFirstName}
            onChange={(e) => setInviteFirstName(e.target.value)}
            placeholder={t('managers.firstNamePlaceholder')}
            className="min-h-10 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          />
          <input
            type="text"
            value={inviteLastName}
            onChange={(e) => setInviteLastName(e.target.value)}
            placeholder={t('managers.lastNamePlaceholder')}
            className="min-h-10 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          />
          <select
            value={inviteRole}
            onChange={(e) => setInviteRole(e.target.value as (typeof ROLE_OPTIONS)[number])}
            className="min-h-10 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          >
            {ROLE_OPTIONS.map((role) => (
              <option key={role} value={role}>
                {roleLabel(role)}
              </option>
            ))}
          </select>
          <Button
            variant="primary"
            onClick={() => inviteMutation.mutate()}
            disabled={inviteMutation.isPending}
          >
            {t('managers.inviteByEmail')}
          </Button>
        </div>
        {lastInviteLink ? (
          <input
            readOnly
            value={lastInviteLink}
            className="mt-3 min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-xs text-[var(--text-secondary)] shadow-[var(--shadow-sm)]"
          />
        ) : null}
      </div>
    </div>
  );
};
