import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

import { useProjectConfiguration } from '@entities/project/api/useCrmData';
import { getErrorMessage } from '@shared/api/core/errors';
import { projectsApi } from '@shared/api/modules/projects';

type SettingsDraft = {
  brandName?: string;
  toneOfVoice?: string;
  defaultLanguage?: string;
  defaultTimezone?: string;
  requestsPerMinute?: string;
  fallbackModel?: string;
  integrationProvider?: string;
  integrationUrl?: string;
  widgetOrigin?: string;
};

const getConfigObject = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
);

export const ProjectSettingsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const { data: configuration, isLoading, isError, error } = useProjectConfiguration(projectId);

  const [draft, setDraft] = useState<SettingsDraft>({});

  const settings = getConfigObject(configuration?.settings);
  const limits = getConfigObject(configuration?.limit_profile);
  const channels = Array.isArray(configuration?.channels) ? configuration.channels : [];
  const widgetChannel = channels.find((channel) => (
    channel.kind === 'widget' && channel.provider === 'web'
  ));
  const widgetConfig = getConfigObject(widgetChannel?.config_json);

  const brandName = draft.brandName ?? String(settings.brand_name ?? '');
  const toneOfVoice = draft.toneOfVoice ?? String(settings.tone_of_voice ?? '');
  const defaultLanguage = draft.defaultLanguage ?? String(settings.default_language ?? '');
  const defaultTimezone = draft.defaultTimezone ?? String(settings.default_timezone ?? '');
  const requestsPerMinute = draft.requestsPerMinute
    ?? (limits.requests_per_minute == null ? '' : String(limits.requests_per_minute));
  const fallbackModel = draft.fallbackModel ?? String(limits.fallback_model ?? '');
  const integrationProvider = draft.integrationProvider ?? 'custom_webhook';
  const integrationUrl = draft.integrationUrl ?? '';
  const widgetOrigin = draft.widgetOrigin ?? String(widgetConfig.allowed_origin ?? '');

  const updateDraft = (patch: SettingsDraft) => {
    setDraft((current) => ({ ...current, ...patch }));
  };

  const invalidateConfiguration = async () => {
    await queryClient.invalidateQueries({ queryKey: ['project-configuration', projectId] });
  };

  const saveSettingsMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error('Project is not selected');
      await projectsApi.updateSettings(projectId, {
        brand_name: brandName || undefined,
        tone_of_voice: toneOfVoice || undefined,
        default_language: defaultLanguage || undefined,
        default_timezone: defaultTimezone || undefined,
      });
      await projectsApi.updateLimits(projectId, {
        requests_per_minute: requestsPerMinute ? Number(requestsPerMinute) : undefined,
        fallback_model: fallbackModel || undefined,
      });
    },
    onSuccess: async () => {
      await invalidateConfiguration();
      setDraft({});
      toast.success('Настройки проекта сохранены');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const saveIntegrationMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error('Project is not selected');
      if (!integrationProvider.trim()) throw new Error('Укажите поставщика интеграции');
      await projectsApi.upsertIntegration(projectId, {
        provider: integrationProvider.trim(),
        status: integrationUrl.trim() ? 'enabled' : 'disabled',
        config_json: integrationUrl.trim() ? { url: integrationUrl.trim() } : {},
      });
    },
    onSuccess: async () => {
      await invalidateConfiguration();
      setDraft((current) => ({ ...current, integrationUrl: '' }));
      toast.success('Интеграция сохранена');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const saveWidgetChannelMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error('Project is not selected');
      await projectsApi.upsertChannel(projectId, {
        kind: 'widget',
        provider: 'web',
        status: widgetOrigin.trim() ? 'active' : 'disabled',
        config_json: widgetOrigin.trim() ? { allowed_origin: widgetOrigin.trim() } : {},
      });
    },
    onSuccess: async () => {
      await invalidateConfiguration();
      setDraft((current) => ({ ...current, widgetOrigin: undefined }));
      toast.success('Канал веб-виджета сохранен');
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  if (isLoading) {
    return <div className="p-8 text-[var(--text-muted)]">Загрузка настроек...</div>;
  }

  if (isError) {
    return (
      <div className="p-8 text-[var(--text-muted)]">
        Не удалось загрузить настройки проекта: {getErrorMessage(error)}
      </div>
    );
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
              onChange={(event) => updateDraft({ brandName: event.target.value })}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Стиль общения</span>
            <input
              value={toneOfVoice}
              onChange={(event) => updateDraft({ toneOfVoice: event.target.value })}
              placeholder="friendly, expert, concise"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Язык по умолчанию</span>
            <input
              value={defaultLanguage}
              onChange={(event) => updateDraft({ defaultLanguage: event.target.value })}
              placeholder="ru"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Timezone</span>
            <input
              value={defaultTimezone}
              onChange={(event) => updateDraft({ defaultTimezone: event.target.value })}
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
            <span className="text-[var(--text-muted)]">Запросов в минуту</span>
            <input
              type="number"
              value={requestsPerMinute}
              onChange={(event) => updateDraft({ requestsPerMinute: event.target.value })}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Резервная модель</span>
            <input
              value={fallbackModel}
              onChange={(event) => updateDraft({ fallbackModel: event.target.value })}
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
            <span className="text-[var(--text-muted)]">Поставщик</span>
            <input
              value={integrationProvider}
              onChange={(event) => updateDraft({ integrationProvider: event.target.value })}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-white px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Адрес webhook</span>
            <input
              value={integrationUrl}
              onChange={(event) => updateDraft({ integrationUrl: event.target.value })}
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
          Каналы определяют, где клиенты и менеджеры взаимодействуют с проектом: Telegram-боты, платформенный бот или веб-виджет.
        </p>
        <label className="block max-w-xl space-y-1 text-sm">
          <span className="text-[var(--text-muted)]">Разрешённый сайт для веб-виджета</span>
          <input
            value={widgetOrigin}
            onChange={(event) => updateDraft({ widgetOrigin: event.target.value })}
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
        {channels.length ? (
          <div className="mt-5 overflow-hidden rounded-lg border border-[var(--border-subtle)]">
            {channels.map((channel, index) => (
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
