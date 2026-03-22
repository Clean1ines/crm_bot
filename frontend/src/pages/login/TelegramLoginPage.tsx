import React, { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

export const TelegramLoginPage: React.FC = () => {
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const widgetContainerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const log = (label: string, data?: any) => {
    console.log(`[TG-FRONT] ${label}`, data ?? "");
  };

  // 1. Получаем username бота
  useEffect(() => {
    log("BOT_FETCH_START");
    fetch(`${API_BASE_URL}/api/bot/username`)
      .then(async (res) => {
        const txt = await res.text();
        if (!res.ok) throw new Error(txt);
        const json = JSON.parse(txt);
        log("BOT_FETCH_OK", json);
        setBotUsername(json.username);
      })
      .catch((err) => log("BOT_FETCH_ERROR", err));
  }, []);

  // 2. Обработка callback ОТ TELEGRAM
  useEffect(() => {
    const raw = window.location.search;
    if (!raw) return;

    const params = new URLSearchParams(raw);
    const data = Object.fromEntries(params.entries());

    if (!data.hash) return;

    // УБРАЛИ ПРОВЕРКУ tg_done, ЧТОБЫ ИСКЛЮЧИТЬ ЗАВИСАНИЕ
    log("AUTH_REQUEST", data);

    fetch(`${API_BASE_URL}/api/auth/telegram`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
        log("AUTH_SUCCESS", res);
        localStorage.setItem("mrak_token", res.access_token);
        // Редирект через navigate, чтобы не рвать сетевые запросы
        navigate("/projects", { replace: true });
      })
      .catch((err) => {
        log("AUTH_ERROR", err);
      });
  }, [navigate]);

  // 3. Инжект виджета
  useEffect(() => {
    if (!botUsername || !widgetContainerRef.current) return;
    
    // Если в URL есть хэш, не рисуем виджет, чтобы не путать юзера
    if (window.location.search.includes("hash=")) return;

    widgetContainerRef.current.innerHTML = "";
    log("INJECTING_WIDGET");

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-userpic", "false");
    script.setAttribute("data-request-access", "write");
    script.setAttribute("data-auth-url", window.location.origin + window.location.pathname);
    script.async = true;

    script.onload = () => log("WIDGET_LOADED");
    widgetContainerRef.current.appendChild(script);
  }, [botUsername]);

  return (
    <div className="min-h-screen w-screen flex items-center justify-center bg-black text-white">
      {window.location.search.includes("hash=") ? (
        <div className="flex flex-col items-center gap-4">
           <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin"></div>
           <span className="text-orange-500 font-medium">Verifying Telegram session...</span>
        </div>
      ) : !botUsername ? (
        <span className="opacity-50">Initializing secure connection...</span>
      ) : (
        <div ref={widgetContainerRef} />
      )}
    </div>
  );
};