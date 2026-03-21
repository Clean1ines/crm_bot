import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '@shared/api/queryClient';
import { ChatInterface } from '@/widgets/chat-window/ui/ChatInterface';
import { WorkspacePage } from '@/pages/workspace/WorkspacePage';
import { WorkflowChatPage } from '@/pages/workspace/WorkflowChatPage'; // ADDED
import { AuthGuard } from '@/features/auth/protect-routes/AuthGuard';
import { LoginPage } from '@/pages/login/LoginPage';
import { ProtectedLayout } from '@/widgets/layout/ui/ProtectedLayout';
import { Toast } from '@shared/ui/toast/Toast';

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
        <div className="min-h-screen w-screen flex items-center justify-center bg-[#000000] text-white">
          <div className="text-center p-8">
            <h2 className="text-2xl font-bold text-[#b8956a] mb-4">Что-то пошло не так</h2>
            <button onClick={() => window.location.reload()} className="px-4 py-2 bg-[#b8956a] text-black rounded hover:bg-[#d4b48a]">
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
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/"
              element={
                <AuthGuard>
                  <ProtectedLayout />
                </AuthGuard>
              }
            >
              <Route index element={<ChatInterface />} />
            </Route>
            <Route
              path="/workspace"
              element={
                <AuthGuard>
                  <WorkspacePage />
                </AuthGuard>
              }
            />
            {/* ADDED: маршрут для страницы чата выполнения воркфлоу */}
            <Route
              path="/workspace/chat"
              element={
                <AuthGuard>
                  <WorkflowChatPage />
                </AuthGuard>
              }
            />
            <Route path="/workspace.html" element={<Navigate to="/workspace" replace />} />
          </Routes>
        </BrowserRouter>
        <Toast />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;