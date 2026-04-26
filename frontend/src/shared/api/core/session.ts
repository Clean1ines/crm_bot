import { queryClient } from '../queryClient';
import {
  AUTH_CLEARED_EVENT,
  LOGIN_PATH,
  SESSION_TOKEN_KEY,
} from './config';

declare global {
  interface Window {
    __isRedirectingToLogin?: boolean;
  }
}

export const getSessionToken = (): string | null => localStorage.getItem(SESSION_TOKEN_KEY);

export const setSessionToken = (token: string): void => {
  localStorage.setItem(SESSION_TOKEN_KEY, token);
};

export const clearSessionToken = (): void => {
  localStorage.removeItem(SESSION_TOKEN_KEY);
};

export const isUnauthorized = (response: Response): boolean => response.status === 401;

/**
 * Central 401 contract:
 * - clear token
 * - clear React Query cache best-effort
 * - emit auth cleared event
 * - redirect to /login once
 * - return whether session existed before cleanup
 */
export const handleUnauthorizedResponse = (): boolean => {
  const hadSession = getSessionToken() !== null;

  clearSessionToken();

  try {
    queryClient.clear();
  } catch {
    // Query cache cleanup is best-effort. Auth cleanup and redirect must still happen.
  }

  window.dispatchEvent(new Event(AUTH_CLEARED_EVENT));

  if (window.location.pathname === LOGIN_PATH) {
    return hadSession;
  }

  if (window.__isRedirectingToLogin) {
    return hadSession;
  }

  window.__isRedirectingToLogin = true;
  window.location.replace(LOGIN_PATH);

  return hadSession;
};
