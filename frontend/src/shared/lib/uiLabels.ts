export const roleLabel = (role?: string | null): string => {
  if (role === 'owner') return 'Владелец';
  if (role === 'admin') return 'Администратор';
  if (role === 'manager') return 'Менеджер';
  return role || 'Участник';
};

export const authProviderLabel = (provider?: string | null): string => {
  if (provider === 'telegram') return 'Telegram';
  if (provider === 'email') return 'Email';
  if (provider === 'google') return 'Google';
  return provider || 'Способ входа';
};

export const threadStatusLabel = (status?: string | null): string => {
  if (status === 'active') return 'Обрабатывает ассистент';
  if (status === 'waiting_manager') return 'Ждёт менеджера';
  if (status === 'manual') return 'В работе у менеджера';
  if (status === 'closed') return 'Закрыт';
  if (status === 'pending') return 'В очереди';
  if (status === 'processing' || status === 'running') return 'В работе';
  if (status === 'paused') return 'На паузе';
  if (status === 'completed' || status === 'done' || status === 'succeeded' || status === 'success') return 'Готово';
  if (status === 'cancelled') return 'Остановлено';
  if (status === 'failed' || status === 'error') return 'Ошибка';
  return status || 'Статус не указан';
};

export const channelKindLabel = (kind?: string | null): string => {
  if (kind === 'widget') return 'Веб-виджет';
  if (kind === 'client_bot') return 'Клиентский бот';
  if (kind === 'manager_bot') return 'Менеджерский бот';
  if (kind === 'platform_bot') return 'Платформенный бот';
  return kind || 'Канал';
};

export const channelProviderLabel = (provider?: string | null): string => {
  if (provider === 'web') return 'Сайт';
  if (provider === 'telegram') return 'Telegram';
  if (provider === 'custom_webhook') return 'Внешний обработчик';
  return provider || 'Подключение';
};

export const channelStatusLabel = (status?: string | null): string => {
  if (status === 'active' || status === 'enabled') return 'Активен';
  if (status === 'disabled') return 'Отключён';
  if (status === 'pending') return 'Ожидает настройки';
  if (status === 'error') return 'Требует внимания';
  return status || 'Статус не указан';
};

export const integrationProviderLabel = (provider?: string | null): string => {
  if (provider === 'custom_webhook') return 'Внешний обработчик';
  if (provider === 'webhook') return 'Внешний обработчик';
  return provider || 'Внешнее подключение';
};

export const knowledgeDocumentStatusLabel = (status?: string | null): string => {
  if (status === 'processed') return 'обработан';
  if (status === 'processing') return 'обрабатывается';
  if (status === 'pending') return 'ожидает обработки';
  if (status === 'cancelled') return 'остановлен';
  if (status === 'error' || status === 'failed') return 'не обработан';
  return status || 'статус не указан';
};
