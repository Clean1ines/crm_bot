import { test, expect } from '@playwright/test';

console.log('>>> navigation.spec.ts is loaded');
const MASTER_KEY = process.env.MASTER_KEY || '12345678';

test.describe('Project Navigation', () => {
  test('TASK-006: Clicking project in sidebar navigates to /workspace with projectId', async ({ page, request }) => {
    const loginResp = await request.post('/api/auth/login', {
      data: { master_key: MASTER_KEY }
    });
    expect(loginResp.ok()).toBeTruthy();
    const data = await loginResp.json();
    const token = data.session_token || data.token;
    expect(token).toBeTruthy();

    const projectName = `E2E-Project-${Date.now()}`;
    const createResp = await request.post('/api/projects', {
      headers: { 'Authorization': `Bearer ${token}` },
      data: { name: projectName, description: 'test' }
    });
    expect(createResp.status()).toBe(201);
    const project = await createResp.json();
    const projectId = project.id;

    await page.addInitScript((t: string) => {
      window.sessionStorage.setItem('mrak_session_token', t);
    }, token);

    await page.goto('/');
    await expect(page.locator('[data-testid="main-header"]')).toBeVisible();

    const projectLocator = page.locator('[data-testid="project-item"]').filter({ hasText: projectName }).first();
    await expect(projectLocator).toBeVisible();
    await projectLocator.click();

    await expect(page).toHaveURL(new RegExp(`.*/workspace\\?projectId=${projectId}`), { timeout: 10000 });

    await expect(page.locator('[data-testid="sidebar"]').getByText(projectName)).toBeVisible({ timeout: 10000 });
  });
});
