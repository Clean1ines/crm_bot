const VISITOR_STORAGE_PREFIX = 'crm_bot_widget_visitor';

const createVisitorId = (): string => (
  window.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
);

export const getVisitorStorageKey = (projectId: string | null | undefined): string => (
  `${VISITOR_STORAGE_PREFIX}:${projectId ?? 'unknown'}`
);

export const getOrCreateVisitorId = (projectId: string | null | undefined): string => {
  const key = getVisitorStorageKey(projectId);
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;

  const next = createVisitorId();
  window.localStorage.setItem(key, next);
  return next;
};
