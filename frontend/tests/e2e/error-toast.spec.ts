import { test, expect } from '@playwright/test';

console.log('>>> error-toast.spec.ts is loaded');

const MASTER_KEY = process.env.MASTER_KEY || '12345678';

test.describe('Global Error Toast (400 Bad Request)', () => {
  test('should show toast with error message when project creation fails with 400', async ({ page, request }) => {
    // 1. Login via API to get token
    const loginResp = await request.post('/api/auth/login', {
      data: { master_key: MASTER_KEY }
    });
    expect(loginResp.ok()).toBeTruthy();
    const data = await loginResp.json();
    const token = data.session_token || data.token;
    expect(token).toBeTruthy();

    // 2. Set token in sessionStorage for browser
    await page.addInitScript((t: string) => {
      window.sessionStorage.setItem('mrak_session_token', t);
    }, token);

    // 3. Setup route to intercept POST /api/projects and return 400 with error message
    const errorMessage = 'Проект с таким именем уже существует';
    await page.route('**/api/projects', async (route) => {
      if (route.request().method() === 'POST') {
        console.log('Intercepted POST /api/projects, returning 400');
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ error: errorMessage })
        });
      } else {
        await route.fallback();
      }
    });

    // 4. Navigate to workspace
    await page.goto('/workspace');
    await expect(page.locator('[data-testid="workspace-canvas"]')).toBeVisible({ timeout: 15000 });

    // 5. Trigger project creation via API client
    await page.evaluate(async () => {
      const { api } = await import('/src/api/client.ts');
      await api.projects.create({ name: 'Duplicate', description: '' });
    });

    // 6. Wait for toast to appear
    const toast = page.locator('[role="status"]');
    await expect(toast).toBeVisible({ timeout: 5000 });
    const toastText = await toast.textContent();
    expect(toastText).toContain(errorMessage);
  });
});
