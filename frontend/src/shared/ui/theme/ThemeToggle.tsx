import { t } from '../../i18n';
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
  auto: t('theme.mode.auto'),
  light: t('theme.mode.light'),
  dark: t('theme.mode.dark'),
  system: t('theme.mode.system'),
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
      className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg bg-[var(--control-bg)] px-3 text-xs font-medium text-[var(--text-secondary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--control-bg-hover)] hover:text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
      aria-label={t('theme.toggle.aria', { mode: titleByMode[normalizedMode], resolved: resolvedTheme === 'dark' ? t('theme.resolved.dark') : t('theme.resolved.light') })}
      title={t('theme.toggle.title', { mode: titleByMode[normalizedMode] })}
    >
      {iconByMode[normalizedMode]}
      {!compact && <span>{labelByMode[normalizedMode]}</span>}
    </button>
  );
};
