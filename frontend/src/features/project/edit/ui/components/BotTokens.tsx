import { t } from '../../../../../shared/i18n';
import React, { useState } from 'react';
import { projectsApi } from '@shared/api/modules/projects';
import { useNotification } from '@/shared/lib/notification/useNotifications';

export const BotTokens: React.FC<{ projectId: string }> = ({ projectId }) => {
  const [clientToken, setClientToken] = useState('');
  const [managerToken, setManagerToken] = useState('');
  const { showNotification } = useNotification();

  const handleSetClient = async () => {
    if (!clientToken.trim()) return;
    const { error } = await projectsApi.setBotToken(projectId, clientToken);
    if (error) showNotification(t('botTokens.error.generic'), 'error');
    else showNotification(t('botTokens.client.saved'), 'success');
  };

  const handleSetManager = async () => {
    if (!managerToken.trim()) return;
    const { error } = await projectsApi.setManagerToken(projectId, managerToken);
    if (error) showNotification(t('botTokens.error.generic'), 'error');
    else showNotification(t('botTokens.manager.saved'), 'success');
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-[var(--text-primary)]">{t('botTokens.client.label')}</label>
        <input
          type="password"
          value={clientToken}
          onChange={e => setClientToken(e.target.value)}
          className="mt-1 min-h-10 block w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          placeholder={t('botTokens.token.placeholder')}
        />
        <button onClick={handleSetClient} className="mt-2 min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)]">{t('botTokens.save')}</button>
      </div>
      <div>
        <label className="block text-sm font-medium text-[var(--text-primary)]">{t('botTokens.manager.label')}</label>
        <input
          type="password"
          value={managerToken}
          onChange={e => setManagerToken(e.target.value)}
          className="mt-1 min-h-10 block w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          placeholder={t('botTokens.token.placeholder')}
        />
        <button onClick={handleSetManager} className="mt-2 min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)]">{t('botTokens.save')}</button>
      </div>
    </div>
  );
};