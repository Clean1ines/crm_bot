import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link, useParams } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '@shared/api/queryClient';
import { Toast } from '@shared/ui/toast/Toast';
import { ThemeProvider } from '@shared/ui/theme';
import { ClientChatPage } from '@pages/chat/ClientChatPage';
import { TicketsPage } from '@pages/manager/TicketsPage';
import { TicketDetailPage } from '@pages/manager/TicketDetailPage';
import { TelegramLoginPage } from '@pages/login/TelegramLoginPage';
import { DialogsPage } from '@pages/dialogs/DialogsPage';
import { ComingSoon } from '@pages/ComingSoon';
import { ChannelSettingsPage } from '@pages/channels/ChannelSettingsPage';
import { KnowledgePage } from '@pages/knowledge/KnowledgePage';
import { ManagersPage } from '@pages/managers/ManagersPage';
import { ClientsPage } from '@pages/clients/ClientsPage';
import { ProjectSettingsPage } from '@pages/settings/ProjectSettingsPage';
import { ProfilePage } from '@pages/profile/ProfilePage';
import { Layout } from './Layout';
import { getSessionToken } from '@shared/api/core/session';
import { getProjectHomePath, isProjectAdminRole } from '@entities/project/model/access';
import { useProjects } from '@entities/project/api/useProjects';

const loadingScreen = (
  <div className="flex items-center justify-center h-screen bg-[#1E1E1E] text-[#E5E2DA]">
    Загрузка...
  </div>
);

const AuthGuard = ({ children }: { children: React.ReactNode }) => {
  const token = getSessionToken();
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

const AuthenticatedRootRedirect: React.FC = () => {
  const { projects, isLoading } = useProjects();

  if (isLoading) {
    return loadingScreen;
  }

  if (!projects || projects.length === 0) {
    return <Navigate to="/channels" replace />;
  }

  const firstProject = projects[0];
  return <Navigate to={getProjectHomePath(firstProject.id, firstProject.access_role)} replace />;
};

const RootRedirect: React.FC = () => {
  const token = getSessionToken();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return <AuthenticatedRootRedirect />;
};

const ProjectAdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { projectId } = useParams<{ projectId: string }>();
  const { projects, isLoading } = useProjects();

  if (isLoading) {
    return loadingScreen;
  }

  if (!projectId) {
    return <Navigate to="/" replace />;
  }

  const currentProject = projects.find((project) => project.id === projectId);
  if (!currentProject) {
    return <Navigate to="/" replace />;
  }

  if (isProjectAdminRole(currentProject.access_role)) {
    return <>{children}</>;
  }

  const fallbackPath = getProjectHomePath(projectId, currentProject.access_role);

  return (
    <div className="mx-auto max-w-2xl p-6 sm:p-8">
      <div className="rounded-2xl bg-[var(--surface-elevated)] p-6 shadow-[var(--shadow-card)]">
        <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)]">
          Раздел недоступен для manager
        </h1>
        <p className="mt-3 text-sm text-[var(--text-secondary)]">
          В этой панели manager доступны только тикеты, диалоги и клиентская информация, нужные для обработки обращений.
        </p>
        <div className="mt-5">
          <Link
            to={fallbackPath}
            className="inline-flex min-h-10 items-center rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)]"
          >
            Перейти в рабочий раздел
          </Link>
        </div>
      </div>
    </div>
  );
};

const WorkspaceAdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { projects, isLoading } = useProjects();

  if (isLoading) {
    return loadingScreen;
  }

  if (!projects.length || projects.some((project) => isProjectAdminRole(project.access_role))) {
    return <>{children}</>;
  }

  const firstProject = projects[0];
  return (
    <div className="mx-auto max-w-2xl p-6 sm:p-8">
      <div className="rounded-2xl bg-[var(--surface-elevated)] p-6 shadow-[var(--shadow-card)]">
        <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)]">
          Раздел недоступен для manager
        </h1>
        <p className="mt-3 text-sm text-[var(--text-secondary)]">
          Настройка каналов и токенов доступна только owner и admin проекта.
        </p>
        <div className="mt-5">
          <Link
            to={getProjectHomePath(firstProject.id, firstProject.access_role)}
            className="inline-flex min-h-10 items-center rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)]"
          >
            Вернуться к рабочему разделу
          </Link>
        </div>
      </div>
    </div>
  );
};

const DialogsPageWrapper = () => {
  const { projectId } = useParams<{ projectId: string }>();
  return <DialogsPage key={projectId} />;
};

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen w-screen flex items-center justify-center bg-black text-white">
          <div className="text-center p-8">
            <h2 className="text-2xl font-bold text-[#b8956a] mb-4">Что-то пошло не так</h2>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-[#b8956a] text-black rounded hover:bg-[#d4b48a]"
            >
              Обновить страницу
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<TelegramLoginPage />} />
            <Route path="/" element={<RootRedirect />} />

            <Route element={<AuthGuard><Layout /></AuthGuard>}>
              <Route path="/chat/:projectId" element={<ClientChatPage />} />
              <Route path="/projects/:projectId/dialogs" element={<DialogsPageWrapper />} />
              <Route
                path="/projects/:projectId/clients"
                element={<ErrorBoundary><ClientsPage /></ErrorBoundary>}
              />
              <Route path="/projects/:projectId/workflow" element={<ComingSoon />} />
              <Route
                path="/projects/:projectId/knowledge"
                element={<ProjectAdminRoute><ErrorBoundary><KnowledgePage /></ErrorBoundary></ProjectAdminRoute>}
              />
              <Route path="/projects/:projectId/analytics" element={<ComingSoon />} />
              <Route
                path="/projects/:projectId/channels"
                element={<ProjectAdminRoute><ChannelSettingsPage /></ProjectAdminRoute>}
              />
              <Route path="/projects/:projectId/tickets" element={<TicketsPage />} />
              <Route path="/projects/:projectId/tickets/:threadId" element={<TicketDetailPage />} />
              <Route
                path="/projects/:projectId/managers"
                element={<ProjectAdminRoute><ErrorBoundary><ManagersPage /></ErrorBoundary></ProjectAdminRoute>}
              />
              <Route path="/projects/:projectId/billing" element={<ComingSoon />} />
              <Route
                path="/projects/:projectId/settings"
                element={<ProjectAdminRoute><ErrorBoundary><ProjectSettingsPage /></ErrorBoundary></ProjectAdminRoute>}
              />
              <Route path="/profile" element={<ErrorBoundary><ProfilePage /></ErrorBoundary>} />
              <Route path="/channels" element={<WorkspaceAdminRoute><ChannelSettingsPage /></WorkspaceAdminRoute>} />
            </Route>
          </Routes>
        </BrowserRouter>
        <Toast />
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
