import { afterEach, describe, expect, it, vi } from 'vitest';

import { knowledgeApi } from './knowledge';

const originalFetch = globalThis.fetch;
const originalLocalStorage = globalThis.localStorage;

const installLocalStorageMock = () => {
  const storage = new Map<string, string>();
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: vi.fn((key: string) => storage.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        storage.set(key, value);
      }),
      removeItem: vi.fn((key: string) => {
        storage.delete(key);
      }),
      clear: vi.fn(() => {
        storage.clear();
      }),
    },
  });
};

const encoder = new TextEncoder();

const responseWithBody = (payload: string): Response => {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(payload));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
};

describe('frontend workflow projection event client', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: originalLocalStorage,
    });
    vi.restoreAllMocks();
  });

  it('builds frontend event history URL with cursor query params', async () => {
    installLocalStorageMock();

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          workflow_run_id: 'workflow-1',
          after_source_sequence: 10,
          after_cursor: 'cursor-1',
          next_cursor: 'cursor-2',
          events: [],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    globalThis.fetch = fetchMock;

    const response = await knowledgeApi.getFrontendWorkflowEvents(
      'project-1',
      'source-document:doc-1',
      'workflow-1',
      {
        after_cursor: 'cursor-1',
        after_source_sequence: 10,
        limit: 25,
      },
    );

    expect(response.data.next_cursor).toBe('cursor-2');
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain(
      '/api/projects/project-1/knowledge/source-documents/source-document%3Adoc-1/workflows/workflow-1/frontend-events',
    );
    expect(url).toContain('after_cursor=cursor-1');
    expect(url).toContain('after_source_sequence=10');
    expect(url).toContain('limit=25');
  });

  it('parses frontend_workflow_event SSE payloads and returns cleanup function', async () => {
    installLocalStorageMock();

    const onEvent = vi.fn();
    const onError = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue(
      responseWithBody(
        [
          'id: event-1',
          'event: frontend_workflow_event',
          'data: {"projection_event_id":"event-1","source_event_id":"source-1","source_sequence_number":1,"projection_version":1,"projection_type":"workflow_draft_claim_compaction_next_work_scheduled","event_type":"x","operation_key":null,"canonical_phase":null,"workflow_run_id":"workflow-1","project_id":"project-1","document_id":"document-1","payload":{},"occurred_at":"2026-01-01T00:00:00Z","causation_command_id":null,"correlation_id":null}',
          '',
          '',
        ].join('\n'),
      ),
    );
    globalThis.fetch = fetchMock;

    const stop = knowledgeApi.streamFrontendWorkflowEvents(
      'project-1',
      'document-1',
      'workflow-1',
      { after_cursor: 'cursor-1' },
      onEvent,
      onError,
    );

    expect(typeof stop).toBe('function');
    await vi.waitFor(() => {
      expect(onEvent).toHaveBeenCalledTimes(1);
    });
    expect(onEvent.mock.calls[0][0].projection_event_id).toBe('event-1');
    expect(onError).not.toHaveBeenCalled();

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('/frontend-events/stream');
    expect(url).toContain('after_cursor=cursor-1');

    stop();
  });
});
