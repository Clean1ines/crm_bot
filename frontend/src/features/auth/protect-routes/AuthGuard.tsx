import React, { useState, useEffect } from 'react';
import { api } from '@shared/api';
import { LoginPage } from '@/pages/login/LoginPage';

interface AuthGuardProps {
  children: React.ReactNode;
}

export const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const { data, error } = await api.auth.session();
      console.log('[AuthGuard] Session response:', { data, error });
      // Проверяем, что data не null/undefined и содержит свойство authenticated
      if (data && typeof data === 'object' && 'authenticated' in data) {
        setIsAuthenticated(data.authenticated === true);
      } else {
        setIsAuthenticated(false);
      }
    } catch (err) {
      console.error('[AuthGuard] Session check failed:', err);
      setIsAuthenticated(false);
    } finally {
      setChecking(false);
    }
  };

  if (checking) {
    return (
      <div className="min-h-screen w-screen flex items-center justify-center bg-[#000000]">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-[#b8956a] border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-[#86868b] text-sm">Checking session...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return <>{children}</>;
};
