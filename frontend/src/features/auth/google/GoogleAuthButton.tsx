import React, { useEffect, useRef, useState } from 'react';
import { t } from '@shared/i18n';

import { getGoogleClientId } from './config';

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (options: {
            client_id: string;
            callback: (response: { credential?: string }) => void;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: {
              theme?: 'outline' | 'filled_blue' | 'filled_black';
              size?: 'large' | 'medium' | 'small';
              text?: 'signin_with' | 'signup_with' | 'continue_with';
              shape?: 'rectangular' | 'pill' | 'circle' | 'square';
              width?: number;
            }
          ) => void;
        };
      };
    };
  }
}

const GOOGLE_SCRIPT_ID = 'google-identity-services';
const GOOGLE_SCRIPT_SRC = 'https://accounts.google.com/gsi/client';

function loadGoogleIdentityScript(): Promise<void> {
  if (window.google?.accounts?.id) {
    return Promise.resolve();
  }

  const existingScript = document.getElementById(GOOGLE_SCRIPT_ID) as HTMLScriptElement | null;
  if (existingScript) {
    return new Promise((resolve, reject) => {
      existingScript.addEventListener('load', () => resolve(), { once: true });
      existingScript.addEventListener('error', () => reject(new Error('Google Identity script failed to load')), { once: true });
    });
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.id = GOOGLE_SCRIPT_ID;
    script.src = GOOGLE_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Google Identity script failed to load'));
    document.head.appendChild(script);
  });
}

interface GoogleAuthButtonProps {
  text?: 'signin_with' | 'signup_with' | 'continue_with';
  onCredential: (idToken: string) => void | Promise<void>;
  onError?: (message: string) => void;
}

export const GoogleAuthButton: React.FC<GoogleAuthButtonProps> = ({
  text = 'continue_with',
  onCredential,
  onError,
}) => {
  const buttonRef = useRef<HTMLDivElement>(null);
  const onCredentialRef = useRef(onCredential);
  const onErrorRef = useRef(onError);
  const [status, setStatus] = useState<'ready' | 'failed'>('ready');
  const clientId = getGoogleClientId();

  useEffect(() => {
    onCredentialRef.current = onCredential;
    onErrorRef.current = onError;
  }, [onCredential, onError]);

  useEffect(() => {
    let cancelled = false;

    async function renderGoogleButton() {
      if (!clientId) {
        return;
      }

      try {
        await loadGoogleIdentityScript();
        if (cancelled || !buttonRef.current || !window.google?.accounts?.id) return;

        buttonRef.current.innerHTML = '';
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: (response) => {
            if (response.credential) {
              void onCredentialRef.current(response.credential);
              return;
            }
            onErrorRef.current?.(t('googleAuth.error.missingCredential'));
          },
        });
        window.google.accounts.id.renderButton(buttonRef.current, {
          theme: 'outline',
          size: 'large',
          text,
          shape: 'pill',
          width: 320,
        });
      } catch (error) {
        if (!cancelled) {
          setStatus('failed');
          onErrorRef.current?.(error instanceof Error ? error.message : t('googleAuth.error.loadFailed'));
        }
      }
    }

    void renderGoogleButton();

    return () => {
      cancelled = true;
    };
  }, [clientId, text]);

  if (status === 'failed') {
    return (
      <div className="rounded-xl bg-[var(--accent-danger-bg)] px-4 py-3 text-sm text-[var(--accent-danger-text)] shadow-[var(--shadow-sm)]">
        {t('googleAuth.error.identityServicesFailed')}
      </div>
    );
  }

  return <div ref={buttonRef} className="flex min-h-11 justify-center" />;
};
