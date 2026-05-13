import React, { useMemo, useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { useNavigate, useParams } from 'react-router-dom';
import { useProjects } from '@entities/project/api/useProjects';
import { useProjectStore } from '@entities/project';
import { getErrorMessage } from '@shared/api/core/errors';
import { BaseModal } from '@shared/ui';

export const ChannelSettingsPage: React.FC = () => {
  const navigate = useNavigate();
  const { projectId: urlProjectId } = useParams<{ projectId: string }>();
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
  const { selectedProjectId: storedSelectedProjectId, setSelectedProjectId } = useProjectStore();

  const selectedProjectId = urlProjectId || storedSelectedProjectId;

  const [clientToken, setClientToken] = useState('');
  const [managerToken, setManagerToken] = useState('');
  const [showClientToken, setShowClientToken] = useState(false);
  const [showManagerToken, setShowManagerToken] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<'client' | 'manager' | null>(null);

  const safeProjects = useMemo(() => (Array.isArray(projects) ? projects : []), [projects]);
  const currentProject = safeProjects.find(p => p.id === selectedProjectId);

  useEffect(() => {
    if (urlProjectId) {
      setSelectedProjectId(urlProjectId);
    }
  }, [urlProjectId, setSelectedProjectId]);

  useEffect(() => {
    if (!projectsLoading && safeProjects.length === 0) {
      openCreateModal();
    }
  }, [projectsLoading, safeProjects.length, openCreateModal]);

  useEffect(() => {
    if (!projectsLoading && safeProjects.length > 0 && !selectedProjectId) {
      const firstProject = safeProjects[0];
      if (!firstProject) return;
      setSelectedProjectId(firstProject.id);
      navigate(`/projects/${firstProject.id}/channels`);
    }
  }, [projectsLoading, safeProjects, selectedProjectId, setSelectedProjectId, navigate]);

  const closeRevokeModal = () => setRevokeTarget(null);

  const handleSaveClientToken = async () => {
    if (!selectedProjectId) {
      toast.error('Сначала выберите проект');
      return;
    }
    if (!clientToken.trim()) {
      toast.error('Введите токен клиентского бота');
      return;
    }
    try {
      await updateBotToken({ projectId: selectedProjectId, token: clientToken.trim() });
      setClientToken('');
      toast.success('Клиентский бот подключён');
    } catch (err) {
      console.error('Ошибка сохранения токена:', err);
      toast.error(getErrorMessage(err, 'Не удалось подключить клиентского бота. Проверьте токен и попробуйте снова.'));
    }
  };

  const handleRevokeClientToken = () => {
    if (!selectedProjectId) {
      toast.error('Сначала выберите проект');
      return;
    }
    setRevokeTarget('client');
  };

  const handleSaveManagerToken = async () => {
    if (!selectedProjectId) {
      toast.error('Сначала выберите проект');
      return;
    }
    if (!managerToken.trim()) {
      toast.error('Введите токен менеджерского бота');
      return;
    }
    try {
      await updateManagerBotToken({ projectId: selectedProjectId, token: managerToken.trim() });
      setManagerToken('');
      toast.success('Менеджерский бот подключён');
    } catch (err) {
      console.error('Ошибка сохранения токена:', err);
      toast.error(getErrorMessage(err, 'Не удалось подключить менеджерского бота. Проверьте токен и попробуйте снова.'));
    }
  };

  const handleRevokeManagerToken = () => {
    if (!selectedProjectId) {
      toast.error('Сначала выберите проект');
      return;
    }
    setRevokeTarget('manager');
  };

  const handleConfirmRevoke = async () => {
    if (!selectedProjectId || revokeTarget === null) {
      closeRevokeModal();
      return;
    }

    try {
      if (revokeTarget === 'client') {
        await updateBotToken({ projectId: selectedProjectId, token: null });
        toast.success('Клиентский бот откреплён');
      } else {
        await updateManagerBotToken({ projectId: selectedProjectId, token: null });
        toast.success('Менеджерский бот откреплён');
      }
      closeRevokeModal();
    } catch (err) {
      console.error('Ошибка открепления бота:', err);
      const fallback = revokeTarget === 'client'
        ? 'Не удалось открепить клиентского бота. Попробуйте ещё раз.'
        : 'Не удалось открепить менеджерского бота. Попробуйте ещё раз.';
      toast.error(getErrorMessage(err, fallback));
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
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="rounded-lg bg-[var(--accent-danger-bg)] p-4 text-[var(--accent-danger-text)] shadow-[var(--shadow-sm)]">
          Не удалось загрузить проекты.
        </div>
      </div>
    );
  }

  if (!currentProject && safeProjects.length === 0) {
    return (
      <div className="p-4 text-center sm:p-6 lg:p-8">
        <p>Нет проектов. Создайте первый проект через боковое меню.</p>
      </div>
    );
  }

  if (!currentProject) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="rounded-lg bg-[var(--accent-warning-bg)] p-4 text-[var(--accent-warning)] shadow-[var(--shadow-sm)]">
          Проект не выбран. Выберите проект в боковом меню.
        </div>
      </div>
    );
  }

  const hasClient = !!currentProject.client_bot_username;
  const hasManager = !!currentProject.manager_bot_username;
  const isRevokingBotToken = revokeTarget === 'client'
    ? isUpdatingBotToken
    : revokeTarget === 'manager'
      ? isUpdatingManagerBotToken
      : false;
  const revokeBotLabel = revokeTarget === 'client' ? 'клиентского бота' : 'менеджерского бота';

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">Каналы</h1>
        <p className="text-[var(--text-muted)] mt-2">
          Настройте Telegram ботов для работы с клиентами и менеджерами
        </p>
      </div>

      <div className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <h2 className="mb-3 text-lg font-semibold leading-tight text-[var(--text-primary)]">Клиентский бот</h2>
        <p className="text-sm text-[var(--text-muted)] mb-4">
          Бот, который будет общаться с клиентами.
        </p>

        {hasClient ? (
          <div className="space-y-4">
            <div className="rounded-lg bg-[var(--accent-success-bg)] p-3 text-sm text-[var(--accent-success-text)] shadow-[var(--shadow-sm)]">
              <strong>✓ Бот подключён</strong> – @{currentProject.client_bot_username}
            </div>
            <button
              onClick={handleRevokeClientToken}
              disabled={isUpdatingBotToken}
              className="min-h-10 rounded-lg bg-[var(--accent-danger)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-danger-text)] disabled:opacity-50"
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
                  className="min-h-10 flex-1 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
                />
                <button
                  onClick={() => setShowClientToken(!showClientToken)}
                  className="min-h-10 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-secondary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--control-bg-hover)]"
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
              className="min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isUpdatingBotToken ? 'Подключение...' : 'Подключить бота'}
            </button>
          </div>
        )}
      </div>

      <div className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <h2 className="mb-3 text-lg font-semibold leading-tight text-[var(--text-primary)]">Менеджерский бот</h2>
        <p className="text-sm text-[var(--text-muted)] mb-4">
          Бот, который будет уведомлять менеджеров об эскалациях.
        </p>

        {hasManager ? (
          <div className="space-y-4">
            <div className="rounded-lg bg-[var(--accent-success-bg)] p-3 text-sm text-[var(--accent-success-text)] shadow-[var(--shadow-sm)]">
              <strong>✓ Бот подключён</strong> – @{currentProject.manager_bot_username}
            </div>
            <button
              onClick={handleRevokeManagerToken}
              disabled={isUpdatingManagerBotToken}
              className="min-h-10 rounded-lg bg-[var(--accent-danger)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-danger-text)] disabled:opacity-50"
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
                  className="min-h-10 flex-1 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
                />
                <button
                  onClick={() => setShowManagerToken(!showManagerToken)}
                  className="min-h-10 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-secondary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--control-bg-hover)]"
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
              className="min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isUpdatingManagerBotToken ? 'Подключение...' : 'Подключить бота'}
            </button>
          </div>
        )}
      </div>
      <BaseModal
        isOpen={revokeTarget !== null}
        onClose={closeRevokeModal}
        title="Открепить бота"
        cancelLabel="Отмена"
      >
        <p className="text-sm leading-relaxed text-[var(--text-primary)]">
          Вы уверены, что хотите открепить {revokeBotLabel}? После этого бот перестанет
          работать для этого проекта, пока вы не подключите новый токен.
        </p>
        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={handleConfirmRevoke}
            disabled={isRevokingBotToken}
            className="min-h-9 rounded-lg bg-[var(--accent-danger)] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[var(--accent-danger-text)] disabled:cursor-wait disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-[var(--accent-danger)]/25"
          >
            {isRevokingBotToken ? 'Открепление...' : 'Открепить'}
          </button>
        </div>
      </BaseModal>

    </div>
  );
};
