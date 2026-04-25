type ClientLike = {
  username?: string | null;
  full_name?: string | null;
  first_name?: string | null;
};

const normalizeUsername = (username?: string | null): string | null => {
  const value = username?.trim();
  if (!value) return null;
  return value.startsWith('@') ? value : `@${value}`;
};

export const getClientDisplayName = (client?: ClientLike | null, fallback = 'Клиент'): string => {
  const username = normalizeUsername(client?.username);
  if (username) return username;

  const fullName = client?.full_name?.trim();
  if (fullName) return fullName;

  const firstName = client?.first_name?.trim();
  if (firstName) return firstName;

  return fallback;
};

export const getClientSecondaryText = (client?: ClientLike | null): string | null => {
  const fullName = client?.full_name?.trim();
  const username = normalizeUsername(client?.username);

  if (username && fullName) return fullName;
  return null;
};

export const getClientInitials = (client?: ClientLike | null): string => {
  const label = getClientDisplayName(client, 'Клиент').replace(/^@/, '');
  const parts = label.split(/\s+/).filter(Boolean);

  if (parts.length === 0) return 'CL';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();

  return `${parts[0][0] ?? ''}${parts[1][0] ?? ''}`.toUpperCase();
};
