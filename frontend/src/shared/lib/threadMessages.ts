import { t } from '../i18n';

import type { Client, Message } from '../../entities/thread/model/types';
import { getClientDisplayName } from './clients';

const MANAGER_PREFIX_PATTERN = /^\[([^\]\n]{1,80})\]:\s*(.+)$/s;

export type MessagePresentation = {
  content: string;
  label: string;
};

export const getMessagePresentation = (
  message: Message,
  client?: Client | null,
): MessagePresentation => {
  if (message.role === 'user') {
    return {
      content: message.content,
      label: getClientDisplayName(client, t('ui.sender.client')),
    };
  }

  if (message.role === 'assistant') {
    return {
      content: message.content,
      label: t('ui.sender.assistant'),
    };
  }

  if (message.role === 'manager') {
    const match = MANAGER_PREFIX_PATTERN.exec(message.content);
    if (match) {
      return {
        content: match[2],
        label: match[1],
      };
    }
    return {
      content: message.content,
      label: t('ui.sender.manager'),
    };
  }

  return {
    content: message.content,
    label: t('ui.sender.system'),
  };
};
