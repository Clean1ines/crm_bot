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

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  const [mode, setModeState] = useState<ThemeMode>(() => getStoredThemeMode());

  const resolvedTheme = resolveThemeMode(mode);

  const setMode = useCallback((nextMode: ThemeMode) => {
    storeThemeMode(nextMode);
    applyThemeMode(nextMode);
    setModeState(nextMode);
  }, []);

  const toggleTheme = useCallback(() => {
    setMode(resolveThemeMode(mode) === 'dark' ? 'light' : 'dark');
  }, [mode, setMode]);

  useEffect(() => {
    applyThemeMode(mode);

    if (mode !== 'system' || typeof window === 'undefined') {
      return undefined;
    }

    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      applyThemeMode('system');
      setModeState('system');
    };

    media.addEventListener('change', handleChange);
    return () => media.removeEventListener('change', handleChange);
  }, [mode]);

  const value = useMemo<ThemeContextValue>(() => ({
    mode,
    resolvedTheme,
    setMode,
    toggleTheme,
  }), [mode, resolvedTheme, setMode, toggleTheme]);

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};
