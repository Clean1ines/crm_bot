import React, { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

import { useProjectConfiguration } from '@entities/project/api/useCrmData';
import { api, getErrorMessage } from '@shared/api/client';

export const ProjectSettingsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const { data: configuration, isLoading } = useProjectConfiguration(projectId);

  const [brandName, setBrandName] = useState('');
  const [toneOfVoice, setToneOfVoice] = useState('');
  const [defaultLanguage, setDefaultLanguage] = useState('');
  const [defaultTimezone, setDefaultTimezone] = useState('');
  const [requestsPerMinute, setRequestsPerMinute] = useState('');
  const [fallbackModel, setFallbackModel] = useState('');
  const [integrationProvider, setIntegrationProvider] = useState('custom_webhook');
  const [integrationUrl, setIntegrationUrl] = useState('');
  const [widgetOrigin, setWidgetOrigin] = useState('');

  useEffect(() => {
    const settings = configuration?.settings || {};
    const limits = configuration?.limit_profile || {};
    const widgetChannel = configuration?.channels.find((channel) => (
      channel.kind === 'widget' && channel.provider === 'web'
    ));
    const widgetConfig = widgetChannel?.config_json && typeof widgetChannel.config_json === 'object'
      ? widgetChannel.config_json as Record<string, unknown>
      : {};
    setBrandName(String(settings.brand_name ?? ''));
    setToneOfVoice(String(settings.tone_of_voice ?? ''));
    setDefaultLanguage(String(settings.default_language ?? ''));
    setDefaultTimezone(String(settings.default_timezone ?? ''));
    setRequestsPerMinute(limits.requests_per_minute == null ? '' : String(limits.requests_per_minute));
    setFallbackModel(String(limits.fallback_model ?? ''));
    setWidgetOrigin(String(widgetConfig.allowed_origin ?? ''));
  }, [configuration]);

  const invalidateConfiguration = async () => {
    await queryClient.invalidateQueries({ queryKey: ['project-configuration', projectId] });
  };

  const saveSettingsMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error('Project is not selected');
      await api.projects.updateSettings(projectId, {
        brand_name: brandName || undefined,
        tone_of_voice: toneOfVoice || undefined,
        default_language: defaultLanguage || undefined,
        default_timezone: defaultTimezone || undefined,
      });
      await api.projects.updateLimits(projectId, {
        requests_per_minute: requestsPerMinute ? Number(requestsPerMinute) : undefined,
        fallback_model: fallbackModel || undefined,
      });
    },
    onSuccess: async () => {
      await invalidateConfiguration();
      toast.success('Настройки проекта сохранены');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const saveIntegrationMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error('Project is not selected');
      if (!integrationProvider.trim()) throw new Error('Укажите provider интеграции');
      await api.projects.upsertIntegration(projectId, {
        provider: integrationProvider.trim(),
        status: integrationUrl.trim() ? 'enabled' : 'disabled',
        config_json: integrationUrl.trim() ? { url: integrationUrl.trim() } : {},
      });
    },
    onSuccess: async () => {
      await invalidateConfiguration();
      toast.success('Интеграция сохранена');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const saveWidgetChannelMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error('Project is not selected');
      await api.projects.upsertChannel(projectId, {
        kind: 'widget',
        provider: 'web',
        status: widgetOrigin.trim() ? 'active' : 'disabled',
        config_json: widgetOrigin.trim() ? { allowed_origin: widgetOrigin.trim() } : {},
      });
    },
    onSuccess: async () => {
      await invalidateConfiguration();
      toast.success('Канал веб-виджета сохранен');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  if (isLoading) {
    return <div className="p-8 text-[var(--text-muted)]">Загрузка настроек...</div>;
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-8">
      <div>
        <h1 className="text-3xl font-semibold text-[var(--text-primary)]">Настройки проекта</h1>
        <p className="mt-2 text-sm text-[var(--text-muted)]">
          Персонализация ассистента, операционные лимиты и внешние подключения проекта.
        </p>
      </div>

      <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-card)] p-6 shadow-sm">
        <h2 className="mb-4 text-xl font-medium text-[var(--text-primary)]">Персонализация</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Бренд</span>
            <input
              value={brandName}
              onChange={(event) => setBrandName(event.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Tone of voice</span>
            <input
              value={toneOfVoice}
              onChange={(event) => setToneOfVoice(event.target.value)}
              placeholder="friendly, expert, concise"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Язык по умолчанию</span>
            <input
              value={defaultLanguage}
              onChange={(event) => setDefaultLanguage(event.target.value)}
              placeholder="ru"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Timezone</span>
            <input
              value={defaultTimezone}
              onChange={(event) => setDefaultTimezone(event.target.value)}
              placeholder="Europe/Moscow"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
        </div>
      </section>

      <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-card)] p-6 shadow-sm">
        <h2 className="mb-4 text-xl font-medium text-[var(--text-primary)]">Лимиты</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Requests per minute</span>
            <input
              type="number"
              value={requestsPerMinute}
              onChange={(event) => setRequestsPerMinute(event.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Fallback model</span>
            <input
              value={fallbackModel}
              onChange={(event) => setFallbackModel(event.target.value)}
              placeholder="llama-3.1-8b-instant"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
        </div>
        <button
          onClick={() => saveSettingsMutation.mutate()}
          disabled={saveSettingsMutation.isPending}
          className="mt-5 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {saveSettingsMutation.isPending ? 'Сохранение...' : 'Сохранить настройки'}
        </button>
      </section>

      <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-card)] p-6 shadow-sm">
        <h2 className="mb-4 text-xl font-medium text-[var(--text-primary)]">Интеграции</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Provider</span>
            <input
              value={integrationProvider}
              onChange={(event) => setIntegrationProvider(event.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Webhook URL</span>
            <input
              value={integrationUrl}
              onChange={(event) => setIntegrationUrl(event.target.value)}
              placeholder="https://example.com/webhook"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
        </div>
        <button
          onClick={() => saveIntegrationMutation.mutate()}
          disabled={saveIntegrationMutation.isPending}
          className="mt-5 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {saveIntegrationMutation.isPending ? 'Сохранение...' : 'Сохранить интеграцию'}
        </button>
      </section>

      <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-card)] p-6 shadow-sm">
        <h2 className="mb-4 text-xl font-medium text-[var(--text-primary)]">Каналы проекта</h2>
        <p className="mb-4 text-sm text-[var(--text-muted)]">
          Канал описывает поверхность входа в проект: Telegram-бот клиента, бот менеджера,
          платформенный бот или веб-виджет. Роли людей при этом остаются в участниках проекта.
        </p>
        <label className="block max-w-xl space-y-1 text-sm">
          <span className="text-[var(--text-muted)]">Allowed origin для веб-виджета</span>
          <input
            value={widgetOrigin}
            onChange={(event) => setWidgetOrigin(event.target.value)}
            placeholder="https://client-site.example"
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
          />
        </label>
        <button
          onClick={() => saveWidgetChannelMutation.mutate()}
          disabled={saveWidgetChannelMutation.isPending}
          className="mt-5 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {saveWidgetChannelMutation.isPending ? 'Сохранение...' : 'Сохранить канал виджета'}
        </button>
        {configuration?.channels?.length ? (
          <div className="mt-5 overflow-hidden rounded-lg border border-[var(--border-subtle)]">
            {configuration.channels.map((channel, index) => (
              <div
                key={`${channel.kind}-${channel.provider}-${index}`}
                className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3 last:border-b-0"
              >
                <div>
                  <div className="font-medium text-[var(--text-primary)]">
                    {String(channel.kind)} / {String(channel.provider)}
                  </div>
                  <div className="text-xs text-[var(--text-muted)]">{String(channel.status ?? 'disabled')}</div>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
};
