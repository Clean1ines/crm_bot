import React, { useState } from 'react';
import { api } from '@shared/api';
import { useNotification } from '@/shared/lib/notification/useNotifications';

export const LoginPage: React.FC = () => {
  const [masterKey, setMasterKey] = useState('');
  const [loading, setLoading] = useState(false);
  const { showNotification, showApiError } = useNotification();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (masterKey.length < 8) {
      showNotification('⚠️ Мастер-ключ должен быть не менее 8 символов', 'error');
      return;
    }

    setLoading(true);

    try {
      const res = await api.auth.login({ master_key: masterKey });
      
      if (res.authenticated || res.status === 'authenticated') {
        showNotification('✅ Успешный вход!', 'success');
        // #CHANGED: редирект на главную страницу, где теперь есть ProjectsSidebar
        window.location.href = '/';
      } else {
        showNotification('❌ Ошибка аутентификации', 'error');
      }
    } catch (error) {
      showApiError(error, 'Ошибка входа');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-screen flex items-center justify-center bg-[#000000] bg-[radial-gradient(circle_at_50%_50%,_#1a1a1e_0%,_#000000_100%)]">
      <div className="w-full max-w-md p-8 bg-[rgba(28,28,30,0.65)] backdrop-blur-[40px] border border-[rgba(255,255,255,0.08)] rounded-2xl shadow-[0_20px_40px_rgba(0,0,0,0.6)]">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-[#b8956a] tracking-[2px] uppercase mb-2">
            MRAK-OS
          </h1>
          <p className="text-sm text-[#86868b]">
            Secure Workspace Authentication
          </p>
        </div>

        <form onSubmit={handleLogin} className="space-y-6">
          <div>
            <label className="block text-[10px] text-[#86868b] uppercase tracking-wider mb-2">
              Master Key
            </label>
            <input
              type="password"
              value={masterKey}
              onChange={(e) => setMasterKey(e.target.value)}
              placeholder="Enter your master key (min 8 characters)"
              className="w-full bg-[rgba(0,0,0,0.4)] border border-[rgba(255,255,255,0.08)] rounded-lg px-4 py-3 text-sm text-[#f5f5f7] outline-none focus:border-[#b8956a] transition-colors"
              disabled={loading}
            />
          </div>

          <button
            type="submit"
            disabled={loading || masterKey.length < 8}
            className="w-full px-4 py-3 text-xs font-semibold rounded-lg bg-gradient-[135deg,#8a6d4a,#b8956a] text-black hover:bg-gradient-[135deg,#b8956a,#d4b48a] transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          >
            {loading ? 'Authenticating...' : '🔓 Enter Workspace'}
          </button>
        </form>

        <div className="mt-8 pt-6 border-t border-[rgba(255,255,255,0.08)]">
          <div className="flex items-center gap-2 text-[10px] text-[#86868b]">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="11" width="18" height="11" rx="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            <span>Session secured with Bearer token</span>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-[#86868b] mt-2">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            <span>Session expires after 24 hours</span>
          </div>
        </div>
      </div>
    </div>
  );
};
