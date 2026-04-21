import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '@shared/api/queryClient';
import { Toast } from '@shared/ui/toast/Toast';
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
import { Layout } from './Layout';
import { getSessionToken } from '@shared/api/client';
import { useProjects } from '@entities/project/api/useProjects';

const AuthGuard = ({ children }: { children: React.ReactNode }) => {
  const token = getSessionToken();
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

const RootRedirect: React.FC = () => {
  const token = getSessionToken();
  const { projects, isLoading } = useProjects();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (isLoading) {
    return <div className="flex items-center justify-center h-screen bg-[#1E1E1E] text-[#E5E2DA]">Загрузка...</div>;
  }

  if (!projects || projects.length === 0) {
    return <Navigate to="/channels" replace />;
  }

  const firstProjectId = projects[0].id;
  return <Navigate to={`/projects/${firstProjectId}/dialogs`} replace />;
};

// Обёртка для DialogsPage, которая пересоздаёт компонент при изменении projectId
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
            <Route path="/projects/:projectId/knowledge" element={<ErrorBoundary><KnowledgePage /></ErrorBoundary>} />
            <Route path="/projects/:projectId/analytics" element={<ComingSoon />} />
            <Route path="/projects/:projectId/channels" element={<ChannelSettingsPage />} />
            <Route path="/projects/:projectId/tickets" element={<TicketsPage />} />
            <Route path="/projects/:projectId/tickets/:threadId" element={<TicketDetailPage />} />
            <Route path="/projects/:projectId/managers" element={<ErrorBoundary><ManagersPage /></ErrorBoundary>} />
            <Route path="/projects/:projectId/billing" element={<ComingSoon />} />
            <Route path="/projects/:projectId/settings" element={<ComingSoon />} />
            <Route path="/channels" element={<ChannelSettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toast />
    </QueryClientProvider>
  );
}

export default App;
