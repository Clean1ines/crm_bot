export const getGoogleClientId = (): string | undefined => {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
  return clientId?.trim() || undefined;
};

export const isGoogleAuthConfigured = (): boolean => {
  return Boolean(getGoogleClientId());
};
