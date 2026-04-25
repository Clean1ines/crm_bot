import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';

import { api, getErrorMessage } from '@shared/api/client';
import { GoogleAuthButton } from '@features/auth/google/GoogleAuthButton';

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

export const ProfilePage: React.FC = () => {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [emailVerificationUrl, setEmailVerificationUrl] = useState('');

  const methodsQuery = useQuery<AuthMethodsResponse>({
    queryKey: ['auth-methods'],
    queryFn: async () => {
      const result = await api.auth.methods();
      return result.data as AuthMethodsResponse;
    },
  });

  useEffect(() => {
    const emailMethod = methodsQuery.data?.methods.find((method) => method.provider === 'email');
    if (emailMethod?.provider_id) {
      setEmail(emailMethod.provider_id);
    }
  }, [methodsQuery.data]);

  const emailMethod = methodsQuery.data?.methods.find((method) => method.provider === 'email');

  const linkEmailMutation = useMutation({
    mutationFn: async () => {
      if (!email.trim()) throw new Error('Укажите email');
      if (!password.trim()) throw new Error('Придумайте пароль для email-входа');
      await api.auth.linkEmail({ email: email.trim(), password });
    },
    onSuccess: async () => {
      setPassword('');
      setEmailVerificationUrl('');
      await queryClient.invalidateQueries({ queryKey: ['auth-methods'] });
      toast.success('Email-вход привязан');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const linkGoogleMutation = useMutation({
    mutationFn: async (idToken: string) => {
      await api.auth.linkGoogleWithIdToken({ id_token: idToken });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth-methods'] });
      toast.success('Google-вход привязан');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const changePasswordMutation = useMutation({
    mutationFn: async () => {
      if (!newPassword.trim()) throw new Error('Укажите новый пароль');
      await api.auth.changePassword({
        new_password: newPassword,
        current_password: currentPassword.trim() || undefined,
      });
    },
    onSuccess: async () => {
      setCurrentPassword('');
      setNewPassword('');
      await queryClient.invalidateQueries({ queryKey: ['auth-methods'] });
      toast.success('Пароль обновлен');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const requestEmailVerificationMutation = useMutation({
    mutationFn: async () => {
      const result = await api.auth.requestEmailVerification();
      return result.data as { url?: string | null; token?: string | null };
    },
    onSuccess: async (data) => {
      setEmailVerificationUrl(data.url || data.token || '');
      await queryClient.invalidateQueries({ queryKey: ['auth-methods'] });
      toast.success('Ссылка подтверждения подготовлена');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const unlinkMethodMutation = useMutation({
    mutationFn: async (provider: 'telegram' | 'email' | 'google') => {
      await api.auth.unlinkMethod(provider);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth-methods'] });
      toast.success('Способ входа отвязан');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  return (
    <div className="mx-auto max-w-4xl space-y-8 p-8">
      <div>
        <h1 className="text-3xl font-semibold text-[var(--text-primary)]">Профиль</h1>
        <p className="mt-2 text-sm text-[var(--text-muted)]">
          Управление способами входа в платформу. Telegram, email и Google должны вести к одному platform user.
        </p>
      </div>

      <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-card)] p-6 shadow-sm">
        <h2 className="mb-4 text-xl font-medium text-[var(--text-primary)]">Подключенные способы входа</h2>
        {methodsQuery.isLoading ? (
          <div className="text-sm text-[var(--text-muted)]">Загрузка...</div>
        ) : (
          <div className="space-y-2">
            {methodsQuery.data?.methods.map((method) => (
              <div
                key={`${method.provider}-${method.provider_id}`}
                className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-white px-4 py-3"
              >
                <div>
                  <div className="font-medium text-[var(--text-primary)]">{method.provider}</div>
                  <div className="text-xs text-[var(--text-muted)]">{method.provider_id}</div>
                </div>
                <button
                  type="button"
                  onClick={() => unlinkMethodMutation.mutate(method.provider as 'telegram' | 'email' | 'google')}
                  disabled={unlinkMethodMutation.isPending}
                  className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-xs font-medium text-[var(--text-primary)] disabled:opacity-50"
                >
                  Отвязать
                </button>
              </div>
            ))}
            {methodsQuery.data?.methods.length === 0 ? (
              <div className="text-sm text-[var(--text-muted)]">Способы входа еще не привязаны.</div>
            ) : null}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-card)] p-6 shadow-sm">
        <h2 className="mb-4 text-xl font-medium text-[var(--text-primary)]">Email-вход</h2>
        <div className="mb-4 rounded-lg border border-[var(--border-subtle)] bg-white px-4 py-3 text-sm text-[var(--text-primary)]">
          Статус email:
          {' '}
          <span className={emailMethod?.verified ? 'text-emerald-600' : 'text-amber-600'}>
            {emailMethod?.verified ? 'подтвержден' : 'не подтвержден'}
          </span>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Email</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Новый пароль для email-входа</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
        </div>
        <button
          onClick={() => linkEmailMutation.mutate()}
          disabled={linkEmailMutation.isPending}
          className="mt-5 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {linkEmailMutation.isPending ? 'Сохранение...' : 'Привязать email'}
        </button>
        <button
          onClick={() => requestEmailVerificationMutation.mutate()}
          disabled={requestEmailVerificationMutation.isPending || !emailMethod}
          className="ml-3 mt-5 rounded-lg border border-[var(--border-subtle)] bg-white px-4 py-2 text-sm font-medium text-[var(--text-primary)] disabled:opacity-50"
        >
          {requestEmailVerificationMutation.isPending ? 'Подготовка...' : 'Получить ссылку подтверждения'}
        </button>
        {emailVerificationUrl ? (
          <label className="mt-4 block space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Ссылка подтверждения</span>
            <textarea
              readOnly
              value={emailVerificationUrl}
              className="min-h-20 w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
        ) : null}
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Текущий пароль</span>
            <input
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Новый пароль</span>
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
        </div>
        <button
          onClick={() => changePasswordMutation.mutate()}
          disabled={changePasswordMutation.isPending}
          className="mt-5 rounded-lg border border-[var(--border-subtle)] bg-white px-4 py-2 text-sm font-medium text-[var(--text-primary)] disabled:opacity-50"
        >
          {changePasswordMutation.isPending ? 'Сохранение...' : 'Обновить пароль'}
        </button>
      </section>

      <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-card)] p-6 shadow-sm">
        <h2 className="mb-2 text-xl font-medium text-[var(--text-primary)]">Google-вход</h2>
        <p className="mb-4 text-sm text-[var(--text-muted)]">
          Google привязывается через официальный Google Identity Services flow и проверяется на backend по ID token.
        </p>
        <div className="mb-4">
          <GoogleAuthButton
            text="continue_with"
            onCredential={(idToken) => linkGoogleMutation.mutate(idToken)}
            onError={(message) => toast.error(message)}
          />
        </div>
        <div className="text-sm text-[var(--text-muted)]">
          После успешного выбора аккаунта Google способ входа сразу появится в списке подключенных методов.
        </div>
      </section>
    </div>
  );
};
