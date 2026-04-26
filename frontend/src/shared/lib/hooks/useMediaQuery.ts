import { useSyncExternalStore } from 'react';

/**
 * Hook for reactive media query matching
 * @param query - CSS media query string (e.g. '(max-width: 768px)')
 * @returns boolean indicating if the query matches
 */
export const useMediaQuery = (query: string): boolean => {
  const getSnapshot = () => window.matchMedia(query).matches;
  const getServerSnapshot = () => false;

  const subscribe = (onStoreChange: () => void) => {
    const media = window.matchMedia(query);
    media.addEventListener('change', onStoreChange);
    return () => media.removeEventListener('change', onStoreChange);
  };

  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
};
