import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { WorkflowTimerCard } from './WorkflowTimerCard';

describe('WorkflowTimerCard', () => {
  it('does not label stopped review-ready workflows as active processing', () => {
    const markup = renderToStaticMarkup(
      <WorkflowTimerCard
        workflowStatus="waiting_for_review"
        timer={{
          mode: 'stopped',
          active_elapsed_seconds: 75,
          wall_elapsed_seconds: 75,
          current_active_started_at: null,
          is_live: false,
        }}
      />,
    );

    expect(markup).toContain('Время обработки');
    expect(markup).not.toContain('Активная обработка');
    expect(markup).toContain('1:15');
  });
});
