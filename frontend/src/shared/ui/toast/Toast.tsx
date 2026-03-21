import { Toaster } from 'react-hot-toast';

/**
 * Toast component for displaying notifications.
 * Wraps react-hot-toast Toaster with default configuration.
 */
export const Toast: React.FC = () => {
  return (
    <Toaster
      position="top-right"
      toastOptions={{
        duration: 5000,
        error: {
          duration: 7000,
        },
      }}
    />
  );
};
