import { t } from '@shared/i18n';
import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

import { useProjectConfiguration } from '@entities/project/api/useCrmData';
import { getErrorMessage } from '@shared/api/core/errors';
import { channelKindLabel, channelProviderLabel, channelStatusLabel } from '@shared/lib/uiLabels';
import { projectsApi } from '@shared/api/modules/projects';

type SettingsDraft = {
  brandName?: string;
  toneOfVoice?: string;
  defaultLanguage?: string;
  targetLanguage?: string;
  defaultTimezone?: string;
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
  const channels = Array.isArray(configuration?.channels) ? configuration.channels : [];
  const widgetChannel = channels.find((channel) => (
    channel.kind === 'widget' && channel.provider === 'web'
  ));
  const widgetConfig = getConfigObject(widgetChannel?.config_json);

  const brandName = draft.brandName ?? String(settings.brand_name ?? '');
  const toneOfVoice = draft.toneOfVoice ?? String(settings.tone_of_voice ?? '');
  const defaultLanguage = draft.defaultLanguage ?? String(settings.default_language ?? '');
  const targetLanguage = draft.targetLanguage ?? String(settings.target_language ?? defaultLanguage);
  const defaultTimezone = draft.defaultTimezone ?? String(settings.default_timezone ?? '');
  const widgetOrigin = draft.widgetOrigin ?? String(widgetConfig.allowed_origin ?? '');

  const updateDraft = (patch: SettingsDraft) => {
    setDraft((current) => ({ ...current, ...patch }));
  };

  const invalidateConfiguration = async () => {
    await queryClient.invalidateQueries({ queryKey: ['project-configuration', projectId] });
  };

  const saveWidgetChannelMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error(t('projectSettings.error.selectProject'));
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
      toast.success(t('projectSettings.feedback.widgetChannelSaved'));
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  if (isLoading) {
    return <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">{t('projectSettings.loading')}</div>;
  }

  if (isError) {
    return (
      <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">
        {t('projectSettings.loadFailed')}: {getErrorMessage(error)}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">{t('projectSettings.title')}</h1>
        <p className="mt-2 text-sm text-[var(--text-muted)]">
          {t('projectSettings.description')}
        </p>
      </div>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <h2 className="mb-4 text-lg font-semibold leading-tight text-[var(--text-primary)]">{t('projectSettings.personalization.title')}</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">{t('projectSettings.personalization.brand')}</span>
            <input
              value={brandName}
              onChange={(event) => updateDraft({ brandName: event.target.value })}
              className="w-full rounded-lg bg-[var(--control-bg)] min-h-10 px-3 py-2 text-sm shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">{t('projectSettings.personalization.tone')}</span>
            <input
              value={toneOfVoice}
              onChange={(event) => updateDraft({ toneOfVoice: event.target.value })}
              placeholder="friendly, expert, concise"
              className="w-full rounded-lg bg-[var(--control-bg)] min-h-10 px-3 py-2 text-sm shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">{t('projectSettings.personalization.defaultLanguage')}</span>
            <input
              value={defaultLanguage}
              onChange={(event) => updateDraft({ defaultLanguage: event.target.value })}
              placeholder="ru"
              className="w-full rounded-lg bg-[var(--control-bg)] min-h-10 px-3 py-2 text-sm shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">Target language (ru/en/de/es)</span>
            <input
              value={targetLanguage}
              onChange={(event) => updateDraft({ targetLanguage: event.target.value })}
              placeholder="ru"
              className="w-full rounded-lg bg-[var(--control-bg)] min-h-10 px-3 py-2 text-sm shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-[var(--text-muted)]">{t('projectSettings.personalization.timezone')}</span>
            <input
              value={defaultTimezone}
              onChange={(event) => updateDraft({ defaultTimezone: event.target.value })}
              placeholder="Europe/Moscow"
              className="w-full rounded-lg bg-[var(--control-bg)] min-h-10 px-3 py-2 text-sm shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
            />
          </label>
        </div>
      </section>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <h2 className="mb-4 text-lg font-semibold leading-tight text-[var(--text-primary)]">{t('projectSettings.channels.title')}</h2>
        <p className="mb-4 text-sm text-[var(--text-muted)]">
          {t('projectSettings.channels.description')}
        </p>
        <label className="block max-w-xl space-y-1 text-sm">
          <span className="text-[var(--text-muted)]">{t('projectSettings.channels.widgetAllowedOrigin')}</span>
          <input
            value={widgetOrigin}
            onChange={(event) => updateDraft({ widgetOrigin: event.target.value })}
            placeholder="https://client-site.example"
            className="w-full rounded-lg bg-[var(--control-bg)] min-h-10 px-3 py-2 text-sm shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
          />
        </label>
        <button
          onClick={() => saveWidgetChannelMutation.mutate()}
          disabled={saveWidgetChannelMutation.isPending}
          className="mt-5 rounded-lg bg-[var(--accent-primary)] min-h-10 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {saveWidgetChannelMutation.isPending ? t('common.states.saving') : t('projectSettings.actions.saveWidgetChannel')}
        </button>
        {channels.length ? (
          <div className="mt-5 overflow-hidden rounded-xl bg-[var(--control-bg)] shadow-[var(--shadow-sm)]">
            {channels.map((channel, index) => (
              <div
                key={`${channel.kind}-${channel.provider}-${index}`}
                className="flex items-center justify-between gap-3 px-4 py-3 shadow-[0_1px_0_var(--divider-soft)] last:shadow-none"
              >
                <div>
                  <div className="font-medium text-[var(--text-primary)]">
                    {channelKindLabel(String(channel.kind))} · {channelProviderLabel(String(channel.provider))}
                  </div>
                  <div className="text-xs text-[var(--text-muted)]">{channelStatusLabel(String(channel.status ?? 'disabled'))}</div>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
};
