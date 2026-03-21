// frontend/src/app/test/setup.ts
import { vi, beforeEach, afterEach } from 'vitest';

// Mock sessionStorage for tests (jsdom doesn't provide it by default)
const mockSessionStorage: any = {
  store: new Map<string, string>(),
  getItem: vi.fn((key: string): string | null => mockSessionStorage.store.get(key) ?? null),
  setItem: vi.fn((key: string, value: string): void => { mockSessionStorage.store.set(key, value); }),
  removeItem: vi.fn((key: string): void => { mockSessionStorage.store.delete(key); }),
  clear: vi.fn((): void => { mockSessionStorage.store.clear(); }),
};

Object.defineProperty(window, 'sessionStorage', {
  value: mockSessionStorage,
  writable: true,
  configurable: true,
});

// Mock import.meta.env for Vite-specific code
Object.defineProperty(global, 'import.meta', {
  value: {
    env: {
      PROD: false,
      DEV: true,
      VITE_API_URL: 'http://localhost:3000',
    },
  },
  writable: true,
});

// Mock fetch for tests
global.fetch = vi.fn(() =>
  Promise.resolve({
    json: () => Promise.resolve({}),
    ok: true,
    status: 200,
    headers: new Map(),
  } as any)
);

// Reset mocks before each test
beforeEach(() => {
  vi.clearAllMocks();
  mockSessionStorage.store.clear();
});

// Cleanup after each test
afterEach(() => {
  vi.restoreAllMocks();
});
