import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProjects } from '@entities/project/api/useProjects';
import { useAppStore } from '@app/store';
import { useProjectStore } from '@entities/project';
import { Project } from '@entities/project';

interface ProjectWithBotToken extends Project {
  bot_token?: string;
}

/**
 * Страница настройки каналов (Telegram бота).
 * Позволяет подключить бота к проекту, указав токен.
 * Автоматически открывает модальное окно создания проекта, если проектов нет.
 * Автоматически выбирает первый проект, если ни один не выбран.
 */
export const ChannelSettingsPage: React.FC = () => {
  const navigate = useNavigate();
  const {
    projects,
    isLoading: projectsLoading,
    updateBotToken,
    isUpdatingBotToken,
    openCreateModal,
  } = useProjects();
  const { selectedProjectId, setSelectedProjectId } = useAppStore();
  const { setCurrentProjectId } = useProjectStore();

  const [token, setToken] = useState('');
  const [showToken, setShowToken] = useState(false);

  const currentProject = projects.find(p => p.id === selectedProjectId) as ProjectWithBotToken | undefined;

  // Если проектов нет, открыть модалку создания
  useEffect(() => {
    if (!projectsLoading && projects.length === 0) {
      openCreateModal();
    }
  }, [projectsLoading, projects.length, openCreateModal]);

  // Если выбранный проект null, но проекты есть, выбрать первый
  useEffect(() => {
    if (!projectsLoading && projects.length > 0 && !selectedProjectId) {
      const firstProject = projects[0];
      setSelectedProjectId(firstProject.id);
      setCurrentProjectId(firstProject.id);
      navigate(`/projects/${firstProject.id}/channels`);
    }
  }, [projectsLoading, projects, selectedProjectId, setSelectedProjectId, setCurrentProjectId, navigate]);

  const handleSaveToken = async () => {
    if (!selectedProjectId) {
      alert('Сначала выберите проект');
      return;
    }
    if (!token.trim()) {
      alert('Введите токен бота');
      return;
    }
    try {
      await updateBotToken({ projectId: selectedProjectId, token: token.trim() });
      setToken('');
      alert('Токен успешно сохранён');
    } catch (err) {
      console.error('Ошибка сохранения токена:', err);
      alert('Не удалось сохранить токен');
    }
  };

  const handleRevokeToken = async () => {
    if (!selectedProjectId) return;
    if (!window.confirm('Вы уверены, что хотите открепить бота? Бот перестанет отвечать.')) return;
    try {
      await updateBotToken({ projectId: selectedProjectId, token: null });
      alert('Бот откреплён');
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

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-semibold text-[var(--text-primary)]">Каналы</h1>
        <p className="text-[var(--text-muted)] mt-2">
          Настройте Telegram бота для работы с клиентами
        </p>
      </div>

      {!currentProject && projects.length > 0 ? (
        <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 p-4 rounded-lg">
          Проект не выбран. Выберите проект в боковом меню.
        </div>
      ) : currentProject ? (
        <div className="bg-[var(--surface-secondary)] rounded-xl border border-[var(--border-subtle)] p-6">
          <div className="flex justify-between items-start mb-6">
            <div>
              <h2 className="text-xl font-medium text-[var(--text-primary)]">Telegram бот</h2>
              <p className="text-sm text-[var(--text-muted)] mt-1">
                Проект: <strong>{currentProject.name}</strong>
              </p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
                Токен бота
              </label>
              <div className="flex gap-2">
                <input
                  type={showToken ? 'text' : 'password'}
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="1234567890:ABCdefGHIJklmNOPqrStuVWXyz"
                  className="flex-1 px-3 py-2 bg-white border border-[var(--border-subtle)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)] focus:border-transparent"
                />
                <button
                  onClick={() => setShowToken(!showToken)}
                  className="px-3 py-2 bg-[var(--bg-tertiary)] text-[var(--text-secondary)] rounded-lg hover:bg-[var(--border-subtle)] transition-colors"
                >
                  {showToken ? 'Скрыть' : 'Показать'}
                </button>
              </div>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                Получите токен у <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer" className="text-[var(--accent-primary)] hover:underline">@BotFather</a> в Telegram
              </p>
            </div>

            <div className="flex gap-3">
              <button
                onClick={handleSaveToken}
                disabled={isUpdatingBotToken || !token.trim()}
                className="px-4 py-2 bg-[var(--accent-primary)] text-white rounded-lg hover:bg-[var(--accent-primary-dark)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isUpdatingBotToken ? 'Сохранение...' : 'Сохранить токен'}
              </button>
              {currentProject.bot_token && (
                <button
                  onClick={handleRevokeToken}
                  disabled={isUpdatingBotToken}
                  className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors disabled:opacity-50"
                >
                  Открепить бота
                </button>
              )}
            </div>

            {currentProject.bot_token && (
              <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
                <strong>✓ Бот подключён</strong> – текущий токен скрыт из соображений безопасности.
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
};
