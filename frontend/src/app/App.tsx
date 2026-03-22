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
            <Route
              path="/projects"
              element={
                <AuthGuard>
                  <ProjectsPage />
                </AuthGuard>
              }
            />
            <Route
              path="/projects/:projectId"
              element={
                <AuthGuard>
                  <ProjectDetailPage />
                </AuthGuard>
              }
            />
            <Route
              path="/chat/:projectId"
              element={
                <AuthGuard>
                  <ClientChatPage />
                </AuthGuard>
              }
            />
            <Route
              path="/manager/tickets"
              element={
                <AuthGuard>
                  <TicketsPage />
                </AuthGuard>
              }
            />
            <Route
              path="/manager/tickets/:threadId"
              element={
                <AuthGuard>
                  <TicketDetailPage />
                </AuthGuard>
              }
            />
          </Routes>
        </BrowserRouter>
        <Toast />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;