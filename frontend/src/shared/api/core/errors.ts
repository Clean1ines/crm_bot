import toast from 'react-hot-toast';

declare global {
  interface Window {
    __lastToast: string | null;
  }
}

export const getErrorMessage = (error: unknown): string => {
  if (error && typeof error === 'object') {
    if ('detail' in error && typeof error.detail === 'string') return error.detail;
    if ('error' in error && typeof error.error === 'string') return error.error;

    if ('detail' in error && Array.isArray(error.detail)) {
      const details = error.detail as Array<{ msg?: string }>;
      const message = details.map((item) => item.msg).filter(Boolean).join(', ');
      if (message) return message;
    }

    if ('message' in error && typeof error.message === 'string') return error.message;
  }

  if (error instanceof Error) return error.message;

  return 'Произошла неизвестная ошибка';
};

export const showErrorToast = (message: string): void => {
  const key = `error-${message}`;

  if (window.__lastToast === key) return;

  window.__lastToast = key;
  setTimeout(() => {
    window.__lastToast = null;
  }, 1000);

  toast.error(message);
};
