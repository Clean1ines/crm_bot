import React, { useState } from 'react';
import { api } from '@shared/api/client';
import { useNotification } from '@/shared/lib/notification/useNotifications';

export const BotTokens: React.FC<{ projectId: string }> = ({ projectId }) => {
  const [clientToken, setClientToken] = useState('');
  const [managerToken, setManagerToken] = useState('');
  const { showNotification } = useNotification();

  const handleSetClient = async () => {
    if (!clientToken.trim()) return;
    const { error } = await api.projects.setBotToken(projectId, clientToken);
    if (error) showNotification('Ошибка', 'error');
    else showNotification('Токен клиента сохранён', 'success');
  };

  const handleSetManager = async () => {
    if (!managerToken.trim()) return;
    const { error } = await api.projects.setManagerToken(projectId, managerToken);
    if (error) showNotification('Ошибка', 'error');
    else showNotification('Токен менеджера сохранён', 'success');
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium">Токен клиентского бота</label>
        <input
          type="password"
          value={clientToken}
          onChange={e => setClientToken(e.target.value)}
          className="mt-1 block w-full border rounded-md p-2"
          placeholder="Введите токен"
        />
        <button onClick={handleSetClient} className="mt-2 bg-blue-600 text-white px-3 py-1 rounded">Сохранить</button>
      </div>
      <div>
        <label className="block text-sm font-medium">Токен менеджерского бота</label>
        <input
          type="password"
          value={managerToken}
          onChange={e => setManagerToken(e.target.value)}
          className="mt-1 block w-full border rounded-md p-2"
          placeholder="Введите токен"
        />
        <button onClick={handleSetManager} className="mt-2 bg-blue-600 text-white px-3 py-1 rounded">Сохранить</button>
      </div>
    </div>
  );
};