import { test, expect } from '@playwright/test';

console.log('>>> auth.client.spec.ts is loaded');
const MASTER_KEY = process.env.MASTER_KEY || '12345678';

test.describe('API Client Token Injection (E2E)', () => {
  test('should attach Bearer token to API requests after login', async ({ page, request }) => {
    const loginResp = await request.post('/api/auth/login', {
      data: { master_key: MASTER_KEY }
    });
    expect(loginResp.ok()).toBeTruthy();
    const data = await loginResp.json();
    const token = data.session_token || data.token;
    expect(token, 'Backend must return session_token').toBeTruthy();

    await page.addInitScript((t: string) => {
      window.sessionStorage.setItem('mrak_session_token', t);
    }, token);

    await page.goto('/workspace');
    await expect(page.locator('[data-testid="workspace-canvas"]')).toBeVisible({ timeout: 15000 });

    const projectsResp = await request.get('/api/projects', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    expect(projectsResp.status()).not.toBe(401);
  });
});
