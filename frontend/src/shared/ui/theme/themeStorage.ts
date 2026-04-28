export type ThemeMode = 'light' | 'dark' | 'system';

const THEME_STORAGE_KEY = 'omnica-theme-mode';

const themeModes = new Set<ThemeMode>(['light', 'dark', 'system']);

export const isThemeMode = (value: string | null): value is ThemeMode => (
  value !== null && themeModes.has(value as ThemeMode)
);

export const getStoredThemeMode = (): ThemeMode => {
  if (typeof window === 'undefined') {
    return 'light';
  }

  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return isThemeMode(stored) ? stored : 'light';
};

export const storeThemeMode = (mode: ThemeMode): void => {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.setItem(THEME_STORAGE_KEY, mode);
};

export const resolveThemeMode = (mode: ThemeMode): 'light' | 'dark' => {
  if (mode !== 'system') {
    return mode;
  }

  if (typeof window === 'undefined') {
    return 'light';
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

export const applyThemeMode = (mode: ThemeMode): void => {
  if (typeof document === 'undefined') {
    return;
  }

  const resolvedTheme = resolveThemeMode(mode);
  document.documentElement.dataset.theme = resolvedTheme;
  document.documentElement.dataset.themeMode = mode;
};
