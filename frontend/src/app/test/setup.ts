// frontend/src/app/test/setup.ts
import { vi, beforeEach, afterEach } from 'vitest';

const sessionStore = new Map<string, string>();

const mockSessionStorage: Storage = {
  get length(): number {
    return sessionStore.size;
  },
  clear: vi.fn((): void => {
    sessionStore.clear();
  }),
  getItem: vi.fn((key: string): string | null => sessionStore.get(key) ?? null),
  key: vi.fn((index: number): string | null => Array.from(sessionStore.keys())[index] ?? null),
  removeItem: vi.fn((key: string): void => {
    sessionStore.delete(key);
  }),
  setItem: vi.fn((key: string, value: string): void => {
    sessionStore.set(key, value);
  }),
};

Object.defineProperty(window, 'sessionStorage', {
  value: mockSessionStorage,
  writable: true,
  configurable: true,
});

Object.defineProperty(globalThis, 'import.meta', {
  value: {
    env: {
      PROD: false,
      DEV: true,
      VITE_API_URL: 'http://localhost:3000',
    },
  },
  writable: true,
});

const mockFetch: typeof fetch = vi.fn(() =>
  Promise.resolve(
    new Response(JSON.stringify({}), {
      status: 200,
      headers: new Headers({ 'Content-Type': 'application/json' }),
    }),
  ),
);

globalThis.fetch = mockFetch;

beforeEach(() => {
  vi.clearAllMocks();
  sessionStore.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});
