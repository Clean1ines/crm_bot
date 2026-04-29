import {
  getDisplayInitials,
  getDisplayName,
  getSecondaryDisplayText,
  type DisplayNameLike,
} from './displayNames';

type ClientLike = DisplayNameLike & {
  chat_id?: number | string | null;
};

export const getClientDisplayName = (client?: ClientLike | null, fallback = 'Клиент'): string => {
  return getDisplayName(client, fallback);
};

export const getClientSecondaryText = (client?: ClientLike | null): string | null => {
  return getSecondaryDisplayText(client);
};

export const getClientInitials = (client?: ClientLike | null): string => {
  return getDisplayInitials(client, 'Клиент');
};
