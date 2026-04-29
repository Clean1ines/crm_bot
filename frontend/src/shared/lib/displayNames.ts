export type DisplayNameLike = {
  display_name?: string | null;
  full_name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  username?: string | null;
  email?: string | null;
};

const normalizeText = (value?: string | null): string | null => {
  const normalized = value?.trim();
  if (!normalized) return null;

  const lowered = normalized.toLowerCase();
  if (lowered === 'none' || lowered === 'null' || lowered === 'undefined') {
    return null;
  }

  return normalized;
};

const normalizeUsername = (username?: string | null): string | null => {
  const value = normalizeText(username);
  if (!value) return null;
  return value.startsWith('@') ? value : `@${value}`;
};

const joinNameParts = (
  firstName?: string | null,
  lastName?: string | null,
): string | null => {
  const parts = [normalizeText(firstName), normalizeText(lastName)].filter(
    (part): part is string => Boolean(part),
  );

  return parts.length ? parts.join(' ') : null;
};

export const getDisplayName = (
  entity?: DisplayNameLike | null,
  fallback = 'Клиент',
): string => {
  return (
    normalizeText(entity?.display_name) ||
    normalizeText(entity?.full_name) ||
    joinNameParts(entity?.first_name, entity?.last_name) ||
    normalizeUsername(entity?.username) ||
    normalizeText(entity?.email) ||
    fallback
  );
};

export const getSecondaryDisplayText = (
  entity?: DisplayNameLike | null,
): string | null => {
  const primary = getDisplayName(entity, '');
  const username = normalizeUsername(entity?.username);
  const fullName = normalizeText(entity?.full_name);
  const email = normalizeText(entity?.email);

  if (primary && username && primary !== username) return username;
  if (primary && fullName && primary !== fullName) return fullName;
  if (primary && email && primary !== email) return email;
  return null;
};

export const getDisplayInitials = (
  entity?: DisplayNameLike | null,
  fallback = 'Клиент',
): string => {
  const label = getDisplayName(entity, fallback).replace(/^@/, '');
  const parts = label.split(/\s+/).filter(Boolean);

  if (parts.length === 0) return fallback.slice(0, 2).toUpperCase();
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();

  return `${parts[0][0] ?? ''}${parts[1][0] ?? ''}`.toUpperCase();
};
