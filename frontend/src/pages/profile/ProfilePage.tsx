import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { t } from '@shared/i18n';

import { getErrorMessage } from '@shared/api/core/errors';
import { authProviderLabel } from '@shared/lib/uiLabels';
import { authApi } from '@shared/api/modules/auth';
import { GoogleAuthButton } from '@features/auth/google/GoogleAuthButton';
import { isGoogleAuthConfigured } from '@features/auth/google/config';

interface AuthMethod {
  provider: string;
  provider_id: string;
  created_at?: string | null;
  verified?: boolean;
  verified_at?: string | null;
}

interface AuthMethodsResponse {
  user_id: string;
  methods: AuthMethod[];
  has_password: boolean;
}

const authMethodSecondaryText = (method: AuthMethod): string => {
  if (method.provider === 'email') return method.provider_id;
  if (method.provider === 'telegram') return t('profile.auth.telegramConnected');
  if (method.provider === 'google') return t('profile.auth.googleConnected');
  return t('profile.auth.genericConnected');
};

export const ProfilePage: React.FC = () => {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [emailVerificationUrl, setEmailVerificationUrl] = useState('');
  const meQuery = useQuery<{ login?: string | null }>({
    queryKey: ['auth-me'],
    queryFn: async () => {
      const result = await authApi.me();
      return result.data as { login?: string | null };
    },
  });
  const [login, setLogin] = useState('');

  const methodsQuery = useQuery<AuthMethodsResponse>({
    queryKey: ['auth-methods'],
    queryFn: async () => {
      const result = await authApi.methods();
      return result.data as AuthMethodsResponse;
    },
  });

  const emailMethod = methodsQuery.data?.methods.find((method) => method.provider === 'email');
  const emailInputValue = email || emailMethod?.provider_id || '';
  const showGoogleAuth = isGoogleAuthConfigured();
  const loginValue = login || meQuery.data?.login || '';
  const normalizedCurrentLogin = (meQuery.data?.login || '').trim();
  const normalizedDraftLogin = loginValue.trim();
  const isLoginChanged = normalizedDraftLogin !== normalizedCurrentLogin;

  const updateLoginMutation = useMutation({
    mutationFn: async () => {
      await authApi.updateMe({ login: login.trim() || null });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth-me'] });
      setLogin('');
      toast.success('Логин сохранён');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const linkEmailMutation = useMutation({
    mutationFn: async () => {
      const normalizedEmail = emailInputValue.trim();
      if (!normalizedEmail) throw new Error(t('profile.email.required'));
      if (!password.trim()) throw new Error(t('profile.email.passwordRequired'));
      await authApi.linkEmail({ email: normalizedEmail, password });
    },
    onSuccess: async () => {
      setPassword('');
      setEmailVerificationUrl('');
      await queryClient.invalidateQueries({ queryKey: ['auth-methods'] });
      toast.success(t('profile.email.linked'));
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const linkGoogleMutation = useMutation({
    mutationFn: async (idToken: string) => {
      await authApi.linkGoogleWithIdToken({ id_token: idToken });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth-methods'] });
      toast.success(t('profile.google.linked'));
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const changePasswordMutation = useMutation({
    mutationFn: async () => {
      if (!newPassword.trim()) throw new Error(t('profile.password.newRequired'));
      await authApi.changePassword({
        new_password: newPassword,
        current_password: currentPassword.trim() || undefined,
      });
    },
    onSuccess: async () => {
      setCurrentPassword('');
      setNewPassword('');
      await queryClient.invalidateQueries({ queryKey: ['auth-methods'] });
      toast.success(t('profile.password.updated'));
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const requestEmailVerificationMutation = useMutation({
    mutationFn: async () => {
      const result = await authApi.requestEmailVerification();
      return result.data as { url?: string | null; token?: string | null };
    },
    onSuccess: async (data) => {
      setEmailVerificationUrl(data.url || data.token || '');
      await queryClient.invalidateQueries({ queryKey: ['auth-methods'] });
      toast.success(t('profile.email.verificationPrepared'));
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const unlinkMethodMutation = useMutation({
    mutationFn: async (provider: 'telegram' | 'email' | 'google') => {
      await authApi.unlinkMethod(provider);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth-methods'] });
      toast.success(t('profile.auth.unlinked'));
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">{t('profile.title')}</h1>
        <p className="mt-2 text-sm text-[var(--text-muted)]">
          {t('profile.description')}
        </p>
      </div>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <h2 className="mb-4 text-lg font-semibold leading-tight text-[var(--text-primary)]">{t('profile.methods.title')}</h2>
        {methodsQuery.isLoading ? (
          <div className="text-sm text-[var(--text-muted)]">{t('common.states.loading')}</div>
        ) : (
          <div className="space-y-2">
            {methodsQuery.data?.methods.map((method) => (
              <div
                key={`${method.provider}-${method.provider_id}`}
                className="flex items-center justify-between gap-3 rounded-xl bg-[var(--control-bg)] px-4 py-3 shadow-[var(--shadow-sm)]"
              >
                <div>
                  <div className="font-medium text-[var(--text-primary)]">{authProviderLabel(method.provider)}</div>
                  <div className="text-xs text-[var(--text-muted)]">{authMethodSecondaryText(method)}</div>
                </div>
                <button
                  type="button"
                  onClick={() => unlinkMethodMutation.mutate(method.provider as 'telegram' | 'email' | 'google')}
                  disabled={unlinkMethodMutation.isPending}
                  className="rounded-lg bg-[var(--control-bg)] px-3 py-2 text-xs font-medium text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--control-bg-hover)] disabled:opacity-50"
                >
                  {t('profile.methods.unlink')}
                </button>
              </div>
            ))}
            {methodsQuery.data?.methods.length === 0 ? (
              <div className="text-sm text-[var(--text-muted)]">{t('profile.methods.empty')}</div>
            ) : null}
          </div>
        )}
      </section>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <h2 className="mb-4 text-lg font-semibold leading-tight text-[var(--text-primary)]">{t('profile.email.title')}</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Логин</span>
            <input
              type="text"
              value={loginValue}
              onChange={(event) => {
                setLogin(event.target.value);
              }}
              placeholder="your_login"
              className="w-full rounded-lg bg-[var(--control-bg)] min-h-10 px-3 py-2 text-sm shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
            />
          </label>
          <div className="flex items-end">
            <button
              type="button"
              onClick={() => updateLoginMutation.mutate()}
              disabled={updateLoginMutation.isPending || !isLoginChanged}
              className="rounded-lg bg-[var(--accent-primary)] min-h-10 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {updateLoginMutation.isPending ? t('common.states.saving') : t('common.actions.save')}
            </button>
          </div>
        </div>
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          Имя в сайдбаре: сначала логин, затем подтверждённый email, затем username Telegram.
        </p>

        <div className="mb-4 rounded-xl bg-[var(--control-bg)] px-4 py-3 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)]">
          {t('profile.email.status')}
          {' '}
          <span className={emailMethod?.verified ? 'text-[var(--accent-success-text)]' : 'text-[var(--accent-warning)]'}>
            {emailMethod?.verified ? t('profile.email.verified') : t('profile.email.notVerified')}
          </span>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Email</span>
            <input
              type="email"
              value={emailInputValue}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-lg bg-[var(--control-bg)] min-h-10 px-3 py-2 text-sm shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Пароль для входа по email</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-lg bg-[var(--control-bg)] min-h-10 px-3 py-2 text-sm shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
            />
          </label>
        </div>
        <button
          onClick={() => linkEmailMutation.mutate()}
          disabled={linkEmailMutation.isPending}
          className="mt-5 rounded-lg bg-[var(--accent-primary)] min-h-10 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {linkEmailMutation.isPending ? t('common.states.saving') : t('profile.email.linkAction')}
        </button>
        <button
          onClick={() => requestEmailVerificationMutation.mutate()}
          disabled={requestEmailVerificationMutation.isPending || !emailMethod}
          className="ml-3 mt-5 rounded-lg bg-[var(--control-bg)] min-h-10 px-4 py-2 text-sm font-medium text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--control-bg-hover)] disabled:opacity-50"
        >
          {requestEmailVerificationMutation.isPending ? t('common.states.loading') : t('profile.email.verificationAction')}
        </button>
        {emailVerificationUrl ? (
          <label className="mt-4 block space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">{t('profile.email.verificationLinkLabel')}</span>
            <textarea
              readOnly
              value={emailVerificationUrl}
              className="min-h-20 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm leading-relaxed shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
            />
          </label>
        ) : null}
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">{t('profile.password.currentLabel')}</span>
            <input
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              className="w-full rounded-lg bg-[var(--control-bg)] min-h-10 px-3 py-2 text-sm shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">{t('profile.password.newLabel')}</span>
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              className="w-full rounded-lg bg-[var(--control-bg)] min-h-10 px-3 py-2 text-sm shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
            />
          </label>
        </div>
        <button
          onClick={() => changePasswordMutation.mutate()}
          disabled={changePasswordMutation.isPending}
          className="mt-5 rounded-lg bg-[var(--control-bg)] min-h-10 px-4 py-2 text-sm font-medium text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--control-bg-hover)] disabled:opacity-50"
        >
          {changePasswordMutation.isPending ? t('common.states.saving') : t('profile.password.updateAction')}
        </button>
      </section>

      {showGoogleAuth ? (
        <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
          <h2 className="mb-2 text-lg font-semibold leading-tight text-[var(--text-primary)]">{t('profile.google.title')}</h2>
          <p className="mb-4 text-sm text-[var(--text-muted)]">
            {t('profile.google.description')}
          </p>
          <div className="mb-4">
            <GoogleAuthButton
              text="continue_with"
              onCredential={(idToken) => linkGoogleMutation.mutate(idToken)}
              onError={(message) => toast.error(message)}
            />
          </div>
          <div className="text-sm text-[var(--text-muted)]">
            {t('profile.google.afterSuccess')}
          </div>
        </section>
      ) : null}
    </div>
  );
};
