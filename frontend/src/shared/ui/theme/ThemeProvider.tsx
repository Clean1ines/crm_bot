import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  applyThemeMode,
  getStoredThemeMode,
  resolveThemeMode,
  storeThemeMode,
  type ThemeMode,
} from './themeStorage';
import { ThemeContext, type ThemeContextValue } from './themeContext';

interface ThemeProviderProps {
  children: React.ReactNode;
}

const nextModeByMode: Record<ThemeMode, ThemeMode> = {
  auto: 'light',
  light: 'dark',
  dark: 'auto',
  system: 'light',
};

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  const [mode, setModeState] = useState<ThemeMode>(() => getStoredThemeMode());
  const [themeClock, setThemeClock] = useState(0);

  const normalizedMode = mode === 'system' ? 'auto' : mode;
  const resolvedTheme = resolveThemeMode(normalizedMode);

  const setMode = useCallback((nextMode: ThemeMode) => {
    const normalizedNextMode = nextMode === 'system' ? 'auto' : nextMode;
    storeThemeMode(normalizedNextMode);
    applyThemeMode(normalizedNextMode);
    setModeState(normalizedNextMode);
  }, []);

  const toggleTheme = useCallback(() => {
    setMode(nextModeByMode[normalizedMode]);
  }, [normalizedMode, setMode]);

  useEffect(() => {
    applyThemeMode(normalizedMode);
  }, [normalizedMode, themeClock]);

  useEffect(() => {
    const refreshThemeClock = () => setThemeClock((value) => value + 1);

    const intervalId = window.setInterval(refreshThemeClock, 60_000);
    window.addEventListener('visibilitychange', refreshThemeClock);
    window.addEventListener('focus', refreshThemeClock);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('visibilitychange', refreshThemeClock);
      window.removeEventListener('focus', refreshThemeClock);
    };
  }, []);

  const value = useMemo<ThemeContextValue>(() => ({
    mode: normalizedMode,
    resolvedTheme,
    setMode,
    toggleTheme,
  }), [normalizedMode, resolvedTheme, setMode, toggleTheme]);

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};
