// frontend/src/utils/logger.ts
// #ADDED: Structured logging utility for frontend with Render Log Drain support

/// <reference types="vite/client" />

interface LogEntry {
  timestamp: string;
  level: 'debug' | 'info' | 'warn' | 'error';
  message: string;
  correlation_id?: string;
  path?: string;
  user_agent?: string;
  error?: {
    name: string;
    message: string;
    stack?: string;
  };
  [key: string]: unknown;
}

// #CHANGED: Removed @ts-expect-error (vite/client provides types)
const getIsProduction = (): boolean => {
  return import.meta.env?.PROD === true;
};

// #ADDED: Extract correlation_id from response headers or generate new
// #CHANGED: Defensive check for document (tests/SSR)
const getCorrelationId = (): string => {
  // Check if we're in a browser environment
  if (typeof document === 'undefined') {
    return `client-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }
  // Try to get from meta tag (injected by backend)
  const meta = document.querySelector('meta[name="x-request-id"]');
  if (meta && meta instanceof HTMLMetaElement && meta.content) {
    return meta.content;
  }
  // Fallback: generate client-side ID
  return `client-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
};

// #ADDED: Send log entry to Render Log Drain (or console in dev)
const sendToLogDrain = async (entry: LogEntry): Promise<void> => {
  const isProduction = getIsProduction();

  // In development, log to console with structured output
  if (!isProduction) {
    const consoleMethod = console[entry.level] || console.log;
    consoleMethod(`[${entry.level.toUpperCase()}] ${entry.message}`, entry);
    return;
  }

  // In production, send to Render Log Drain endpoint
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);

  try {
    await fetch('/api/logs/frontend', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': entry.correlation_id || getCorrelationId(),
      },
      body: JSON.stringify(entry),
      signal: controller.signal,
      keepalive: true,
    });
  } catch (error) {
    console.warn('Failed to send log to drain:', error);
  } finally {
    clearTimeout(timeoutId);
  }
};

// #ADDED: Main logger interface
export const frontendLogger = {
  debug: (message: string, context?: Record<string, unknown>) => {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'debug',
      message,
      correlation_id: getCorrelationId(),
      path: typeof window !== 'undefined' ? window.location.pathname : '/test',
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : 'test-agent',
      ...context,
    };
    void sendToLogDrain(entry);
  },

  info: (message: string, context?: Record<string, unknown>) => {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'info',
      message,
      correlation_id: getCorrelationId(),
      path: typeof window !== 'undefined' ? window.location.pathname : '/test',
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : 'test-agent',
      ...context,
    };
    void sendToLogDrain(entry);
  },

  warn: (message: string, context?: Record<string, unknown>) => {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'warn',
      message,
      correlation_id: getCorrelationId(),
      path: typeof window !== 'undefined' ? window.location.pathname : '/test',
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : 'test-agent',
      ...context,
    };
    void sendToLogDrain(entry);
  },

  error: (message: string, error?: unknown, context?: Record<string, unknown>) => {
    const err = error instanceof Error
      ? { name: error.name, message: error.message, stack: error.stack }
      : { name: 'UnknownError', message: String(error) };

    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'error',
      message,
      correlation_id: getCorrelationId(),
      path: typeof window !== 'undefined' ? window.location.pathname : '/test',
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : 'test-agent',
      error: err,
      ...context,
    };
    void sendToLogDrain(entry);
  },

  registerGlobalHandlers: () => {
    // #CHANGED: Defensive check for window (tests/SSR)
    if (typeof window === 'undefined') return;

    window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
      frontendLogger.error('Unhandled promise rejection', event.reason, {
        rejection_type: event.reason?.constructor?.name,
      });
    });

    window.addEventListener('error', (event: ErrorEvent) => {
      frontendLogger.error('Uncaught error', event.error || event.message, {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      });
    });
  },
};

// #CHANGED: Only register in actual browser environment
if (typeof window !== 'undefined' && getIsProduction()) {
  frontendLogger.registerGlobalHandlers();
}

export default frontendLogger;
