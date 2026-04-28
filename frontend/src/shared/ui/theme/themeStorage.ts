export type ThemeMode = 'auto' | 'light' | 'dark' | 'system';

const THEME_STORAGE_KEY = 'omnica-theme-mode';

const themeModes = new Set<ThemeMode>(['auto', 'light', 'dark', 'system']);

const AUTO_DARK_START_HOUR = 20;
const AUTO_DARK_END_HOUR = 7;

export const isThemeMode = (value: string | null): value is ThemeMode => (
  value !== null && themeModes.has(value as ThemeMode)
);

export const getStoredThemeMode = (): ThemeMode => {
  if (typeof window === 'undefined') {
    return 'auto';
  }

  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);

  if (!isThemeMode(stored)) {
    return 'auto';
  }

  // Legacy migration: previous builds used "system".
  // Product behavior now expects time-based automatic theme.
  return stored === 'system' ? 'auto' : stored;
};

export const storeThemeMode = (mode: ThemeMode): void => {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.setItem(THEME_STORAGE_KEY, mode === 'system' ? 'auto' : mode);
};

const resolveAutoThemeByLocalTime = (): 'light' | 'dark' => {
  const hour = new Date().getHours();
  return hour >= AUTO_DARK_START_HOUR || hour < AUTO_DARK_END_HOUR ? 'dark' : 'light';
};

export const resolveThemeMode = (mode: ThemeMode): 'light' | 'dark' => {
  if (mode === 'light' || mode === 'dark') {
    return mode;
  }

  return resolveAutoThemeByLocalTime();
};

export const applyThemeMode = (mode: ThemeMode): void => {
  if (typeof document === 'undefined') {
    return;
  }

  const normalizedMode = mode === 'system' ? 'auto' : mode;
  const resolvedTheme = resolveThemeMode(normalizedMode);
  document.documentElement.dataset.theme = resolvedTheme;
  document.documentElement.dataset.themeMode = normalizedMode;
};
