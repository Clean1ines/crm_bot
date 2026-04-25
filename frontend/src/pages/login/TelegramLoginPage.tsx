import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navbar } from './components/Navbar';
import { HeroSection } from './components/HeroSection';
import { ChatWidget } from './components/ChatWidget';
import '../../app/styles/landing.css';
import { api, getErrorMessage, setSessionToken } from '@shared/api/client';
import { GoogleAuthButton } from '@features/auth/google/GoogleAuthButton';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const TelegramLoginPage: React.FC = () => {
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showAuthPanel, setShowAuthPanel] = useState(false);
  const [showTelegramWidget, setShowTelegramWidget] = useState(false);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [resetNewPassword, setResetNewPassword] = useState('');
  const [verificationMessage, setVerificationMessage] = useState('');
  const [resetMessage, setResetMessage] = useState('');
  const [resetLink, setResetLink] = useState('');
  const widgetContainerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const log = (label: string, data?: unknown) => {
    console.log(`[TG-FRONT] ${label}`, data ?? '');
  };

  // Fetch bot username for widget
  useEffect(() => {
    log('BOT_FETCH_START');
    fetch(`${API_BASE_URL}/api/bot/username`)
      .then(async (res) => {
        const txt = await res.text();
        if (!res.ok) throw new Error(txt);
        const json = JSON.parse(txt);
        log('BOT_FETCH_OK', json);
        setBotUsername(json.username);
      })
      .catch((err) => log('BOT_FETCH_ERROR', err));
  }, []);

  // Handle Telegram callback (hash in URL)
  useEffect(() => {
    const raw = window.location.search;
    if (!raw) return;

    const params = new URLSearchParams(raw);
    const data = Object.fromEntries(params.entries());

    if (!data.hash) return;

    setIsLoading(true);
    log('AUTH_REQUEST', data);

    fetch(`${API_BASE_URL}/api/auth/telegram`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
      .then(async (res) => {
        if (!res.ok) {
          const errText = await res.text();
          throw new Error(errText);
        }
        return res.json();
      })
      .then((res) => {
        log('AUTH_SUCCESS', res);
        setSessionToken(res.access_token);
        navigate('/', { replace: true });
      })
      .catch((err) => {
        log('AUTH_ERROR', err);
        setIsLoading(false);
      });
  }, [navigate]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const verificationToken = params.get('verify_email_token');
    const incomingResetToken = params.get('reset_password_token');

    if (incomingResetToken) {
      setResetToken(incomingResetToken);
    }

    if (!verificationToken) return;

    setIsLoading(true);
    setAuthError('');
    api.auth.confirmEmailVerification({ token: verificationToken })
      .then(() => {
        setVerificationMessage('Email успешно подтвержден. Теперь можно входить этим способом.');
      })
      .catch((error) => {
        setAuthError(getErrorMessage(error));
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, []);

  // Inject Telegram widget only after the Telegram auth option is selected.
  useEffect(() => {
    if (!showTelegramWidget) return;
    if (!botUsername) return;

    const container = widgetContainerRef.current;
    if (!container) return;

    // Clear container in case it was already used
    container.innerHTML = '';

    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.setAttribute('data-telegram-login', botUsername);
    script.setAttribute('data-size', 'large');
    script.setAttribute('data-userpic', 'false');
    script.setAttribute('data-request-access', 'write');
    script.setAttribute('data-auth-url', window.location.origin + window.location.pathname);
    script.async = true;

    script.onload = () => log('WIDGET_LOADED');
    script.onerror = () => {
      log('WIDGET_LOAD_ERROR');
      container.innerHTML = '<p class="text-red-600">Ошибка загрузки виджета. Попробуйте позже.</p>';
    };
    container.appendChild(script);
  }, [showTelegramWidget, botUsername]);

  const handleLoginClick = () => {
    setShowAuthPanel(true);
  };

  const handleTelegramLoginClick = () => {
    setShowTelegramWidget(true);
  };

  const handleEmailAuth = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsLoading(true);
    setAuthError('');
    try {
      const result = authMode === 'register'
        ? await api.auth.emailRegister({
          email,
          password,
          full_name: fullName || undefined,
        })
        : await api.auth.emailLogin({ email, password });
      setSessionToken(result.data.access_token);
      navigate('/', { replace: true });
    } catch (error) {
      setAuthError(getErrorMessage(error));
      setIsLoading(false);
    }
  };

  const handleGoogleCredential = async (idToken: string) => {
    setIsLoading(true);
    setAuthError('');
    try {
      const result = await api.auth.googleLoginWithIdToken({ id_token: idToken });
      setSessionToken(result.data.access_token);
      navigate('/', { replace: true });
    } catch (error) {
      setAuthError(getErrorMessage(error));
      setIsLoading(false);
    }
  };

  const handlePasswordResetRequest = async () => {
    setIsLoading(true);
    setAuthError('');
    setResetMessage('');
    try {
      if (!email.trim()) throw new Error('Укажите email для сброса пароля');
      const result = await api.auth.requestPasswordReset({ email: email.trim() });
      const data = result.data as { url?: string | null; token?: string | null };
      setResetLink(data.url || data.token || '');
      setResetMessage('Ссылка для сброса подготовлена.');
    } catch (error) {
      setAuthError(getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  };

  const handlePasswordResetConfirm = async () => {
    setIsLoading(true);
    setAuthError('');
    setResetMessage('');
    try {
      if (!resetToken.trim()) throw new Error('Укажите reset token');
      if (!resetNewPassword.trim()) throw new Error('Укажите новый пароль');
      await api.auth.confirmPasswordReset({
        token: resetToken.trim(),
        new_password: resetNewPassword,
      });
      setResetNewPassword('');
      setResetMessage('Пароль обновлен. Теперь можно войти по email.');
    } catch (error) {
      setAuthError(getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading || window.location.search.includes('hash=')) {
    return (
      <div className="min-h-screen w-screen flex items-center justify-center bg-[var(--bg-primary)]">
        <div className="flex flex-col items-center gap-4">
          <div className="spinner"></div>
          <span className="text-[var(--text-secondary)] font-medium">Verifying Telegram session...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen overflow-hidden bg-[var(--bg-primary)]">
      <Navbar onLoginClick={handleLoginClick} />
      <main className="mx-auto h-[calc(100vh-80px)] max-w-7xl overflow-hidden px-6 py-8 md:px-12">
        <div className="grid h-full grid-cols-1 items-center gap-8 md:grid-cols-2">
          <HeroSection />
          <div className="relative max-h-full overflow-hidden">
            {!showAuthPanel ? (
              <ChatWidget />
            ) : (
              <div className="max-h-[calc(100vh-120px)] overflow-y-auto rounded-3xl border border-[var(--border-subtle)] bg-[var(--surface-card)] p-5 shadow-xl">
                  <div className="mb-4 flex rounded-full bg-[var(--surface-secondary)] p-1">
                    <button
                      type="button"
                      onClick={() => setAuthMode('login')}
                      className={`flex-1 rounded-full px-4 py-2 text-sm font-medium transition ${authMode === 'login' ? 'bg-white text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-muted)]'}`}
                    >
                      Войти по email
                    </button>
                    <button
                      type="button"
                      onClick={() => setAuthMode('register')}
                      className={`flex-1 rounded-full px-4 py-2 text-sm font-medium transition ${authMode === 'register' ? 'bg-white text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-muted)]'}`}
                    >
                      Регистрация
                    </button>
                  </div>
                  <form className="space-y-3" onSubmit={handleEmailAuth}>
                    {authMode === 'register' ? (
                      <input
                        value={fullName}
                        onChange={(event) => setFullName(event.target.value)}
                        placeholder="Имя"
                        className="w-full rounded-xl border border-[var(--border-subtle)] bg-white px-4 py-3 text-sm"
                      />
                    ) : null}
                    <input
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="email@example.com"
                      className="w-full rounded-xl border border-[var(--border-subtle)] bg-white px-4 py-3 text-sm"
                      required
                    />
                    <input
                      type="password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder="Пароль"
                      className="w-full rounded-xl border border-[var(--border-subtle)] bg-white px-4 py-3 text-sm"
                      required
                    />
                    {authError ? <p className="text-sm text-red-600">{authError}</p> : null}
                    <button
                      type="submit"
                      disabled={isLoading}
                      className="w-full rounded-xl bg-[var(--accent-primary)] px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"
                    >
                      {authMode === 'register' ? 'Создать аккаунт' : 'Войти'}
                    </button>
                  </form>
                  <button
                    type="button"
                    onClick={handlePasswordResetRequest}
                    disabled={isLoading}
                    className="mt-3 w-full rounded-xl border border-[var(--border-subtle)] bg-white px-4 py-3 text-sm font-medium text-[var(--text-primary)] disabled:opacity-60"
                  >
                    Сбросить пароль по email
                  </button>
                  {verificationMessage ? <p className="mt-3 text-sm text-emerald-600">{verificationMessage}</p> : null}
                  {resetMessage ? <p className="mt-3 text-sm text-emerald-600">{resetMessage}</p> : null}
                  {resetLink ? (
                    <textarea
                      readOnly
                      value={resetLink}
                      className="mt-3 min-h-20 w-full rounded-xl border border-[var(--border-subtle)] bg-white px-4 py-3 text-sm"
                    />
                  ) : null}
                  <div className="mt-3 space-y-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-4">
                    <input
                      value={resetToken}
                      onChange={(event) => setResetToken(event.target.value)}
                      placeholder="Reset token"
                      className="w-full rounded-xl border border-[var(--border-subtle)] bg-white px-4 py-3 text-sm"
                    />
                    <input
                      type="password"
                      value={resetNewPassword}
                      onChange={(event) => setResetNewPassword(event.target.value)}
                      placeholder="Новый пароль после reset"
                      className="w-full rounded-xl border border-[var(--border-subtle)] bg-white px-4 py-3 text-sm"
                    />
                    <button
                      type="button"
                      onClick={handlePasswordResetConfirm}
                      disabled={isLoading}
                      className="w-full rounded-xl border border-[var(--border-subtle)] bg-white px-4 py-3 text-sm font-medium text-[var(--text-primary)] disabled:opacity-60"
                    >
                      Подтвердить сброс пароля
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={handleTelegramLoginClick}
                    className="mt-3 w-full rounded-xl border border-[var(--border-subtle)] bg-white px-4 py-3 text-sm font-medium text-[var(--text-primary)]"
                  >
                    Войти через Telegram
                  </button>
                  {showTelegramWidget ? (
                    <div
                      ref={widgetContainerRef}
                      className="mt-3 flex w-full justify-center"
                    />
                  ) : null}
                  <div className="mt-3 space-y-2">
                    <GoogleAuthButton
                      text="continue_with"
                      onCredential={handleGoogleCredential}
                      onError={setAuthError}
                    />
                  </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};
