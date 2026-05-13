import { describe, expect, it } from 'vitest';

import { getErrorMessage, isTechnicalErrorMessage, sanitizeErrorMessage } from './errors';

describe('frontend user-facing error sanitizing', () => {
  it('masks database constraint details from plain strings', () => {
    const raw = 'duplicate key value violates unique constraint "pk_knowledge_entry_source_refs" DETAIL: Key (entry_id, source_chunk_id, source_index)=(abc, def, 1) already exists.';

    const message = sanitizeErrorMessage(raw);

    expect(message).toContain('Внутренняя ошибка сервера');
    expect(message).not.toContain('duplicate key value');
    expect(message).not.toContain('pk_knowledge_entry_source_refs');
    expect(message).not.toContain('DETAIL');
  });

  it('masks database constraint details from backend detail payloads', () => {
    const message = getErrorMessage({
      detail: 'asyncpg.exceptions.UniqueViolationError: duplicate key value violates unique constraint "some_db_constraint"',
    });

    expect(message).toContain('Внутренняя ошибка сервера');
    expect(message).not.toContain('asyncpg');
    expect(message).not.toContain('some_db_constraint');
  });

  it('keeps safe local validation messages readable', () => {
    expect(getErrorMessage(new Error('Укажите email менеджера'))).toBe('Укажите email менеджера');
  });

  it('uses a friendly validation message for structured validation payloads', () => {
    expect(getErrorMessage({ detail: [{ msg: 'Field required' }] })).toBe(
      'Проверьте заполненные поля и попробуйте ещё раз.',
    );
  });

  it('detects technical stack traces and filesystem paths', () => {
    expect(isTechnicalErrorMessage('Traceback (most recent call last): File "/app/src/api.py", line 12')).toBe(true);
  });
});
