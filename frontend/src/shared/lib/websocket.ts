import { useEffect, useRef, useState, useCallback } from 'react';
import { getSessionToken } from '../api/client';

export interface WebSocketMessage {
  type: string;
  [key: string]: unknown;
}

interface UseWebSocketOptions {
  threadId: string | null;
  onMessage: (message: WebSocketMessage) => void;
  onError?: (event: Event) => void;
  onClose?: (event: CloseEvent) => void;
  reconnect?: boolean;
  reconnectInterval?: number;
}

/**
 * React hook for managing WebSocket connection to a thread.
 * Automatically handles authentication, reconnection, and cleanup.
 */
export function useWebSocket({
  threadId,
  onMessage,
  onError,
  onClose,
  reconnect = true,
  reconnectInterval = 5000,
}: UseWebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isManualCloseRef = useRef(false);

  const connect = useCallback(() => {
    if (!threadId) return;

    const token = getSessionToken();
    if (!token) {
      console.error('No session token, cannot connect WebSocket');
      return;
    }

    const baseUrl = import.meta.env.VITE_API_URL || '';
    const wsUrl = baseUrl.replace(/^http/, 'ws');
    const fullUrl = `${wsUrl}/ws/${threadId}`;

    const ws = new WebSocket(fullUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected', threadId);
      setIsConnected(true);
      ws.send(JSON.stringify({ token }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (err) {
        console.error('Failed to parse WebSocket message', err);
      }
    };

    ws.onerror = (event) => {
      console.error('WebSocket error', event);
      onError?.(event);
    };

    ws.onclose = (event) => {
      console.log('WebSocket closed', event.code, event.reason);
      setIsConnected(false);
      onClose?.(event);
      if (reconnect && !isManualCloseRef.current) {
        if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          connect();
        }, reconnectInterval);
      }
    };
  }, [threadId, onMessage, onError, onClose, reconnect, reconnectInterval]);

  const disconnect = useCallback(() => {
    isManualCloseRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  useEffect(() => {
    if (threadId) {
      isManualCloseRef.current = false;
      connect();
    }
    return () => {
      disconnect();
    };
  }, [threadId, connect, disconnect]);

  return { isConnected, disconnect };
}
