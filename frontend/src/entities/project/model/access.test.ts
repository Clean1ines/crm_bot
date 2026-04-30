import { describe, expect, it } from 'vitest';

import { getProjectHomePath, getProjectHomeSegment, isProjectAdminRole } from './access';

describe('project access helpers', () => {
  it('routes manager projects to tickets by default', () => {
    expect(getProjectHomeSegment('manager')).toBe('tickets');
    expect(getProjectHomePath('project-1', 'manager')).toBe('/projects/project-1/tickets');
  });

  it('keeps dialogs as the default for admin roles', () => {
    expect(getProjectHomeSegment('owner')).toBe('dialogs');
    expect(getProjectHomeSegment('admin')).toBe('dialogs');
  });

  it('classifies only owner and admin as project admins', () => {
    expect(isProjectAdminRole('owner')).toBe(true);
    expect(isProjectAdminRole('admin')).toBe(true);
    expect(isProjectAdminRole('manager')).toBe(false);
    expect(isProjectAdminRole('viewer')).toBe(false);
    expect(isProjectAdminRole(null)).toBe(false);
  });
});
