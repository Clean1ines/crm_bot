import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navbar } from './components/Navbar';
import { HeroSection } from './components/HeroSection';
import { ChatWidget } from './components/ChatWidget';
import '../../app/styles/landing.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

/**
 * Landing page with Telegram login widget.
 * Handles OAuth callback and redirects to the app root after successful authentication.
 */
export const TelegramLoginPage: React.FC = () => {
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
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
        // Redirect to root, where RootRedirect will decide the final destination
        navigate('/', { replace: true });
      })
      .catch((err) => {
        log('AUTH_ERROR', err);
        setIsLoading(false);
      });
  }, [navigate]);

  // Inject Telegram widget if no hash is present (i.e., we are not in callback mode)
  useEffect(() => {
    if (!botUsername || !widgetContainerRef.current) return;

    // If we are in callback (hash present), don't show widget
    if (window.location.search.includes('hash=')) return;

    widgetContainerRef.current.innerHTML = '';
    log('INJECTING_WIDGET');

    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.setAttribute('data-telegram-login', botUsername);
    script.setAttribute('data-size', 'large');
    script.setAttribute('data-userpic', 'false');
    script.setAttribute('data-request-access', 'write');
    script.setAttribute('data-auth-url', window.location.origin + window.location.pathname);
    script.async = true;

    script.onload = () => log('WIDGET_LOADED');
    widgetContainerRef.current.appendChild(script);
  }, [botUsername]);

  // If we are waiting for auth response, show spinner
  if (isLoading || window.location.search.includes('hash=')) {
    return (
      <div className="min-h-screen w-screen flex items-center justify-center bg-[#F6F4EF]">
        <div className="flex flex-col items-center gap-4">
          <div className="spinner"></div>
          <span className="text-[#6B6B6B] font-medium">Verifying Telegram session...</span>
        </div>
      </div>
    );
  }

  // Otherwise, show full landing page with widget in the right column
  return (
    <div className="min-h-screen bg-[#F6F4EF]">
      <Navbar />
      <main className="max-w-7xl mx-auto px-6 md:px-12 py-12">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
          {/* Left column */}
          <HeroSection />

          {/* Right column */}
          <div className="relative">
            {botUsername ? (
              <div ref={widgetContainerRef} className="flex justify-center" />
            ) : (
              <div className="animate-pulse">
                <ChatWidget />
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};
