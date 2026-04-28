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
    if (error) showNotification('Ошибка', 'error');
    else showNotification('Токен клиента сохранён', 'success');
  };

  const handleSetManager = async () => {
    if (!managerToken.trim()) return;
    const { error } = await projectsApi.setManagerToken(projectId, managerToken);
    if (error) showNotification('Ошибка', 'error');
    else showNotification('Токен менеджера сохранён', 'success');
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-[var(--text-primary)]">Токен клиентского бота</label>
        <input
          type="password"
          value={clientToken}
          onChange={e => setClientToken(e.target.value)}
          className="mt-1 min-h-10 block w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          placeholder="Введите токен"
        />
        <button onClick={handleSetClient} className="mt-2 min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)]">Сохранить</button>
      </div>
      <div>
        <label className="block text-sm font-medium text-[var(--text-primary)]">Токен менеджерского бота</label>
        <input
          type="password"
          value={managerToken}
          onChange={e => setManagerToken(e.target.value)}
          className="mt-1 min-h-10 block w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          placeholder="Введите токен"
        />
        <button onClick={handleSetManager} className="mt-2 min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)]">Сохранить</button>
      </div>
    </div>
  );
};