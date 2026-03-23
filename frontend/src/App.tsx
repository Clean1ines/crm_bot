import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '@shared/api/queryClient';
import { Toast } from '@shared/ui/toast/Toast';
import { ProjectsPage } from '@pages/projects/ProjectsPage';
import { ProjectDetailPage } from '@pages/projects/ProjectDetailPage';
import { ClientChatPage } from '@pages/chat/ClientChatPage';
import { TicketsPage } from '@pages/manager/TicketsPage';
import { TicketDetailPage } from '@pages/manager/TicketDetailPage';
import { TelegramLoginPage } from '@pages/login/TelegramLoginPage';
import { DialogsPage } from '@pages/dialogs/DialogsPage';
import { ComingSoon } from '@pages/ComingSoon';
import { Layout } from './app/Layout';
import { getSessionToken } from '@shared/api/client';

const AuthGuard = ({ children }: { children: React.ReactNode }) => {
  const token = getSessionToken();
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
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
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<TelegramLoginPage />} />
            <Route path="/" element={<Navigate to="/projects" replace />} />
            
            <Route element={<AuthGuard><Layout /></AuthGuard>}>
              <Route path="/projects" element={<ProjectsPage />} />
              <Route path="/projects/:projectId" element={<DialogsPage />} />
              <Route path="/chat/:projectId" element={<ClientChatPage />} />
              <Route path="/manager/tickets" element={<TicketsPage />} />
              <Route path="/manager/tickets/:threadId" element={<TicketDetailPage />} />
              <Route path="/projects/:projectId/dialogs" element={<DialogsPage />} />
              <Route path="/projects/:projectId/clients" element={<ComingSoon />} />
              <Route path="/projects/:projectId/workflow" element={<ComingSoon />} />
              <Route path="/projects/:projectId/knowledge" element={<ComingSoon />} />
              <Route path="/projects/:projectId/analytics" element={<ComingSoon />} />
              <Route path="/projects/:projectId/channels" element={<ComingSoon />} />
              <Route path="/projects/:projectId/managers" element={<ComingSoon />} />
              <Route path="/projects/:projectId/billing" element={<ComingSoon />} />
              <Route path="/projects/:projectId/settings" element={<ComingSoon />} />
            </Route>
          </Routes>
        </BrowserRouter>
        <Toast />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
