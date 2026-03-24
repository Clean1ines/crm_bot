import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navbar } from './components/Navbar';
import { HeroSection } from './components/HeroSection';
import { ChatWidget } from './components/ChatWidget';
import '../../app/styles/landing.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const TelegramLoginPage: React.FC = () => {
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showLoginWidget, setShowLoginWidget] = useState(false);
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
        localStorage.setItem('mrak_token', res.access_token);
        navigate('/', { replace: true });
      })
      .catch((err) => {
        log('AUTH_ERROR', err);
        setIsLoading(false);
      });
  }, [navigate]);

  // Inject Telegram widget when showLoginWidget becomes true
  useEffect(() => {
    if (!showLoginWidget) return;
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
  }, [showLoginWidget, botUsername]);

  const handleLoginClick = () => {
    setShowLoginWidget(true);
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
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <Navbar onLoginClick={handleLoginClick} />
      <main className="max-w-7xl mx-auto px-6 md:px-12 py-12">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
          <HeroSection />
          <div className="relative">
            {!showLoginWidget ? (
              <ChatWidget />
            ) : (
              <div
                ref={widgetContainerRef}
                className="flex justify-center w-full"
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );
};
