/**
 * Types for thread, message, and memory entities.
 * Used in dialogs UI.
 */

import type { components } from '../../../shared/api/generated/schema';

export type Thread = components['schemas']['ThreadResponse'];

export interface Client {
  id: string;
  full_name?: string | null;
  username?: string | null;
  chat_id: number;
}

export interface LastMessage {
  content: string;
  created_at: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool' | 'manager';
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
