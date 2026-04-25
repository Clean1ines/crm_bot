/**
 * Types for thread, message, and memory entities.
 * Used in dialogs UI.
 */

import type { components } from '../../../shared/api/generated/schema';

export type Thread = components['schemas']['ThreadResponse'];

export interface Client {
  id: string;
  user_id?: string | null;
  full_name?: string | null;
  username?: string | null;
  email?: string | null;
  company?: string | null;
  phone?: string | null;
  metadata?: Record<string, unknown>;
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
  client?: Client | null;
  status?: string;
  created_at?: string | null;
  updated_at?: string | null;
  interaction_mode?: string | null;
  [key: string]: unknown;
}
