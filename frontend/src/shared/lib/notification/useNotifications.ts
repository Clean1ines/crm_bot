// frontend/src/hooks/useNotifications.ts
import { useCallback } from 'react';
import { create } from 'zustand';
import { TimeoutError } from '@shared/api';

interface Notification {
  id: number;
  message: string;
  type: 'info' | 'error' | 'success';
}

interface NotificationStore {
  notifications: Notification[];
  addNotification: (message: string, type: 'info' | 'error' | 'success') => void;
  removeNotification: (id: number) => void;
}

const useNotificationStore = create<NotificationStore>((set) => ({
  notifications: [],
  addNotification: (message, type) => {
    const id = Date.now();
    set((state) => ({ notifications: [...state.notifications, { id, message, type }] }));
    setTimeout(() => {
      set((state) => ({ notifications: state.notifications.filter(n => n.id !== id) }));
    }, 5000); // #CHANGED: 3000 → 5000 for timeout messages
  },
  removeNotification: (id) => set((state) => ({ notifications: state.notifications.filter(n => n.id !== id) })),
}));

export const useNotification = () => {
  const addNotification = useNotificationStore((s) => s.addNotification);
  
  const showNotification = useCallback((message: string, type: 'info' | 'error' | 'success' = 'info') => {
    addNotification(message, type);
  }, [addNotification]);

  // #ADDED: Helper for API errors with timeout handling
  const showApiError = useCallback((error: unknown, defaultMessage: string = 'Ошибка запроса') => {
    if (error instanceof TimeoutError) {
      showNotification('⏱️ Превышено время ожидания ответа сервера (30s)', 'error');
    } else if (error instanceof Error) {
      showNotification(`${defaultMessage}: ${error.message}`, 'error');
    } else {
      showNotification(defaultMessage, 'error');
    }
  }, [showNotification]);

  return { showNotification, showApiError };
};

export { useNotificationStore };