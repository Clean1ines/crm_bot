import React from 'react';
import { Clock3, Moon, Sun } from 'lucide-react';
import { useTheme } from './themeContext';
import type { ThemeMode } from './themeStorage';

interface ThemeToggleProps {
  compact?: boolean;
}

const nextModeByMode: Record<ThemeMode, ThemeMode> = {
  auto: 'light',
  light: 'dark',
  dark: 'auto',
  system: 'light',
};

const labelByMode: Record<ThemeMode, string> = {
  auto: 'Auto',
  light: 'Light',
  dark: 'Dark',
  system: 'Auto',
};

const titleByMode: Record<ThemeMode, string> = {
  auto: 'Авто по времени суток',
  light: 'Светлая тема',
  dark: 'Тёмная тема',
  system: 'Авто по времени суток',
};

const iconByMode: Record<ThemeMode, React.ReactNode> = {
  auto: <Clock3 className="h-4 w-4" />,
  light: <Sun className="h-4 w-4" />,
  dark: <Moon className="h-4 w-4" />,
  system: <Clock3 className="h-4 w-4" />,
};

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ compact = false }) => {
  const { mode, resolvedTheme, setMode } = useTheme();
  const normalizedMode = mode === 'system' ? 'auto' : mode;

  const handleClick = () => {
    setMode(nextModeByMode[normalizedMode]);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/30"
      aria-label={`Тема: ${titleByMode[normalizedMode]}, сейчас отображается ${resolvedTheme === 'dark' ? 'тёмная' : 'светлая'}`}
      title={`Тема: ${titleByMode[normalizedMode]}. Нажмите, чтобы переключить.`}
    >
      {iconByMode[normalizedMode]}
      {!compact && <span>{labelByMode[normalizedMode]}</span>}
    </button>
  );
};
