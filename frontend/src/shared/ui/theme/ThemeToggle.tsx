import React from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from './themeContext';

interface ThemeToggleProps {
  compact?: boolean;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ compact = false }) => {
  const { resolvedTheme, toggleTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/30"
      aria-label={isDark ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
      title={isDark ? 'Светлая тема' : 'Тёмная тема'}
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      {!compact && <span>{isDark ? 'Light' : 'Dark'}</span>}
    </button>
  );
};
