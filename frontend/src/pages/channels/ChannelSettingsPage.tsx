import React, { useMemo, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProjects } from '@entities/project/api/useProjects';
import { useAppStore } from '@app/store';
import { useProjectStore } from '@entities/project';

export const ChannelSettingsPage: React.FC = () => {
  const navigate = useNavigate();
  const {
    projects,
    isLoading: projectsLoading,
    updateBotToken,
    updateManagerBotToken,
    isUpdatingBotToken,
    isUpdatingManagerBotToken,
    openCreateModal,
    error: projectsError,
  } = useProjects();
  const { selectedProjectId, setSelectedProjectId } = useAppStore();
  const { setCurrentProjectId } = useProjectStore();

  const [clientToken, setClientToken] = useState('');
  const [managerToken, setManagerToken] = useState('');
  const [showClientToken, setShowClientToken] = useState(false);
  const [showManagerToken, setShowManagerToken] = useState(false);

  const safeProjects = useMemo(() => (Array.isArray(projects) ? projects : []), [projects]);
  const currentProject = safeProjects.find(p => p.id === selectedProjectId);

  // Если проектов нет, открыть модалку создания
  useEffect(() => {
    if (!projectsLoading && safeProjects.length === 0) {
      openCreateModal();
    }
  }, [projectsLoading, safeProjects.length, openCreateModal]);

  // Если выбранный проект null, но проекты есть, выбрать первый
  useEffect(() => {
    if (!projectsLoading && safeProjects.length > 0 && !selectedProjectId) {
      const firstProject = safeProjects[0];
      if (!firstProject) return;
      setSelectedProjectId(firstProject.id);
      setCurrentProjectId(firstProject.id);
      navigate(`/projects/${firstProject.id}/channels`);
    }
  }, [projectsLoading, safeProjects, selectedProjectId, setSelectedProjectId, setCurrentProjectId, navigate]);

  const handleSaveClientToken = async () => {
    if (!selectedProjectId) {
      alert('Сначала выберите проект');
      return;
    }
    if (!clientToken.trim()) {
      alert('Введите токен бота');
      return;
    }
    try {
      await updateBotToken({ projectId: selectedProjectId, token: clientToken.trim() });
      setClientToken('');
      alert('Клиентский бот подключён');
    } catch (err) {
      console.error('Ошибка сохранения токена:', err);
      alert('Не удалось подключить бота');
    }
  };

  const handleRevokeClientToken = async () => {
    if (!selectedProjectId) return;
    if (!window.confirm('Вы уверены, что хотите открепить клиентского бота?')) return;
    try {
      await updateBotToken({ projectId: selectedProjectId, token: null });
      alert('Клиентский бот откреплён');
    } catch (err) {
      console.error('Ошибка открепления бота:', err);
      alert('Не удалось открепить бота');
    }
  };

  const handleSaveManagerToken = async () => {
    if (!selectedProjectId) {
      alert('Сначала выберите проект');
      return;
    }
    if (!managerToken.trim()) {
      alert('Введите токен бота');
      return;
    }
    try {
      await updateManagerBotToken({ projectId: selectedProjectId, token: managerToken.trim() });
      setManagerToken('');
      alert('Менеджерский бот подключён');
    } catch (err) {
      console.error('Ошибка сохранения токена:', err);
      alert('Не удалось подключить бота');
    }
  };

  const handleRevokeManagerToken = async () => {
    if (!selectedProjectId) return;
    if (!window.confirm('Вы уверены, что хотите открепить менеджерского бота?')) return;
    try {
      await updateManagerBotToken({ projectId: selectedProjectId, token: null });
      alert('Менеджерский бот откреплён');
    } catch (err) {
      console.error('Ошибка открепления бота:', err);
      alert('Не удалось открепить бота');
    }
  };

  if (projectsLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-[var(--text-muted)]">Загрузка проектов...</div>
      </div>
    );
  }

  if (projectsError) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          Не удалось загрузить проекты.
        </div>
      </div>
    );
  }

  if (!currentProject && safeProjects.length === 0) {
    return (
      <div className="p-8 text-center">
        <p>Нет проектов. Создайте первый проект через боковое меню.</p>
      </div>
    );
  }

  if (!currentProject) {
    return (
      <div className="p-8">
        <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 p-4 rounded-lg">
          Проект не выбран. Выберите проект в боковом меню.
        </div>
      </div>
    );
  }

  const hasClient = !!currentProject.client_bot_username;
  const hasManager = !!currentProject.manager_bot_username;

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8">
      <div className="mb-8">
        <h1 className="text-3xl font-semibold text-[var(--text-primary)]">Каналы</h1>
        <p className="text-[var(--text-muted)] mt-2">
          Настройте Telegram ботов для работы с клиентами и менеджерами
        </p>
      </div>

      {/* Клиентский бот */}
      <div className="bg-[var(--surface-secondary)] rounded-xl border border-[var(--border-subtle)] p-6 shadow-sm">
        <h2 className="text-xl font-medium text-[var(--text-primary)] mb-4">Клиентский бот</h2>
        <p className="text-sm text-[var(--text-muted)] mb-4">
          Бот, который будет общаться с клиентами.
        </p>

        {hasClient ? (
          <div className="space-y-4">
            <div className="p-3 bg-[var(--accent-success-bg)] border border-[var(--accent-success-border)] rounded-lg text-sm text-[var(--accent-success-text)]">
              <strong>✓ Бот подключён</strong> – @{currentProject.client_bot_username}
            </div>
            <button
              onClick={handleRevokeClientToken}
              disabled={isUpdatingBotToken}
              className="px-4 py-2 bg-[var(--accent-danger)] text-white rounded-lg hover:bg-[var(--accent-danger)]/80 transition-colors disabled:opacity-50"
            >
              {isUpdatingBotToken ? 'Открепление...' : 'Открепить бота'}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
                Токен бота
              </label>
              <div className="flex gap-2">
                <input
                  type={showClientToken ? 'text' : 'password'}
                  value={clientToken}
                  onChange={(e) => setClientToken(e.target.value)}
                  placeholder="1234567890:ABCdefGHIJklmNOPqrStuVWXyz"
                  className="flex-1 px-3 py-2 bg-white border border-[var(--border-subtle)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)] focus:border-transparent"
                />
                <button
                  onClick={() => setShowClientToken(!showClientToken)}
                  className="px-3 py-2 bg-[var(--bg-tertiary)] text-[var(--text-secondary)] rounded-lg hover:bg-[var(--border-subtle)] transition-colors"
                >
                  {showClientToken ? 'Скрыть' : 'Показать'}
                </button>
              </div>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                Получите токен у <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer" className="text-[var(--accent-primary)] hover:underline">@BotFather</a> в Telegram
              </p>
            </div>
            <button
              onClick={handleSaveClientToken}
              disabled={isUpdatingBotToken || !clientToken.trim()}
              className="px-4 py-2 bg-[var(--accent-primary)] text-white rounded-lg hover:bg-[var(--accent-primary)]/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isUpdatingBotToken ? 'Подключение...' : 'Подключить бота'}
            </button>
          </div>
        )}
      </div>

      {/* Менеджерский бот */}
      <div className="bg-[var(--surface-secondary)] rounded-xl border border-[var(--border-subtle)] p-6 shadow-sm">
        <h2 className="text-xl font-medium text-[var(--text-primary)] mb-4">Менеджерский бот</h2>
        <p className="text-sm text-[var(--text-muted)] mb-4">
          Бот, который будет уведомлять менеджеров об эскалациях.
        </p>

        {hasManager ? (
          <div className="space-y-4">
            <div className="p-3 bg-[var(--accent-success-bg)] border border-[var(--accent-success-border)] rounded-lg text-sm text-[var(--accent-success-text)]">
              <strong>✓ Бот подключён</strong> – @{currentProject.manager_bot_username}
            </div>
            <button
              onClick={handleRevokeManagerToken}
              disabled={isUpdatingManagerBotToken}
              className="px-4 py-2 bg-[var(--accent-danger)] text-white rounded-lg hover:bg-[var(--accent-danger)]/80 transition-colors disabled:opacity-50"
            >
              {isUpdatingManagerBotToken ? 'Открепление...' : 'Открепить бота'}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
                Токен бота
              </label>
              <div className="flex gap-2">
                <input
                  type={showManagerToken ? 'text' : 'password'}
                  value={managerToken}
                  onChange={(e) => setManagerToken(e.target.value)}
                  placeholder="1234567890:ABCdefGHIJklmNOPqrStuVWXyz"
                  className="flex-1 px-3 py-2 bg-white border border-[var(--border-subtle)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)] focus:border-transparent"
                />
                <button
                  onClick={() => setShowManagerToken(!showManagerToken)}
                  className="px-3 py-2 bg-[var(--bg-tertiary)] text-[var(--text-secondary)] rounded-lg hover:bg-[var(--border-subtle)] transition-colors"
                >
                  {showManagerToken ? 'Скрыть' : 'Показать'}
                </button>
              </div>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                Получите токен у <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer" className="text-[var(--accent-primary)] hover:underline">@BotFather</a> в Telegram
              </p>
            </div>
            <button
              onClick={handleSaveManagerToken}
              disabled={isUpdatingManagerBotToken || !managerToken.trim()}
              className="px-4 py-2 bg-[var(--accent-primary)] text-white rounded-lg hover:bg-[var(--accent-primary)]/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isUpdatingManagerBotToken ? 'Подключение...' : 'Подключить бота'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
