// frontend/src/utils/logger.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { frontendLogger } from '@/shared/lib/logger';

// Mock console methods with proper typing
const mockConsole: Record<string, ReturnType<typeof vi.fn>> = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
  log: vi.fn(),
};

describe('frontendLogger', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.entries(mockConsole).forEach(([key, fn]) => {
      vi.spyOn(console, key as keyof Console).mockImplementation(fn);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should export all required methods', () => {
    expect(typeof frontendLogger.debug).toBe('function');
    expect(typeof frontendLogger.info).toBe('function');
    expect(typeof frontendLogger.warn).toBe('function');
    expect(typeof frontendLogger.error).toBe('function');
    expect(typeof frontendLogger.registerGlobalHandlers).toBe('function');
  });

  it('should log to console in development mode', () => {
    frontendLogger.info('dev log');
    expect(mockConsole.info).toHaveBeenCalled();
  });

  it('should handle Error objects', () => {
    const err = new Error('test');
    frontendLogger.error('failed', err);
    expect(mockConsole.error).toHaveBeenCalled();
  });

  it('should include timestamp in ISO format', () => {
    frontendLogger.info('test');
    const callArgs = mockConsole.info.mock.calls[0];

    expect(callArgs[1].timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it('should merge custom context', () => {
    frontendLogger.info('test', { customKey: 'value' });
    const callArgs = mockConsole.info.mock.calls[0];

    expect(callArgs[1].customKey).toBe('value');
  });

  it('should register global error handlers (noop in tests)', () => {
    expect(() => frontendLogger.registerGlobalHandlers()).not.toThrow();
  });
});
