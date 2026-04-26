import type { components } from '../generated/schema';
import { API_BASE_URL } from '../core/config';
import { authedJsonRequest } from '../core/http';
import { handleUnauthorizedResponse, isUnauthorized } from '../core/session';

type TelegramAuthData = components['schemas']['TelegramAuthData'];

export type AuthTokenResponse = {
  access_token: string;
  token_type?: string;
  user?: unknown;
};

export const authApi = {
  telegram: async (body: TelegramAuthData): Promise<{ data: AuthTokenResponse; response: Response }> => {
    const response = await fetch(`${API_BASE_URL}/api/auth/telegram`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    const data = await response.json() as AuthTokenResponse;

    if (isUnauthorized(response)) {
      handleUnauthorizedResponse();
    }

    if (!response.ok) {
      throw data;
    }

    return { data, response };
  },

  emailRegister: (body: { email: string; password: string; full_name?: string }) =>
    authedJsonRequest('/api/auth/email/register', { method: 'POST', body }),

  emailLogin: (body: { email: string; password: string }) =>
    authedJsonRequest('/api/auth/email/login', { method: 'POST', body }),

  linkEmail: (body: { email: string; password: string }) =>
    authedJsonRequest('/api/auth/link/email', { method: 'POST', body }),

  requestEmailVerification: () =>
    authedJsonRequest('/api/auth/email/verification/request', { method: 'POST' }),

  confirmEmailVerification: (body: { token: string }) =>
    authedJsonRequest('/api/auth/email/verification/confirm', { method: 'POST', body }),

  googleLogin: (body: { provider_subject: string; email?: string; full_name?: string }) =>
    authedJsonRequest('/api/auth/google/login', { method: 'POST', body }),

  googleLoginWithIdToken: (body: { id_token: string }) =>
    authedJsonRequest('/api/auth/google/login/id-token', { method: 'POST', body }),

  linkGoogle: (body: { provider_subject: string; email?: string }) =>
    authedJsonRequest('/api/auth/link/google', { method: 'POST', body }),

  linkGoogleWithIdToken: (body: { id_token: string }) =>
    authedJsonRequest('/api/auth/link/google/id-token', { method: 'POST', body }),

  changePassword: (body: { new_password: string; current_password?: string }) =>
    authedJsonRequest('/api/auth/password/change', { method: 'POST', body }),

  requestPasswordReset: (body: { email: string }) =>
    authedJsonRequest('/api/auth/password/reset/request', { method: 'POST', body }),

  confirmPasswordReset: (body: { token: string; new_password: string }) =>
    authedJsonRequest('/api/auth/password/reset/confirm', { method: 'POST', body }),

  unlinkMethod: (provider: 'telegram' | 'email' | 'google') =>
    authedJsonRequest(`/api/auth/methods/${provider}`, { method: 'DELETE' }),

  me: () =>
    authedJsonRequest('/api/auth/me', { method: 'GET' }),

  methods: () =>
    authedJsonRequest('/api/auth/methods', { method: 'GET' }),
};
