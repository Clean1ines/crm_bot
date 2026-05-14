import toast from 'react-hot-toast';

import { t } from '../../i18n';

declare global {
  interface Window {
    __lastToast: string | null;
  }
}

const DEFAULT_ERROR_MESSAGE = t('api.error.default');
const TECHNICAL_ERROR_MESSAGE = t('api.error.technical');
const VALIDATION_ERROR_MESSAGE = t('api.error.validation');
const NETWORK_ERROR_MESSAGE = t('api.error.network');
const MAX_VISIBLE_ERROR_LENGTH = 280;

const FRIENDLY_ERROR_BY_NORMALIZED_MESSAGE: Record<string, string> = {
  'project is not selected': t('api.error.projectNotSelected'),
  'no thread id': t('api.error.threadNotDetected'),
  'no response body': t('api.error.emptyResponse'),
  'auth response does not contain access token': t('api.error.authMissingToken'),
  'failed to fetch': NETWORK_ERROR_MESSAGE,
  'networkerror': NETWORK_ERROR_MESSAGE,
  'network error': NETWORK_ERROR_MESSAGE,
  'internal server error': TECHNICAL_ERROR_MESSAGE,
  '[object object]': DEFAULT_ERROR_MESSAGE,
};

const TECHNICAL_ERROR_PATTERNS = [
  /\bduplicate key value\b/i,
  /\bviolates unique constraint\b/i,
  /\bviolates foreign key constraint\b/i,
  /\bforeign key constraint\b/i,
  /\bnot-null constraint\b/i,
  /\bnull value in column\b/i,
  /\bDETAIL:\b/i,
  /\bKey \([^)]+\)=/i,
  /\bSQLSTATE\b/i,
  /\b(asyncpg|psycopg|sqlalchemy)\b/i,
  /\b(IntegrityError|ProgrammingError|OperationalError|DatabaseError)\b/i,
  /\bTraceback \(most recent call last\):/i,
  /\bFile "[^"]+", line \d+/i,
  /\bHTTP 5\d\d\b/i,
  /\bInternal Server Error\b/i,
  /\/(home|app|usr|var)\/[^\s]+/i,
  /\.(py|ts|tsx|js):\d+:\d+/i,
];

const normalizeWhitespace = (value: string): string => (
  value.replace(/\s+/g, ' ').trim()
);

const stripErrorPrefix = (value: string): string => (
  value.replace(/^Error:\s*/i, '').trim()
);

const isRecord = (value: unknown): value is Record<string, unknown> => (
  value !== null && typeof value === 'object' && !Array.isArray(value)
);

export const isTechnicalErrorMessage = (message: string): boolean => (
  TECHNICAL_ERROR_PATTERNS.some((pattern) => pattern.test(message))
);

export const sanitizeErrorMessage = (
  message: unknown,
  fallback = DEFAULT_ERROR_MESSAGE,
): string => {
  if (typeof message !== 'string') {
    return fallback;
  }

  const normalized = stripErrorPrefix(normalizeWhitespace(message));
  if (!normalized) {
    return fallback;
  }

  const friendlyOverride = FRIENDLY_ERROR_BY_NORMALIZED_MESSAGE[normalized.toLowerCase()];
  if (friendlyOverride) {
    return friendlyOverride;
  }

  if (isTechnicalErrorMessage(normalized)) {
    return TECHNICAL_ERROR_MESSAGE;
  }

  if (normalized.length > MAX_VISIBLE_ERROR_LENGTH) {
    return `${normalized.slice(0, MAX_VISIBLE_ERROR_LENGTH).trim()}…`;
  }

  return normalized;
};

const getValidationDetailMessage = (detail: unknown): string | null => {
  if (!Array.isArray(detail)) {
    return null;
  }

  const message = detail
    .map((item) => (isRecord(item) && typeof item.msg === 'string' ? item.msg : ''))
    .filter(Boolean)
    .join(', ');

  if (!message) {
    return VALIDATION_ERROR_MESSAGE;
  }

  if (isTechnicalErrorMessage(message)) {
    return TECHNICAL_ERROR_MESSAGE;
  }

  return VALIDATION_ERROR_MESSAGE;
};

export const getErrorMessage = (
  error: unknown,
  fallback = DEFAULT_ERROR_MESSAGE,
): string => {
  if (typeof error === 'string') {
    return sanitizeErrorMessage(error, fallback);
  }

  if (isRecord(error)) {
    const detail = error.detail;
    if (typeof detail === 'string') {
      return sanitizeErrorMessage(detail, fallback);
    }

    const validationDetail = getValidationDetailMessage(detail);
    if (validationDetail) {
      return validationDetail;
    }

    const errorText = error.error;
    if (typeof errorText === 'string') {
      return sanitizeErrorMessage(errorText, fallback);
    }

    const message = error.message;
    if (typeof message === 'string') {
      return sanitizeErrorMessage(message, fallback);
    }
  }

  if (error instanceof Error) {
    return sanitizeErrorMessage(error.message, fallback);
  }

  return fallback;
};

export const showErrorToast = (message: string): void => {
  const safeMessage = sanitizeErrorMessage(message);
  const key = `error-${safeMessage}`;

  if (typeof window === 'undefined') {
    toast.error(safeMessage);
    return;
  }

  if (window.__lastToast === key) return;

  window.__lastToast = key;
  setTimeout(() => {
    window.__lastToast = null;
  }, 1000);

  toast.error(safeMessage);
};
