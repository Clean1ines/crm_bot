/**
 * Types for thread, message, and memory entities.
 * Used in dialogs UI.
 */

import type { components } from '../../../shared/api/generated/schema';

export type Thread = components['schemas']['ThreadResponse'];
export type Client = NonNullable<Thread['client']>;
export type LastMessage = NonNullable<Thread['last_message']>;

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  created_at: string;
  metadata?: {
    tokens?: number;
    latency_ms?: number;
    explanation?: string;
    [key: string]: unknown;
  };
}

export interface TimelineEvent {
  id: number;
  type: string;
  payload: Record<string, unknown>;
  ts: string;
}

export interface MemoryEntry {
  id: string;
  key: string;
  value: unknown;
  type: string;
  created_at: string;
  updated_at: string;
}

export interface ThreadState {
  [key: string]: unknown;
}
