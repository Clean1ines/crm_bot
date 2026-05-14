import { translate as t } from '../i18n';

export const roleLabel = (role?: string | null): string => {
  if (role === 'owner') return t('ui.role.owner');
  if (role === 'admin') return t('ui.role.admin');
  if (role === 'manager') return t('ui.role.manager');
  return role || t('ui.role.fallback');
};

export const authProviderLabel = (provider?: string | null): string => {
  if (provider === 'telegram') return 'Telegram';
  if (provider === 'email') return 'Email';
  if (provider === 'google') return 'Google';
  return provider || t('ui.authProvider.fallback');
};

export const threadStatusLabel = (status?: string | null): string => {
  if (status === 'active') return t('ui.threadStatus.active');
  if (status === 'waiting_manager') return t('ui.threadStatus.waitingManager');
  if (status === 'manual') return t('ui.threadStatus.manual');
  if (status === 'closed') return t('ui.threadStatus.closed');
  if (status === 'pending') return t('ui.jobStatus.pending');
  if (status === 'processing' || status === 'running') return t('ui.jobStatus.processing');
  if (status === 'paused') return t('ui.jobStatus.paused');
  if (status === 'completed' || status === 'done' || status === 'succeeded' || status === 'success') return t('ui.jobStatus.completed');
  if (status === 'cancelled') return t('ui.jobStatus.cancelled');
  if (status === 'failed' || status === 'error') return t('ui.jobStatus.failed');
  return status || t('ui.status.fallback');
};

export const channelKindLabel = (kind?: string | null): string => {
  if (kind === 'widget') return t('ui.channelKind.widget');
  if (kind === 'client_bot') return t('ui.channelKind.clientBot');
  if (kind === 'manager_bot') return t('ui.channelKind.managerBot');
  if (kind === 'platform_bot') return t('ui.channelKind.platformBot');
  return kind || t('ui.channelKind.fallback');
};

export const channelProviderLabel = (provider?: string | null): string => {
  if (provider === 'web') return t('ui.channelProvider.web');
  if (provider === 'telegram') return 'Telegram';
  if (provider === 'custom_webhook') return t('ui.integrationProvider.customWebhook');
  return provider || t('ui.channelProvider.fallback');
};

export const channelStatusLabel = (status?: string | null): string => {
  if (status === 'active' || status === 'enabled') return t('ui.channelStatus.active');
  if (status === 'disabled') return t('ui.channelStatus.disabled');
  if (status === 'pending') return t('ui.channelStatus.pending');
  if (status === 'error') return t('ui.channelStatus.error');
  return status || t('ui.status.fallback');
};

export const integrationProviderLabel = (provider?: string | null): string => {
  if (provider === 'custom_webhook') return t('ui.integrationProvider.customWebhook');
  if (provider === 'webhook') return t('ui.integrationProvider.webhook');
  return provider || t('ui.integrationProvider.fallback');
};

export const knowledgeDocumentStatusLabel = (status?: string | null): string => {
  if (status === 'processed') return t('ui.knowledgeDocumentStatus.processed');
  if (status === 'processing') return t('ui.knowledgeDocumentStatus.processing');
  if (status === 'pending') return t('ui.knowledgeDocumentStatus.pending');
  if (status === 'cancelled') return t('ui.knowledgeDocumentStatus.cancelled');
  if (status === 'error' || status === 'failed') return t('ui.knowledgeDocumentStatus.failed');
  return status || t('ui.knowledgeDocumentStatus.fallback');
};
